# SmartPark — Parking Lot Allocation & Billing System

**DBMS PBL Project 20** · PostgreSQL 17 · Python (FastAPI) · no build step

A working operations system for multi-level parking: live slot allocation,
reservations, gate entry and exit, tariff-based billing, passes, payments and
reporting.

![Dashboard](docs/screens/02-dashboard.png)

---

## The problem

Multi-level parking facilities need live slot allocation, reservations,
entry/exit records, passes and billing. Manual ticketing produces two specific
failures:

- **Slot conflicts.** Two attendants hand out the same bay because neither can
  see what the other just did.
- **Revenue leakage.** Charges are computed by hand from a rate card, so they
  are inconsistent, and unpaid exits go unrecorded.

This system removes both at the database level rather than by asking staff to be
careful. Gate entry takes a row lock on the bay it is about to allocate, so two
operators cannot be handed the same one. Every charge is computed by a single
database function from the tariff that was in force when the vehicle arrived —
the application cannot supply an amount, and if it tries, a trigger overwrites
it.

## What the system does

| Screen | What it is for |
|---|---|
| **Dashboard** | Live occupancy, today's takings, recent gate activity |
| **Slot map** | The building as a floor plan — floors, zones, aisles, every bay's state |
| **Gate** | Record an arrival (bay chosen and locked automatically) and a departure (bill raised on exit) |
| **Reservations** | Hold a bay for a future arrival; overlapping holds are impossible |
| **Passes** | Sell and cancel daily, weekly and monthly passes; a pass makes its stays free |
| **Billing** | Bills, invoices and recorded payments |
| **Reports** | Occupancy, peak hours, revenue, duration, pass usage, violations, free slots |
| **Customers** | Customers and their vehicles |
| **Settings** | Facilities, vehicle types and tariff versions (administrators only) |

---

# Getting it running

Written for someone comfortable with a browser but new to the command line.
Every command is meant to be copied whole and pasted into **Terminal**.

To open Terminal: press `Cmd + Space`, type `Terminal`, press Return.

## The short way

If PostgreSQL is already installed and running, these two commands do
everything:

```bash
cd ~/Desktop/smart-parking && ./setup.sh
```

```bash
./.venv/bin/uvicorn api.main:app --port 8077
```

Then open **http://127.0.0.1:8077** and sign in as `admin@smartpark.in` with the
password `Parking@123`.

