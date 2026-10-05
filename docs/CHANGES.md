# Change log — what was created, modified and archived

A one-line reason per file, and every migration with its purpose. Written for
the handoff; the substance is in [REVIEW_MAPPING.md](REVIEW_MAPPING.md).

---

## The decision that shaped everything else

The project as inherited was a **static HTML + Firebase Firestore** app, not the
TanStack Start + Supabase stack the brief assumed. Firestore is a NoSQL document
store: no schema, no foreign keys, no `CHECK`, no joins, no subqueries, no
views, no normal forms. The graded statement requires *"MySQL, PostgreSQL or
Oracle … normalized up to Third Normal Form"*, so Review 2 was almost entirely
un-scoreable on the existing backend.

The storage engine was therefore replaced with **PostgreSQL 17** (already
installed and running on this machine) and a **Python/FastAPI** layer added —
the statement asks for "a small front-end application developed using Java or
Python". Route paths, page structure and the domain model were preserved.

Nothing was deleted. The Firebase prototype is archived intact in
`legacy-firebase/` and is not referenced by any shipped file.

---

## Migrations applied

| Migration | Purpose |
|---|---|
| `001_extensions_roles_enums.sql` | `btree_gist` (needed for the exclusion constraints) and `citext`; the three PostgreSQL roles RLS is written against; six enumerated types |
| `002_core_tables.sql` | `app_user`, `facility`, `floor`, `zone`, `vehicle_type`, `customer` — the structural spine |
| `003_slot_vehicle_tariff.sql` | `slot`, `vehicle`, `tariff`; the two composite unique keys behind business rule 2; `ex_tariff_no_overlap` |
| `004_operations.sql` | `pass_type`, `parking_pass`, `reservation`, `parking_session`, `bill`, `payment`, `violation`. **Business rules 1–4 land here** |
| `005_functions.sql` | `fn_calculate_charge` (**business rule 5**), `fn_applicable_tariff`, the trigger that overwrites client-supplied bill amounts, the trigger that derives bill status from payments |
| `006_gate_transactions.sql` | `fn_allocate_slot` with `SELECT … FOR UPDATE SKIP LOCKED`, `fn_gate_entry`, `fn_gate_exit`, `fn_expire_stale_reservations` |
| `007_views.sql` | The seven report views, all `WITH (security_invoker = true)` |
| `008_indexes.sql` | 15 indexes, each `COMMENT`ed with the query it serves |
| `009_rls.sql` | RLS enabled on 9 tables; 26 policies; the identity helper functions; table and function grants |
| `010_seed.sql` | Facilities, floors, zones, 134 slots, tariffs, pass products, staff and customer logins, 35 customers, 50 vehicles |
| `011_seed_history.sql` | ~1,600 sessions over 30 days on a realistic arrival curve, bills, payments, reservations, passes, violations, then `ANALYZE` |
| `012_column_comments.sql` | `COMMENT ON COLUMN` for every significant column — the source of the Description column in the generated data dictionary |
| `013_integrity_service_audit.sql` | Ownership FKs for bookings and passes; `reservation.vehicle_type_id` with the rule-2 composite FKs; `slot.service_note` and `fn_set_slot_service`; the `audit_log` table and `trg_audit` on ten tables; `v_recent_activity`; operator-scoped payment and violation policies |
| `014_supabase_hardening.sql` | Revokes the default privileges Supabase gives its `anon`/`authenticated` roles; no-op on a plain PostgreSQL |
| `015_customer_email_shape.sql` | `ck_customer_email_shape` |
| `016_payment_within_balance.sql` | `trg_payment_within_balance`: no payment beyond what is owed, no payment on a waived bill |
| `017_zero_bill_is_paid.sql` | A ₹0 bill (free period or pass) is settled automatically instead of sitting as "unpaid" |
| `018_audit_and_rule_comments.sql` | Comments for the objects added in 013–016, for the data dictionary |

