"""Generate docs/database/DATA_DICTIONARY.md from the LIVE schema.

Hand-written dictionaries drift the moment a migration lands. This reads
information_schema and pg_catalog, so the document is a report on the database
that exists rather than a description of one somebody remembers.

Run:  ./.venv/bin/python tests/gen_data_dictionary.py
"""
import json
import os
import pathlib
import subprocess
import sys

PSQL = "/opt/homebrew/opt/postgresql@17/bin/psql"
DB = os.environ.get("SMARTPARK_DB", "smartpark")
OUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "database" / "DATA_DICTIONARY.md"


def q(sql):
    """Run a query and return rows as lists of strings.

    Results come back as JSON rather than delimiter-separated text: several
    column and constraint comments contain newlines, which silently split a
    delimited row into two malformed ones.
    """
    # json_agg over a subquery preserves that subquery's ORDER BY. Every
    # column must be aliased: two unaliased CASE expressions would both become
    # the JSON key "case" and one would be lost.
    wrapped = f"SELECT coalesce(json_agg(t), '[]'::json)::text FROM ({sql}) t"
    r = subprocess.run([PSQL, "-d", DB, "-t", "-A", "-c", wrapped],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"psql failed:\n{r.stderr}")
    rows = json.loads(r.stdout.strip() or "[]")
    out = []
    for row in rows:
        vals = [v for k, v in row.items() if k != "ordinality"]
        out.append(["" if v is None else str(v) for v in vals])
    return out


tables = q("""
    SELECT c.relname AS tname, COALESCE(obj_description(c.oid), '') AS tcomment
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'r'
     ORDER BY c.relname
""")

columns = q("""
    SELECT c.relname AS tname, a.attnum AS num, a.attname AS col,
           format_type(a.atttypid, a.atttypmod) AS typ,
           CASE WHEN a.attnotnull THEN 'NOT NULL' ELSE '' END AS notnull,
           COALESCE(pg_get_expr(d.adbin, d.adrelid), '') AS dflt,
           CASE WHEN a.attgenerated = 's' THEN 'GENERATED' ELSE '' END AS gen,
           COALESCE(col_description(c.oid, a.attnum), '') AS ccomment
      FROM pg_attribute a
      JOIN pg_class c ON c.oid = a.attrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
     WHERE n.nspname = 'public' AND c.relkind = 'r'
       AND a.attnum > 0 AND NOT a.attisdropped
     ORDER BY c.relname, a.attnum
""")

cons = q("""
    SELECT c.conrelid::regclass::text AS tname, c.conname AS cname,
           CASE c.contype WHEN 'p' THEN 'PRIMARY KEY' WHEN 'f' THEN 'FOREIGN KEY'
                          WHEN 'u' THEN 'UNIQUE' WHEN 'c' THEN 'CHECK'
                          WHEN 'x' THEN 'EXCLUDE' END AS kind,
           pg_get_constraintdef(c.oid) AS cdef,
           COALESCE(obj_description(c.oid, 'pg_constraint'), '') AS ccomment
      FROM pg_constraint c
     WHERE c.connamespace = 'public'::regnamespace
       AND c.conrelid <> 0
     ORDER BY c.conrelid::regclass::text,
              CASE c.contype WHEN 'p' THEN 1 WHEN 'u' THEN 2 WHEN 'f' THEN 3
                             WHEN 'c' THEN 4 ELSE 5 END, c.conname
""")

idx = q("""
    SELECT tablename AS tname, indexname AS iname, indexdef AS idef,
           COALESCE(obj_description(
             (schemaname||'.'||indexname)::regclass, 'pg_class'), '') AS icomment
      FROM pg_indexes WHERE schemaname = 'public'
     ORDER BY tablename, indexname
""")

enums = q("""
    SELECT t.typname AS ename,
           string_agg(quote_literal(e.enumlabel), ', ' ORDER BY e.enumsortorder) AS evals
      FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
      JOIN pg_namespace n ON n.oid = t.typnamespace
     WHERE n.nspname = 'public'
     GROUP BY t.typname ORDER BY t.typname
""")

rowcounts = {r[0]: r[1] for r in q("""
    SELECT relname AS tname, n_live_tup::text AS n FROM pg_stat_user_tables
     WHERE schemaname = 'public'
""")}

rls = {r[0]: r[1] for r in q("""
    SELECT c.relname AS tname,
           CASE WHEN c.relrowsecurity THEN 'enabled' ELSE 'not enabled' END AS state
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'r'
""")}

policies = {}
for t, p, cmd in q("""SELECT tablename AS tname, policyname AS pname, cmd AS c FROM pg_policies
                       WHERE schemaname='public' ORDER BY tablename, policyname"""):
    policies.setdefault(t, []).append(f"`{p}` ({cmd})")

