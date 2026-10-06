# Repository guide: what every file is for

SmartPark is a parking management system whose rules live in **PostgreSQL**. A
**Python** (FastAPI) layer sits between the database and a **browser** interface.
This guide walks through the repository folder by folder. It is written to be read
top to bottom when presenting the project.

## The shape of the project in one picture

```
 Browser (web/)                 Application (api/)                 Database (db/)
 ──────────────                 ───────────────────                ──────────────
 HTML pages and         ──►     FastAPI: one endpoint      ──►     PostgreSQL 17:
 JavaScript modules             per action; sets the               tables, constraints,
 (no build step)        ◄──     user's role, then asks     ◄──     triggers, functions,
                                the database                       views, security policies
```

The important design decision: **the rules are in the database, not in the code.**
Whatever the application does (or a hand-written SQL statement tries to do), the
database refuses data that breaks a rule. The application layer is deliberately thin.

## How one click travels through the files

Take **Gate → Record arrival**, the signature action:

| Step | File | What happens |
|--:|---|---|
| 1 | [`web/gate.html`](../web/gate.html), [`web/js/gate.js`](../web/js/gate.js) | The operator types a registration; the form validates it and calls the API |
| 2 | [`web/js/api.js`](../web/js/api.js) | The one place the browser talks to the server; adds the sign-in token |
| 3 | [`api/main.py`](../api/main.py) (`/api/gate/entry`) | Checks the user is staff, then calls one database function |
| 4 | [`api/db.py`](../api/db.py) | Opens a transaction and tells PostgreSQL who is asking (`SET LOCAL ROLE`), so row-level security applies |
| 5 | [`db/migrations/006_gate_transactions.sql`](../db/migrations/006_gate_transactions.sql) | `fn_gate_entry` finds a free bay of the right type, **locks it** (`FOR UPDATE SKIP LOCKED`), opens the session and issues a ticket, all in one transaction |
| 6 | [`db/migrations/004_operations.sql`](../db/migrations/004_operations.sql) | The constraints that make a double booking or a car-in-bike-bay impossible fire here |
| 7 | [`api/errors.py`](../api/errors.py) | If the database refused, turns the raw PostgreSQL error into a plain-English message |
| 8 | `web/js/gate.js`, [`web/js/motion.js`](../web/js/motion.js) | Shows the ticket and the allocated bay |

---

## Root files

| File | What it is |
|---|---|
| [`README.md`](../README.md) | The front page: the problem, objectives, features, architecture, the database at a glance, how to run it, how to test it, screenshots |
| [`setup.sh`](../setup.sh) | One command to build everything: creates the database, applies all 19 migrations in order, installs the Python packages. `./setup.sh --reset` rebuilds from scratch |
| [`requirements.txt`](../requirements.txt) | The Python packages the application needs (FastAPI, psycopg, bcrypt, PyJWT), pinned to tested versions |
| [`requirements-dev.txt`](../requirements-dev.txt) | Extra packages only for testing (pytest, httpx, Playwright) |
| [`pytest.ini`](../pytest.ini) | Tells pytest where the tests are and how to import the application |
| [`.env.example`](../.env.example) | The environment variables the application reads (database URL, token secret), documented with no real values. Real secrets are never committed |
| [`.gitignore`](../.gitignore) | Keeps secrets, virtual environments, caches and editor files out of git |
| [`vercel.json`](../vercel.json), [`.vercelignore`](../.vercelignore) | Settings for the online demo hosted on Vercel, and which folders are not uploaded to it |

## `db/`: the database (the heart of the project)

### `db/migrations/`: the database, built in 19 numbered steps

Applied in filename order. Each file has a header comment explaining its purpose and
the reasoning behind each rule.