All are idempotent enough to replay on a fresh database and are applied in
filename order by `setup.sh`.

---

## Files created

### Database
| File | Why |
|---|---|
| `db/migrations/001`–`012` | The schema, constraints, functions, views, indexes, RLS and seed |
| `db/tests/constraint_tests.sql` | 16 deliberate rule violations, each expected to be refused |
| `db/tests/rls_tests.sql` | 9 checks that the policies restrict and fail closed |

### Application
| File | Why |
|---|---|
| `api/config.py` | Environment configuration with local defaults |
| `api/db.py` | Connection pool; declares the caller's identity per transaction so RLS applies |
| `api/auth.py` | bcrypt hashing, JWT bearer tokens, role guards |
| `api/errors.py` | Maps PostgreSQL constraint names to messages an operator can act on |
| `api/main.py` | Routes — thin wrappers over the database functions and views |

### Interface
| File | Why |
|---|---|
| `web/css/tokens.css` | The whole design system as variables — no component holds a raw hex |
| `web/css/app.css` | Layout, components, the floor-plan slot map, responsive rules |
| `web/js/motion.js` | The animation layer; resolves reduced-motion once for the whole app |
| `web/js/api.js` | The single data client |
| `web/js/ui.js` | Shell, icons, and the four async states every list needs |
| `web/js/charts.js` | Inline SVG charts built from tokens — no charting library |
| `web/index.html` + `web/js/*.js` | Ten screens: sign-in, dashboard, slot map, gate, reservations, passes, billing, reports, customers, settings |

### Tests and tooling
| File | Why |
|---|---|
| `tests/e2e_smoke.py` | 39-check end-to-end run over HTTP; repeatable |
| `tests/gen_data_dictionary.py` | Generates the data dictionary from the live schema so it cannot drift |
| `tests/gen_testing_doc.py` | Generates `docs/TESTING.md` from real captured test output |
| `tests/capture_screens.py` | Captures the 18 output screens via the installed Chrome |
| `setup.sh` | One-command build, for a reader who would rather not run twelve |
| `requirements.txt` | Pinned to the versions actually tested; verified with a clean install |

### Documentation
`README.md`, `docs/REVIEW_MAPPING.md`, `docs/TESTING.md`,
`docs/database/ER_DIAGRAM.md`, `docs/database/NORMALIZATION.md`,
`docs/database/DATA_DICTIONARY.md`, `docs/database/queries.sql`,
`docs/screens/` (18 PNGs), and this file.

---

## Files archived, not deleted

Everything below moved to `legacy-firebase/` and is referenced by nothing:

`index.html`, `dashboard.html`, `slots.html`, `gate.html`, `reservations.html`,
`passes.html`, `billing.html`, `reports.html`, `customers.html`,
`settings.html`, `css/` (3 files), `js/` (13 files), `firebase.json`,
`.firebaserc`, `firestore.rules`, `README.old.md`.

There was no git repository at the time, so deleting would have been
unrecoverable. Since the merge the folder is excluded from the repository by
`.gitignore`: it stays on the original machine for reference and is not part of
the submission.

---

## Defects found in the inherited code

Recorded because several were invisible until the code was actually run.

| # | Defect | Consequence |
|---|---|---|
| 1 | `checkAuth` imported from `utils.js` by `billing.js`, `passes.js`, `reservations.js`; never exported | Hard ES-module load error — **three pages never executed a line** |
| 2 | `animateCounter(element, …)` called with a string ID at all 12 sites | `TypeError` on every stat tile |
| 3 | `dashboard.js` hardcoded revenue `12450` and a seven-day trend | Fabricated figures on screen |
| 4 | `gate.js` hardcoded `rate = 50` | Billing ignored the tariff table entirely |
| 5 | Seed wrote `{perHour, perDay}`; billing read `{ratePerHour, ratePerDay, maxDaily}` | Tariff table rendered `undefined` |
| 6 | Pass check was a `setTimeout` always returning "Valid Pass Found" | Pass validation was theatre |
| 7 | Revenue, usage, violations and free-slots reports were empty stubs | Four of five reports did nothing |
| 8 | Read-then-write slot allocation with no transaction | Documented race, with an alert saying so |
| 9 | `allow read, write: if request.auth != null` | Any signed-in user could read every customer's data |
| 10 | 60 slots, 1 customer, 0 sessions | Charts had nothing to plot |