by_table = {}
for row in columns:
    by_table.setdefault(row[0], []).append(row)
cons_by_table = {}
for row in cons:
    cons_by_table.setdefault(row[0], []).append(row)
idx_by_table = {}
for row in idx:
    idx_by_table.setdefault(row[0], []).append(row)

L = []
w = L.append
w("# Data Dictionary\n")
w("Smart Parking Lot Allocation & Billing System — DBMS PBL Project 20.\n")
w("**Generated from the live schema** by `tests/gen_data_dictionary.py`, which")
w("reads `information_schema` and `pg_catalog`. It is a report on the database")
w("that exists, not a description maintained by hand — regenerate it after any")
w("migration and it cannot drift.\n")
w(f"PostgreSQL objects: **{len(tables)} tables**, "
  f"**{sum(1 for c in cons if c[2]=='CHECK')} CHECK constraints**, "
  f"**{sum(1 for c in cons if c[2]=='FOREIGN KEY')} foreign keys**, "
  f"**{sum(1 for c in cons if c[2]=='EXCLUDE')} exclusion constraints**, "
  f"**{len(idx)} indexes**, **{len(enums)} enumerated types**.\n")
w("---\n")

w("## Enumerated types\n")
w("| Type | Values |")
w("|---|---|")
for name, vals in enums:
    w(f"| `{name}` | {vals} |")
w("")
w("---\n")

w("## Tables\n")
for tname, tcomment in tables:
    w(f"### `{tname}`\n")
    if tcomment:
        w(f"{tcomment}\n")
    w(f"*Rows in the seeded database: {rowcounts.get(tname, '0')}. "
      f"Row-level security: {rls.get(tname, 'unknown')}.*\n")
    w("| # | Column | Type | Null | Default | Description |")
    w("|--:|---|---|---|---|---|")
    for _, num, col, typ, notnull, default, gen, comment in by_table.get(tname, []):
        d = default.replace("nextval(", "seq(") if default else "—"
        if gen:
            d = "GENERATED"
        if len(d) > 42:
            d = d[:39] + "…"
        w(f"| {num} | `{col}` | `{typ}` | {'NOT NULL' if notnull else 'nullable'} "
          f"| {'`' + d + '`' if d != '—' else '—'} | {comment or ''} |")
    w("")

    tc = cons_by_table.get(tname, [])
    if tc:
        w("**Constraints**\n")
        w("| Name | Kind | Definition | Note |")
        w("|---|---|---|---|")
        for _, cname, kind, cdef, ccomment in tc:
            cd = cdef if len(cdef) <= 150 else cdef[:147] + "…"
            w(f"| `{cname}` | {kind} | `{cd}` | {ccomment} |")
        w("")

    ti = [i for i in idx_by_table.get(tname, [])
          if not any(i[1] == c[1] for c in tc)]
    if ti:
        w("**Indexes** (beyond those backing the constraints above)\n")
        w("| Name | Definition | Serves |")
        w("|---|---|---|")
        for _, iname, idef, icomment in ti:
            short = idef.split(" ON ", 1)[-1]
            w(f"| `{iname}` | `{short}` | {icomment.replace('SERVES: ', '')} |")
        w("")

    if policies.get(tname):
        w(f"**RLS policies:** {', '.join(policies[tname])}\n")
    w("")

w("---\n")
w("## Views\n")
views = q("""
    SELECT c.relname AS vname, COALESCE(obj_description(c.oid), '') AS vcomment,
           CASE WHEN c.reloptions::text LIKE '%security_invoker=true%'
                THEN 'yes' ELSE 'NO' END AS si
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname='public' AND c.relkind='v' AND c.relname LIKE 'v\\_%'
     ORDER BY c.relname
""")
w("| View | security_invoker | Purpose |")
w("|---|:--:|---|")
for name, comment, si in views:
    w(f"| `{name}` | {si} | {comment} |")
w("")
w("`security_invoker = true` on every view means row-level security is")
w("evaluated as the querying role. Without it a view runs as its owner and")
w("becomes a way around the policies it appears to respect.\n")

w("---\n")
w("## Functions\n")
fns = q("""
    SELECT p.proname AS fname,
           pg_get_function_identity_arguments(p.oid) AS args,
           CASE WHEN p.prosecdef THEN 'DEFINER' ELSE 'INVOKER' END AS sec,
           COALESCE(obj_description(p.oid, 'pg_proc'), '') AS fcomment
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname='public' AND p.proname LIKE 'fn\\_%'
     ORDER BY p.proname
""")
w("| Function | Security | Purpose |")
w("|---|---|---|")
for name, args, sec, comment in fns:
    w(f"| `{name}({args})` | {sec} | {comment} |")
w("")

OUT.write_text("\n".join(L))
print(f"wrote {OUT} ({len(L)} lines)")
