# Review Mapping

Smart Parking Lot Allocation & Billing System — **DBMS PBL Project 20**.

Each line of the graded statement, mapped to the exact file, table, view,
function or screen that satisfies it. Paths are relative to the repository root.

Quick orientation:

| Where | What is in it |
|---|---|
| `db/migrations/` | The whole database, 12 numbered scripts, applied in order |
| `db/tests/` | Constraint and RLS tests, runnable with `psql -f` |
| `api/` | Python (FastAPI) application layer |
| `web/` | The interface |
| `docs/database/` | ER diagram, normalization, data dictionary, demonstration queries |
| `docs/screens/` | 18 output screens |

---

## Review 1 — problem, ER model, initial schema (5 marks)

| Rubric line | Where it is satisfied |
|---|---|
| Problem identification, scope, objectives | [`README.md`](../README.md) § *The problem* and § *What the system does* |
| Users and roles | `user_role` enum (`db/migrations/001`); `app_user.role`; three PostgreSQL roles `parking_admin` / `parking_operator` / `parking_customer` created in `001` and granted in `009` |
| Functional requirements | [`README.md`](../README.md) § *What the system does*, cross-referenced to the screen that implements each |
| **ER diagram** covering facilities, floors, zones, slots, vehicle types, vehicles, customers, reservations, parking sessions, passes, tariffs, bills, payments | [`docs/database/ER_DIAGRAM.md`](database/ER_DIAGRAM.md) — Mermaid diagram of all 16 tables, plus a second diagram showing how the slot/vehicle-type match is enforced |
| Initial relational schema: tables, primary keys, relationships | [`docs/database/DATA_DICTIONARY.md`](database/DATA_DICTIONARY.md); cardinality table in `ER_DIAGRAM.md` §4 |

All thirteen entities the statement names are present as tables. `violation`,
`pass_type` and `app_user` are additional, required by the violations report and
the role model.

---

## Review 2 — normalization, DDL, sample data, SQL (5 marks)

### Normalized design to 3NF with functional dependencies

| Rubric line | Where |
|---|---|
| Functional dependencies, written out | [`NORMALIZATION.md`](database/NORMALIZATION.md) §2 — 28 FDs (F1–F28) plus 5 derived dependencies (D1–D5) |
| 1NF → 2NF → 3NF derivation | `NORMALIZATION.md` §3 — each normal form applied to the flat parking record, with the specific violation and the decomposition that removes it |
| Concise data dictionary | [`DATA_DICTIONARY.md`](database/DATA_DICTIONARY.md) — every table, column, type, constraint, default and description, **generated from the live schema** by `tests/gen_data_dictionary.py` so it cannot drift |
| Evidence of 3NF | `NORMALIZATION.md` §6 — per-table table, plus a BCNF note |

Worth raising in the viva: §4 and §5 of that document explain three attributes
deliberately **not** stored (`slot.status`, `parking_session.status`,
`parking_pass.status`) and two denormalisations that are defended rather than
apologised for.

### DDL with constraints enforcing the five business rules

Each rule is enforced **declaratively in the database**, not in application
code, and each has been tested to failure with the real error captured.

| # | Business rule | Enforced by | File | Test |
|---|---|---|---|---|
| 1 | **One active vehicle per slot** | `uq_active_session_slot` — partial unique index `ON parking_session (slot_id) WHERE exit_time IS NULL` | `004_operations.sql` | [TESTING.md](TESTING.md) TEST 1 |
| 1b | One active slot per vehicle (mirror) | `uq_active_session_vehicle` — same shape on `vehicle_id` | `004_operations.sql` | TEST 2 |
| 2 | **Slot / vehicle-type match** | Three constraints: `UNIQUE (slot_id, vehicle_type_id)` on `slot`, `UNIQUE (vehicle_id, vehicle_type_id)` on `vehicle`, and two composite foreign keys from `parking_session` to both. No trigger — the invalid row cannot be represented | `003` + `004` | TEST 3, TEST 3b |
| 3 | **Exit after entry** | `CHECK (exit_time IS NULL OR exit_time > entry_time)` | `004_operations.sql` | TEST 4 |
| 4 | **Reservation expiry** | `CHECK (reserved_until > reserved_from)`; `reservation_status` enum; `EXCLUDE USING gist (slot_id WITH =, tstzrange(...) WITH &&) WHERE status IN ('held','confirmed')`; `fn_expire_stale_reservations()` sweep | `004` + `006` | TEST 5, TEST 6 |
| 5 | **Tariff-based charges** | `fn_calculate_charge(session_id)`; `trg_bill_enforce_amounts` overwrites any client-supplied amount with its output; `total_amount` is `GENERATED ALWAYS`; `CHECK (base_amount >= 0)` | `005_functions.sql` | TEST 7, **TEST 8** |

