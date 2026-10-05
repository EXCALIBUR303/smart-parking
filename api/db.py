"""Database access.

The single important idea in this module is `session_scope`: every request runs
inside one transaction that first declares who is asking.

    SET LOCAL app.current_user_id = '<id>'
    SET LOCAL ROLE parking_customer | parking_operator | parking_admin

SET LOCAL is scoped to the transaction, so a pooled connection cannot carry one
request's identity into the next. This is what makes the row-level security
policies in migration 009 apply to real traffic rather than only to psql.

Note the API never queries as the database owner for user data. PostgreSQL
exempts a table owner from its own RLS policies, so querying as the owner would
silently disable every policy in the system.
"""
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

_pool = ConnectionPool(
    DATABASE_URL, min_size=1, max_size=10, open=False,
    # prepare_threshold=None disables psycopg3's automatic server-side
    # preparation of repeated queries (its default re-prepares a statement
    # after 5 executions on one connection). That is unsafe in front of a
    # transaction-mode pooler such as Supabase's Supavisor: the pooler may
    # hand two transactions on the "same" client connection to two different
    # backend connections, and a statement prepared against the first can
    # vanish before the second transaction runs it, raising "prepared
    # statement does not exist" intermittently as query volume grows.
    # Harmless against a direct, unpooled connection (plain local Postgres),
    # so this is safe to leave on unconditionally.
    kwargs={"row_factory": dict_row, "prepare_threshold": None},
)

ROLE_FOR = {
    "admin": "parking_admin",
    "operator": "parking_operator",
    "customer": "parking_customer",
}


def open_pool() -> None:
    _pool.open()
    _pool.wait(timeout=10)


def close_pool() -> None:
    _pool.close()


@contextmanager
def session_scope(user_id=None, role=None, *, privileged=False):
    """One transaction, with the caller's identity declared to the database.

    privileged=True skips the SET ROLE and runs as the connection owner. It is
    used only for authentication (reading a password hash before we know who
    the caller is), never for application data.
    """
    with _pool.connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                if not privileged:
                    if user_id is not None:
                        cur.execute("SELECT set_config('app.current_user_id', %s, true)", (str(user_id),))
                    db_role = ROLE_FOR.get(role)
                    if db_role:
                        # Role names cannot be parameterised; ROLE_FOR is a
                        # closed dictionary, so no caller value reaches this SQL.
                        cur.execute(f"SET LOCAL ROLE {db_role}")
                yield cur


def fetch_all(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def fetch_one(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()