---

## Defects found and fixed in the new code during verification

Recorded because they show what the tests actually caught.

| Found by | Defect | Fix |
|---|---|---|
| Browser click-through | `fn_gate_entry` — the OUT parameter `slot_id` shadowed `slot.slot_id` in an unqualified predicate. Only fired on the **reserved-bay branch**, which the API test never took | Aliased the table; assigned OUT parameters only at the end from locals. Added a reserved-bay case to `e2e_smoke.py` so it cannot regress |
| End-to-end test | `fn_gate_exit` — same class of bug on `bill_id` | Same fix |
| End-to-end test | `SELECT … FOR UPDATE` needs `UPDATE` privilege, which operators must not hold on `slot` | Gate functions became `SECURITY DEFINER` with a pinned `search_path`, plus an explicit facility guard inside — since RLS no longer applies in that body |
| Endpoint timing | Dashboard took **82 seconds**. `fn_current_role()` was `SECURITY DEFINER`, so PostgreSQL could not inline it and called it per row inside every RLS filter | Rewrote it to read `current_user` — no table access, inlinable, and more secure, since a database role cannot be spoofed by an application setting |
| Endpoint timing | Still 2 s after that: a freshly built database has no statistics, so the planner used defaults (750 rows for every table) and chose nested loops | `ANALYZE` appended to the seed. 82 s → 38 ms |
| Seed inspection | `random()` in a non-correlated `LATERAL` is folded to one constant for the whole statement, so every bill took the same payment branch | Replaced with a per-row hash of `bill_id`; also reproducible |
| Query review | Q2 and Q7 returned zero rows — correct, but a `LEFT JOIN` showing nothing does not demonstrate a `LEFT JOIN` | Seeded three never-parked customers; changed Q7 to a question the data can answer |
| `EXPLAIN` review | The plate lookup plans as a sequential scan, because `vehicle` is ~50 rows in one page | Left the plan alone and documented why, adding Q16b (forced index scan) and Q16c (a table where the index wins unprompted) |
| Contrast audit | White on `--accent` measures 3.84:1 — below AA for button labels | Added text-safe token variants; fills keep the brief's specified values |
| Design audit | 7 raw hex values left in `app.css` | Promoted to `--state-*-line` tokens; component files now hold zero |


---

## v2 — the control-room redesign

The interface was recomposed, not restyled. Full rationale in
[DESIGN.md](DESIGN.md); this is the file-level record.

### Rewritten
| File | Change |
|---|---|
| `web/css/tokens.css` | New system: cool concrete grounds, charcoal ink, operational teal, safety amber, restrained coral. 93 tokens, each contrast-measured. Tight radii (3-6px), one shadow level, ink-on-dark set |
| `web/css/app.css` | Rewritten around the architectural grid: instrument rail, command strip, recessed floor plate, the four-channel bay system, and the rest of the product restyled in the same language |
| `web/js/motion.js` | 15 helpers, all honouring one reduced-motion resolution: entrances, budgeted stagger, spring press feedback, counters, panels, bay-state diffing, nav indicator, progressive chart draw, live list insertion, gauge fill |
| `web/js/dashboard.js` | Recomposed: command strip, dominant floor plate, hover cards, level markers, state filter, bay search, live polling paused on hidden tabs |
| `web/js/charts.js` | Progressive draw by `stroke-dashoffset` plus area wipe; pointer AND keyboard hover readout |
| `web/index.html` | Live SVG facility plan as backdrop, architectural title block, demonstration accounts as credential chips |
| `web/js/ui.js` | Sliding nav indicator, shared `bayHTML` / `zoneHTML` / `groupByZone` so the map is identical everywhere |