**TEST 8 is the one to demonstrate.** A client posts a bill claiming the parking
cost ₹1.00. The row is accepted and the trigger silently replaces the figure:

```
     source      | base  | tax  | total
-----------------+-------+------+-------
 client claimed  |  1.00 | 0.00 |  1.00
 database stored | 35.00 | 6.30 | 41.30
```

### Other integrity

| Requirement | Where |
|---|---|
| Primary keys | All 16 tables, `BIGINT GENERATED ALWAYS AS IDENTITY` |
| Foreign keys with deliberate `ON DELETE` | 31 of them; each commented with why that action and not another (`002`–`004`) |
| `UNIQUE` | 18, including `vehicle.plate_number`, `parking_session.ticket_no`, `bill.session_id` |
| `NOT NULL` | On every attribute the domain requires |
| `CHECK` | 30, including plate format, phone format, non-negative money, sane tariff caps |
| `DEFAULT` | Considered per column — see `DATA_DICTIONARY.md` |
| Exclusion constraints | 3: no overlapping reservations, no overlapping passes, no overlapping tariffs |

### Sample data at demonstration volume

`db/migrations/010_seed.sql` and `011_seed_history.sql`:

| | Seeded |
|---|--:|
| Facilities / floors / zones | 2 / 5 / 10 |
| Slots (5 vehicle types, 1 out of service) | 134 |
| Customers (3 registered but never parked) | 31 |
| Vehicles | 46 |
| Staff and customer logins | 8 |
| Parking sessions over the last 30 days | ~1,600 |
| Sessions currently open | 20 |
| Bills (paid / partly paid / unpaid) | ~1,590 |
| Payments across 5 methods | ~1,400 |
| Reservations in all five statuses | 32 |
| Passes: active, scheduled, expired, cancelled | 27 |
| Violations of all five kinds | ~29 |

Arrivals follow a real curve — a 09:00 morning peak and a 17:00 evening peak,
quieter weekends, near-empty small hours — so the peak-hours report has a shape
to show rather than a flat line. See `docs/screens/09-report-peak-hours.png`.

### SQL demonstrating joins, subqueries, aggregation and views

[`docs/database/queries.sql`](database/queries.sql) — 16 commented queries, each
labelled with the rubric line it answers. All return rows on the shipped seed.

| Feature | Query |
|---|---|
| Inner join, 3 tables | Q1 |
| Left outer join | Q2 |
| Five-table join | Q3 |
| `GROUP BY … HAVING` | Q4 |
| Correlated subquery | Q5 |
| Subquery in `FROM` | Q6 |
| `NOT EXISTS` | Q7 |
| `IN (subquery)` | Q8 |
| Window functions — `RANK`, running total, moving average | Q9 |
| `CASE` | Q10 |
| Date arithmetic | Q11 |
| `UNION ALL` | Q12 |
| Self-join | Q13 |
| The seven views | Q14 |
| `fn_calculate_charge` checked against its tariff | Q15 |
| `EXPLAIN` showing index usage | Q16 |

### Views — one per required report

All in `db/migrations/007_views.sql`, all created `WITH (security_invoker = true)`
so row-level security still applies through them.

| Report the statement names | View | Screen |
|---|---|---|
| Occupancy | `v_current_occupancy` | `08-report-occupancy.png` |
| Free slots | `v_free_slots` | `14-report-free-slots.png` |
| Peak hours | `v_peak_hours` | `09-report-peak-hours.png` |
| Duration | `v_session_duration` | `11-report-duration.png` |
| Pass usage | `v_pass_usage` | `12-report-pass-usage.png` |
| Violations | `v_violations` | `13-report-violations.png` |
| Revenue | `v_revenue_daily` | `10-report-revenue.png` |

---

## Review 3 — working application (5 marks)

### A Python application connected to the designed database

`api/` — FastAPI over PostgreSQL via psycopg 3. The statement asks for Java or
Python; this is Python. The layer is deliberately thin: every business rule,
every amount and every concurrency guarantee lives in the database.

| File | Role |
|---|---|
| `api/main.py` | Routes |
| `api/db.py` | Connection pool; declares the caller's identity to the database per transaction so RLS applies |
| `api/auth.py` | bcrypt password hashing, JWT bearer tokens, role guards |
| `api/errors.py` | Maps PostgreSQL constraint names to messages an operator can act on |
| `api/config.py` | Environment configuration |

### Required functionality