| File | What it creates |
|---|---|
| [`001_extensions_roles_enums.sql`](../db/migrations/001_extensions_roles_enums.sql) | Two PostgreSQL extensions (`btree_gist`, which makes overlap-prevention constraints possible, and `citext` for case-insensitive e-mail), the three database roles (`parking_admin`, `parking_operator`, `parking_customer`) and the enumerated types (user roles, bill status, payment method…) |
| [`002_core_tables.sql`](../db/migrations/002_core_tables.sql) | The foundation tables: `app_user`, `facility`, `floor`, `zone`, `vehicle_type`, `customer` |
| [`003_slot_vehicle_tariff.sql`](../db/migrations/003_slot_vehicle_tariff.sql) | `slot`, `vehicle`, `tariff`, and the composite keys behind the "right bay for the right vehicle" rule |
| [`004_operations.sql`](../db/migrations/004_operations.sql) | `pass_type`, `parking_pass`, `reservation`, `parking_session`, `bill`, `payment`, `violation`. **Business rules 1 to 4 live here** |
| [`005_functions.sql`](../db/migrations/005_functions.sql) | `fn_calculate_charge` (the tariff arithmetic, **business rule 5**), and the triggers that overwrite any client-supplied bill amount and update bill status from payments |
| [`006_gate_transactions.sql`](../db/migrations/006_gate_transactions.sql) | `fn_allocate_slot`, `fn_gate_entry`, `fn_gate_exit` (the locking transactions) and `fn_expire_stale_reservations` |
| [`007_views.sql`](../db/migrations/007_views.sql) | The seven report views (occupancy, free slots, peak hours, duration, pass usage, violations, revenue) |
| [`008_indexes.sql`](../db/migrations/008_indexes.sql) | The indexes for frequently searched columns, each commented with the query it serves |
| [`009_rls.sql`](../db/migrations/009_rls.sql) | Row-level security: which rows each role may see or change (26 policies) |
| [`010_seed.sql`](../db/migrations/010_seed.sql) | Sample data: facilities, floors, zones, 134 bays, tariffs, pass products, users, customers, vehicles |
| [`011_seed_history.sql`](../db/migrations/011_seed_history.sql) | A month of realistic parking activity: sessions, bills, payments, reservations, passes, violations |
| [`012_column_comments.sql`](../db/migrations/012_column_comments.sql) | Descriptions on columns; they become the "Description" column of the data dictionary |
| [`013_integrity_service_audit.sql`](../db/migrations/013_integrity_service_audit.sql) | Ownership keys (a booking must use the customer's own vehicle), bay servicing, the audit trail and the live-activity view |
| [`014_supabase_hardening.sql`](../db/migrations/014_supabase_hardening.sql) | Locks down the default access Supabase gives its public API roles (does nothing on plain PostgreSQL) |
| [`015_customer_email_shape.sql`](../db/migrations/015_customer_email_shape.sql) | A format check on customer e-mail addresses |
| [`016_payment_within_balance.sql`](../db/migrations/016_payment_within_balance.sql) | A trigger that refuses a payment larger than what is still owed |
| [`017_zero_bill_is_paid.sql`](../db/migrations/017_zero_bill_is_paid.sql) | A ₹0 bill (free period or pass) is marked paid automatically |
| [`018_audit_and_rule_comments.sql`](../db/migrations/018_audit_and_rule_comments.sql) | Descriptions for the objects added in 013 to 016 |
| [`019_planned_facilities.sql`](../db/migrations/019_planned_facilities.sql) | Three planned (inactive) sites, so every table holds at least five sample rows |

### Other files in `db/`

| File | What it is |
|---|---|
| [`db/schema_snapshot.sql`](../db/schema_snapshot.sql) | **The whole finished schema in one file** (no data): every table, key, constraint, index, view, function, trigger, policy and grant. Read this to see the complete backend at a glance. Verified to load into an empty database with no errors |
| [`db/tests/constraint_tests.sql`](../db/tests/constraint_tests.sql) | 25 deliberate attempts to break the rules (two cars in one bay, exit before entry, a negative bill…). The database refuses 24; the 25th shows a trigger silently correcting a forged amount |
| [`db/tests/lifecycle_tests.sql`](../db/tests/lifecycle_tests.sql) | Time-driven rules: a lapsed reservation expires, a 30-hour stay is billed and flagged, a pass makes a stay free, an expired pass does not. Rolled back afterwards |
| [`db/tests/rls_tests.sql`](../db/tests/rls_tests.sql) | Proves row-level security: a customer sees only their own rows, an operator only their facility, and no identity means no rows |
| [`db/scripts/refresh_demo_history.sql`](../db/scripts/refresh_demo_history.sql) | Moves the sample history forward to today, so the demo does not show an empty "today" |

## `api/`: the application layer (Python, FastAPI)

| File | What it does |
|---|---|
| [`api/main.py`](../api/main.py) | All 45 endpoints: sign-in, slots, gate, reservations, passes, billing, customers, vehicles, reports, audit. Each is one SQL statement or one database-function call, with no business arithmetic of its own. Also serves the `web/` pages |
| [`api/db.py`](../api/db.py) | The connection pool, and `session_scope`: opens a transaction and declares the signed-in user and role to PostgreSQL, so row-level security applies to every request |
| [`api/auth.py`](../api/auth.py) | Password checking (bcrypt), signed sign-in tokens (JWT), and the "staff only" and "admin only" guards |
| [`api/errors.py`](../api/errors.py) | Translates PostgreSQL errors into messages a gate operator can act on (for example "That bay is already reserved for an overlapping period") |
| [`api/config.py`](../api/config.py) | Reads settings from environment variables; refuses to start online with the development secret |

Full list of endpoints: [`docs/API.md`](API.md).

## `web/`: the interface (plain HTML, CSS and JavaScript)

No build step and no framework: open a file, edit it, refresh the browser.

**The ten pages** (each loads its own script from `web/js/`):

| Page | Script | Screen |
|---|---|---|
| [`index.html`](../web/index.html) | (inline) | Sign-in |
| [`dashboard.html`](../web/dashboard.html) | [`dashboard.js`](../web/js/dashboard.js) | Live occupancy, takings, revenue chart, activity feed |
| [`slots.html`](../web/slots.html) | [`slots.js`](../web/js/slots.js), [`bay-sheet.js`](../web/js/bay-sheet.js) | The floor map, and the panel for one bay |
| [`gate.html`](../web/gate.html) | [`gate.js`](../web/js/gate.js) | Arrival and departure |
| [`reservations.html`](../web/reservations.html) | [`reservations.js`](../web/js/reservations.js) | Bookings |
| [`passes.html`](../web/passes.html) | [`passes.js`](../web/js/passes.js) | Selling and cancelling passes |
| [`billing.html`](../web/billing.html) | [`billing.js`](../web/js/billing.js) | Bills, invoices and the payments ledger |
| [`reports.html`](../web/reports.html) | [`reports.js`](../web/js/reports.js) | The seven reports and per-vehicle history |
| [`customers.html`](../web/customers.html) | [`customers.js`](../web/js/customers.js) | Customers and their vehicles |
| [`settings.html`](../web/settings.html) | [`settings.js`](../web/js/settings.js) | Tariffs, facilities and the audit trail (administrators only) |

**Shared modules in `web/js/`:**

| File | What it does |
|---|---|
| [`api.js`](../web/js/api.js) | The only code that talks to the server |
| [`ui.js`](../web/js/ui.js) | The shared interface: sidebar, sortable and searchable tables, dialogs, tabs, menus, toasts, keyboard shortcuts |
| [`charts.js`](../web/js/charts.js) | The charts, drawn as SVG from real query results (no chart library) |
| [`motion.js`](../web/js/motion.js) | Animation helpers; honours the "reduce motion" setting |

**Styling and assets:**

| File | What it is |
|---|---|
| [`css/app.css`](../web/css/app.css) | All component and page styles |
| [`css/tokens.css`](../web/css/tokens.css) | The design tokens: colours, spacing, type sizes. Every colour in `app.css` refers to one of these |
| [`css/fonts.css`](../web/css/fonts.css), `fonts/` | The three typefaces, served from the project itself (open-licence fonts), so the app looks the same offline |
| `vendor/motion-11.18.2.js` | The animation library (MIT licence), also served locally for offline use |
| `img/logo.svg`, `img/mark.svg`, `favicon.svg` | The SmartPark logo and icon |

## `docs/`: the documentation

| File | What it covers |
|---|---|
| [`database/ER_DIAGRAM.md`](database/ER_DIAGRAM.md) | **The ER diagrams**: Chen notation with a key to every shape, plus the crow's-foot version |
| [`database/RELATIONAL_SCHEMA.md`](database/RELATIONAL_SCHEMA.md) | **The relational schema**: all 17 relations with keys, every foreign key and its delete rule, candidate keys, and the order tables must be created in |
| [`database/NORMALIZATION.md`](database/NORMALIZATION.md) | The functional dependencies and the step-by-step derivation to Third Normal Form |
| [`database/DATA_DICTIONARY.md`](database/DATA_DICTIONARY.md) | Every table and column with its type, constraints and description (generated from the database) |
| [`database/queries.sql`](database/queries.sql) | 18 demonstration queries: joins, subqueries, aggregation, window functions, JSONB, views. Run with `psql -f` |
| `database/er/` | The diagram images (PNG for reading, SVG for zooming) |
| [`TESTING.md`](TESTING.md) | The captured output of every test suite |
| [`API.md`](API.md) | Every endpoint, who may call it, what it runs |
| [`DEMO_GUIDE.md`](DEMO_GUIDE.md) | A ten-minute walkthrough of the working system |
| [`REVIEW_MAPPING.md`](REVIEW_MAPPING.md) | Each line of the project statement and rubric, mapped to the file that satisfies it |
| [`DESIGN.md`](DESIGN.md) | The visual design: the idea behind the interface, bay states, interaction rules |
| [`CHANGES.md`](CHANGES.md) | What was built, changed and fixed, migration by migration |
| `screens/` | 25 screenshots of the running system, used in the README and the report |

## `tests/`: the automated checks

| File | What it checks |
|---|---|
| [`e2e_smoke.py`](../tests/e2e_smoke.py) | A full day's flow through the real API: sign in, reserve, arrive, depart, bill, pay, every report, and who may do what (40 checks) |
| [`test_api.py`](../tests/test_api.py) | 18 pytest tests against a separate test database: customer and vehicle CRUD, ownership, bay servicing, payments, scoping |
| [`page_smoke.py`](../tests/page_smoke.py) | Loads every page in a real browser and fails on any console error or failed request |
| [`a11y_components.py`](../tests/a11y_components.py), [`a11y_keyboard.py`](../tests/a11y_keyboard.py), [`a11y_contrast.py`](../tests/a11y_contrast.py) | Keyboard use, dialogs, tabs and text contrast |
| [`check_imports.py`](../tests/check_imports.py) | Every JavaScript import resolves to something that exists |
| [`gen_schema_docs.py`](../tests/gen_schema_docs.py) | **Generates the relational schema document and every ER diagram from the live database** |
| [`gen_data_dictionary.py`](../tests/gen_data_dictionary.py) | Generates the data dictionary from the live database |
| [`gen_testing_doc.py`](../tests/gen_testing_doc.py) | Runs every suite and writes `docs/TESTING.md` from the real output |
| [`capture_screens.py`](../tests/capture_screens.py) | Retakes the screenshots in `docs/screens/` |

## `Project-Report/`

The written project report as PDF and Word.

---

## Suggested order for a walkthrough

1. **README**: the problem and the architecture picture.
2. **ER diagram** ([`ER_DIAGRAM.md`](database/ER_DIAGRAM.md)): start with the key, then the overview, then one module.
3. **Relational schema** ([`RELATIONAL_SCHEMA.md`](database/RELATIONAL_SCHEMA.md)) and **normalization** ([`NORMALIZATION.md`](database/NORMALIZATION.md)).
4. **Backend**: [`db/schema_snapshot.sql`](../db/schema_snapshot.sql) for the whole schema, then [`006_gate_transactions.sql`](../db/migrations/006_gate_transactions.sql) for the locking transaction.
5. **Proof**: [`TESTING.md`](TESTING.md), then run [`constraint_tests.sql`](../db/tests/constraint_tests.sql) live.
6. **The running system**: follow [`DEMO_GUIDE.md`](DEMO_GUIDE.md).