If that worked, skip to [Try it in two minutes](#try-it-in-two-minutes). If
anything failed, or you would rather see each step, carry on below — the long
way does exactly the same thing, one command at a time.

To rebuild the database from scratch later: `./setup.sh --reset`

---

## The long way, one step at a time

### Step 1 — check you have PostgreSQL and Python

Paste this and press Return:

```bash
psql --version && python3 --version
```

You should see two version lines, PostgreSQL 14 or newer and Python 3.11 or
newer. If `psql` is not found on a Mac, install it with:

```bash
brew install postgresql@17
```

and then add it to your path for this session:

```bash
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
```

### Step 2 — start the database server

```bash
brew services start postgresql@17
```

Check it is listening:

```bash
pg_isready
```

You want to see `accepting connections`.

### Step 3 — go to the project folder

```bash
cd ~/Desktop/smart-parking
```

### Step 4 — create the database

```bash
createdb smartpark
```

Nothing is printed when this works. If it says the database already exists and
you want to start fresh, remove it first:

```bash
dropdb --if-exists smartpark && createdb smartpark
```

### Step 5 — build the schema and load the sample data

This runs all twelve migration scripts in order. It takes about a second.

```bash
for f in db/migrations/*.sql; do psql -q -v ON_ERROR_STOP=1 -d smartpark -f "$f" || break; done
```

Check it worked:

```bash
psql -d smartpark -c "SELECT count(*) AS slots FROM slot; SELECT count(*) AS sessions FROM parking_session;"
```

You should see about 134 slots and about 1,600 sessions.

### Step 6 — install the Python packages

This creates a private folder called `.venv` for this project's packages, so
nothing is installed system-wide.

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

### Step 7 — start the application

```bash
./.venv/bin/uvicorn api.main:app --port 8077
```

Leave this running. It prints `Application startup complete.`

### Step 8 — open it

Go to **http://127.0.0.1:8077** in your browser.

Sign in with any of these. The password for all of them is `Parking@123`.

| Role | Email | Sees |
|---|---|---|
| Administrator | `admin@smartpark.in` | Everything, both facilities, Settings |
| Gate operator | `ops.central@smartpark.in` | SmartPark Central only |
| Gate operator | `ops.river@smartpark.in` | SmartPark Riverside only |
| Customer | `rahul.sharma@example.com` | Only their own vehicles, bills and bookings |

Signing in as the operator and then as the customer is the quickest way to see
row-level security working: the customer sees 3 vehicles where the
administrator sees 46.

## Stopping and restarting

### To stop the application

Press `Ctrl + C` in the Terminal window where it is running.

### To start it again later

```bash
cd ~/Desktop/smart-parking && ./.venv/bin/uvicorn api.main:app --port 8077
```

The database keeps running in the background, so steps 1–6 are only needed once.

---

## Try it in two minutes

1. Sign in as `ops.central@smartpark.in`.
2. Open **Slot map**. Bays are colour-coded *and* labelled — free, reserved,
   occupied, out of service.
3. Open **Gate**. Type a registration that is on file but not currently parked —
   for example `TS10WX1515` — and press **Record arrival**. A bay is allocated
   and locked, and a ticket is issued.
4. Go back to **Slot map**: that bay now reads *Occupied*.
5. Back on **Gate**, paste the ticket number into **Departure** and press
   **Look up vehicle**. The running charge is shown, computed from the tariff.
6. Press **Confirm departure**. A bill is raised. Record a payment against it.
7. Open **Reports** and look at **Peak hours** — a real arrival curve with a
   morning and an evening peak.

To see an error handled well, try recording an arrival for a vehicle that is
already parked, or type `HELLO` as a registration.

---

## Running the tests

Start the application first (step 7), then in a **second** Terminal window:

```bash
cd ~/Desktop/smart-parking
```

**Prove every business rule rejects its violation** — 16 deliberate attempts to
break the database:

```bash
psql -d smartpark -f db/tests/constraint_tests.sql
```

**Prove row-level security actually restricts:**

```bash
psql -d smartpark -f db/tests/rls_tests.sql
```

**Run the end-to-end test** — sign in, reserve, gate entry, gate exit, bill,
payment, every report:

```bash
./.venv/bin/python tests/e2e_smoke.py
```

**Run the demonstration queries** — joins, subqueries, aggregation, windows,
views:

```bash
psql -d smartpark -f docs/database/queries.sql
```

**Regenerate the data dictionary** from the live schema:

```bash
./.venv/bin/python tests/gen_data_dictionary.py
```

**Retake the screenshots** (needs Google Chrome installed):

```bash
./.venv/bin/pip install playwright && ./.venv/bin/python tests/capture_screens.py
```

Captured results are in [`docs/TESTING.md`](docs/TESTING.md).

---

## How it is built

```
smart-parking/
├── db/
│   ├── migrations/          the whole database, 12 numbered scripts
│   │   ├── 001_extensions_roles_enums.sql
│   │   ├── 002_core_tables.sql
│   │   ├── 003_slot_vehicle_tariff.sql
│   │   ├── 004_operations.sql            ← business rules 1–4
│   │   ├── 005_functions.sql             ← business rule 5, triggers
│   │   ├── 006_gate_transactions.sql     ← SELECT … FOR UPDATE
│   │   ├── 007_views.sql                 ← the seven report views
│   │   ├── 008_indexes.sql
│   │   ├── 009_rls.sql                   ← row-level security
│   │   ├── 010_seed.sql
│   │   ├── 011_seed_history.sql
│   │   └── 012_column_comments.sql
│   └── tests/               constraint and RLS tests
├── api/                     Python (FastAPI) application layer
├── web/                     the interface — plain HTML, CSS and ES modules
├── tests/                   end-to-end suite, screenshot and docs generators
├── docs/
│   ├── database/            ER diagram, normalization, data dictionary, queries
│   ├── screens/             18 output screens
│   ├── TESTING.md
│   └── REVIEW_MAPPING.md    ← what to hand the evaluator
└── legacy-firebase/         the superseded prototype, kept but not wired up
```

**No build step and no npm.** The interface is plain HTML, CSS and ES modules
served straight from `web/`. Editing a file and refreshing the browser is the
whole development loop.

### Where the rules actually live

Everything that matters is enforced by PostgreSQL, not by application code:

| Rule | Enforced by |
|---|---|
| One vehicle per bay at a time | Partial unique index `uq_active_session_slot` |
| A car cannot use a bike bay | Two composite foreign keys — the row cannot exist |
| Exit must follow entry | `CHECK (exit_time > entry_time)` |
| No overlapping reservations | GiST exclusion constraint |
| Charges come from the tariff | `fn_calculate_charge()` + a trigger that overwrites any client-supplied amount |
| Who can see what | Row-level security, 26 policies across 9 tables |

Two operators cannot be handed the same bay because `fn_gate_entry` locks it
with `SELECT … FOR UPDATE SKIP LOCKED` before inserting.

---

## Configuration

Defaults work for local use with no configuration at all. To override:

| Variable | Default | Meaning |
|---|---|---|
| `SMARTPARK_DATABASE_URL` | `postgresql:///smartpark` | Database connection |
| `SMARTPARK_JWT_SECRET` | `dev-only-change-me` | Token signing key |

**Set a real secret before putting this anywhere other than your own machine:**

```bash
export SMARTPARK_JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

### Expiring stale reservations on a schedule

The API sweeps lapsed holds on every reservations request, which is enough for a
demo. On a server with `pg_cron` available you can schedule it instead:

```sql
SELECT cron.schedule('expire-holds', '*/5 * * * *',
                     'SELECT fn_expire_stale_reservations()');
```

The function is idempotent, so running it both ways is harmless.

---

## A note on payments

Payments are **recorded, not processed**. There is no payment gateway, and no
screen in this system collects a card number, a CVV or a UPI credential. A
payment row holds a method, a free-text receipt reference, an amount and a
timestamp — the same information an operator would write on a paper receipt.

---

## Documentation

| Document | What it covers |
|---|---|
| [REVIEW_MAPPING.md](docs/REVIEW_MAPPING.md) | Every Review 1/2/3 rubric line → the exact file that satisfies it |
| [ER_DIAGRAM.md](docs/database/ER_DIAGRAM.md) | Entity–relationship diagrams |
| [NORMALIZATION.md](docs/database/NORMALIZATION.md) | Functional dependencies and the 1NF → 2NF → 3NF derivation |
| [DATA_DICTIONARY.md](docs/database/DATA_DICTIONARY.md) | Every table and column, generated from the live schema |
| [queries.sql](docs/database/queries.sql) | 16 demonstration queries |
| [TESTING.md](docs/TESTING.md) | Constraint tests with real error output, RLS proof, validation table, contrast measurements |
| [DESIGN.md](docs/DESIGN.md) | The v2 design concept, the bay-state system, and the interaction logic |
| [CHANGES.md](docs/CHANGES.md) | What was created, modified and archived, and every defect found along the way |

---

## Troubleshooting

**`psql: command not found`**
Add PostgreSQL to your path for this Terminal session:
```bash
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
```

**`could not connect to server`**
The database is not running:
```bash
brew services start postgresql@17
```

**`address already in use` when starting the application**
Something else is on port 8077. Use another:
```bash
./.venv/bin/uvicorn api.main:app --port 8099
```
Then open `http://127.0.0.1:8099` instead.

**`database "smartpark" is being accessed by other users` when dropping it**
Stop the application first with `Ctrl + C`, then try again.

**The page loads but every panel says it could not load**
The application is not running, or is on a different port. Check the Terminal
window from step 7.