### Added
| File | Purpose |
|---|---|
| `web/js/bay-sheet.js` | Bay detail panel that opens beside the map, focus-trapped, returning focus by slot id |
| `docs/DESIGN.md` | Design concept and interaction logic |
| `tests/a11y_contrast.py` | Contrast as rendered, composing ancestor opacity |
| `tests/a11y_keyboard.py` | Tab order, focus ring, bay operability, focus return |
| `tests/page_smoke.py` | All pages render real content; catches `pageerror` and blank renders |
| `tests/check_imports.py` | Every named ES-module import resolves |

### Defects the v2 audits caught
| Found by | Defect |
|---|---|
| Contrast audit | `--ink-3` (3.05:1, documented decoration-only) carrying readable text in 5 places, including the vehicle type on every bay — 195 elements below AA |
| Hardened contrast audit | `opacity: .75` on text lowered effective contrast below AA while the first audit read it as passing |
| Page smoke, hardened | `gate.js` imported `flashSlot` after the rename to `flashBay` — a blank page with no console output, because a module `SyntaxError` is a `pageerror`, not a console message |
| Keyboard audit | Closing the bay panel refreshed the map, so focus returned to a detached node |
| Token audit | 90 references to v1 token names that no longer resolved, across 8 page scripts |
| Class audit | 21 orphaned class names after the rename — the reason the gate page had no layout |

---

## v3 — merge with the Codex version, and submission hardening

A second implementation of the same brief (React + MySQL, built with Codex) was
reviewed feature by feature. This PostgreSQL build stayed the primary codebase;
nothing was copied across wholesale. Where the other version had a feature this
one lacked, it was re-implemented here on the existing database-first design.

**Database (013–018).** Ownership enforced by composite foreign keys; rule 2
enforced at booking time as well as at entry; bay servicing as a locked
function; a trigger-written audit trail; the live activity view; operator
scoping fixed for payments and violations (an operator at one site could
previously read the other site's payments); overpayment refused by a trigger;
₹0 bills settled automatically; Supabase's default API grants revoked.

**API.** Plain-English errors that also name the rule that refused the request;
customer and vehicle editing and removal; bay servicing; payments ledger;
activity feed; audit trail; vehicle history report; server-side bill search; a
wrong password no longer reports an expired session; the API refuses to start
on Vercel without a real signing secret.

**Interface.** New logo and favicon; shared components (sortable, searchable,
exportable data tables, action menus, tabs, dialogs with focus trapping,
keyboard shortcuts, breadcrumbs, a collapsible sidebar); every page rebuilt on
them; an invoice view; a payments ledger; an audit trail; a bay sheet with
servicing; tables that become cards in narrow panels.

**Defects found and fixed during final verification.**

| Defect | Fix |
|---|---|
| Revenue charts showed only the area fill: the line never drew, because Motion animated `stroke-dashoffset` as an SVG attribute that the inline style outranked | `drawPath` tweens the number and writes the style |
| The sidebar's active marker sat about 50 px below the selected item | The marker had no `top: 0`, so its offset was added to its in-flow position |
| Sign-in submitted natively (password in the URL) if pressed before the page's module had loaded | Button disabled and native submit blocked until the handler is attached |
| The departure dialog offered "Record payment" on a ₹0 bill the database had already settled | Only "Done" for a zero bill, with the reason |
| The audit trail showed raw ISO timestamps | Formatted like every other date in the app |
| If the animation CDN was unreachable, every page failed to load | Motion is imported dynamically; without it the app runs without animation |

**Tests added.** `db/tests/lifecycle_tests.sql` (reservation expiry, overstay,
pass cover and pass expiry, derived billing); constraint tests 16–24; RLS tests
J–L; `tests/test_api.py` (18 pytest cases); browser checks for every page and
for the shared components. `docs/TESTING.md` is generated from a real run of
all of them.