| Required | Screen | Backed by |
|---|---|---|
| Slot search | `web/slots.html` | `v_current_occupancy`, `v_free_slots` |
| Reservation | `web/reservations.html` | `reservation` + `ex_reservation_no_overlap` |
| Gate entry / exit | `web/gate.html` | `fn_gate_entry`, `fn_gate_exit` |
| Slot allocation | automatic on entry | `fn_allocate_slot` with `SELECT … FOR UPDATE` |
| Duration billing | `web/billing.html` | `fn_calculate_charge` + `trg_bill_enforce_amounts` |
| Pass management | `web/passes.html` | `parking_pass`, `pass_type`, `v_pass_usage` |
| Payment | `web/billing.html` | `payment` + `trg_payment_sync_bill_status` |
| Reporting | `web/reports.html` | all seven views |
| Facility / tariff administration | `web/settings.html` | `facility`, `vehicle_type`, versioned `tariff` |
| Customer and vehicle CRUD | `web/customers.html` | `customer`, `vehicle` |

### Demonstration of CRUD, search, validation, reports, error handling

| Rubric line | Evidence |
|---|---|
| **CRUD** | Create: customer, vehicle, reservation, pass, payment, tariff. Read: every screen. Update: reservation status, tariff supersession, bill status by trigger. Delete: vehicle (blocked by `ON DELETE RESTRICT` when history exists), pass cancellation as a soft close |
| **Search** | Plate search at the gate; customer search by name or phone; bill filter by registration and status; slot filter by floor, zone, vehicle type and availability |
| **Validation** | Client-side for responsiveness, database as the real gate. 20 cases tabulated in [TESTING.md](TESTING.md) §4 |
| **Reports** | Seven tabs, each on its own view, all rendering real data |
| **Error handling** | `api/errors.py` maps constraint names to plain English; the UI shows them at field level, not as a generic banner |

### Transaction awareness

`db/migrations/006_gate_transactions.sql`. `fn_gate_entry` takes a row lock on
the candidate bay with `SELECT … FOR UPDATE SKIP LOCKED` before inserting, so
two operators pressing *Record arrival* at the same instant cannot be handed the
same bay. The header comment traces the interleaving that would occur without
the lock. `fn_gate_exit` locks the session row before stamping the exit and
raising the bill. Each function body is one transaction: it commits whole or
not at all.

### Indexing of frequently searched attributes

`db/migrations/008_indexes.sql` — 15 indexes, each carrying a `COMMENT`
naming the query it serves; `queries.sql` Q16 lists them from the catalogue.

Q16 is honest about one thing worth knowing before the viva: the plate lookup
plans as a **sequential scan**, because `vehicle` holds ~50 rows in a single
page and reading it is cheaper than an index plus a heap fetch. Q16b re-runs it
with `enable_seqscan = off` to prove the index exists and serves the predicate,
and Q16c shows `parking_session` at ~1,600 rows choosing the partial index
unprompted.

### Source code, database script, test data, output screens

| Deliverable | Where |
|---|---|
| Source code | `api/`, `web/` |
| Database script | `db/migrations/001` … `012`, applied in order |
| Test data | `010_seed.sql`, `011_seed_history.sql` |
| Output screens | `docs/screens/` — 18 PNGs at 2× |
| Testing evidence | [`docs/TESTING.md`](TESTING.md) |

---

## Cross-cutting rubric lines

| Line | Where |
|---|---|
| Normalization | `NORMALIZATION.md` — derivation, not assertion |
| Data integrity | 31 FKs, 30 CHECKs, 18 UNIQUEs, 3 exclusion constraints; all tested |
| Transaction awareness | `006_gate_transactions.sql`; `SELECT … FOR UPDATE SKIP LOCKED` |
| Indexing | `008_indexes.sql`, each commented with its query |
| Input validation | Client and database; 20 cases in `TESTING.md` §4 |
| Systematic testing | 16 constraint tests, 9 RLS tests, 39-check end-to-end suite — all runnable, all captured |
| Security | Row-level security on all 9 user-data tables, 26 policies, no `USING (true)` anywhere; bcrypt; no payment credentials collected or stored |

---

## Two things to be ready for in the viva

**"Why is there no `status` column on `slot`?"** Because occupancy is already
determined by `parking_session`. Storing it as well is a second place to update
on every gate event with nothing forcing the two to agree. `NORMALIZATION.md` §4.

**"Show me that a car cannot park in a bike bay."** Not a trigger — three
constraints that make the row unrepresentable. Run `db/tests/constraint_tests.sql`
and read TEST 3 and TEST 3b: lying in *either* direction is refused by a
different foreign key.
