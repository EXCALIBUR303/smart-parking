# Testing

Smart Parking Lot Allocation & Billing System — DBMS PBL Project 20.

Every result below is captured output from a real run, not a description
of what the code is expected to do. Regenerate the whole document with:

```bash
./.venv/bin/python tests/gen_testing_doc.py
```

| Suite | What it proves | Result |
|---|---|---|
| Constraint tests | Each business rule rejects its violation | **15 of 16 attempts refused by the database**; the remaining one is accepted and silently corrected, which is TEST 8's point |
| RLS tests | Policies restrict rows, and fail closed | **Pass** |
| End-to-end smoke | Sign-in → reserve → entry → exit → bill → payment → reports | **39 checks, 0 failures** |

---

## 1. Constraint tests — trying to break each business rule

```bash
psql -d smartpark -f db/tests/constraint_tests.sql
```

Each block deliberately violates one rule inside its own transaction,
which is then rolled back. The error text is exactly what PostgreSQL
returned. A constraint that has never been tested to failure is one you
cannot defend in a viva.

### TEST 1 — BUSINESS RULE 1 - one active vehicle per slot

**Attempt.** open a second session on a slot that is already occupied.

**Expected.** unique violation on uq_active_session_slot

**PostgreSQL returned:**

```
ERROR:  duplicate key value violates unique constraint "uq_active_session_slot"
DETAIL:  Key (slot_id)=(97) already exists.
```

**Result: REFUSED by the database.**

### TEST 2 — BUSINESS RULE 1 (mirror) - one active slot per vehicle

**Attempt.** park an already-parked vehicle in a second free bay.

**Expected.** unique violation on uq_active_session_vehicle

**PostgreSQL returned:**

```
ERROR:  duplicate key value violates unique constraint "uq_active_session_vehicle"
DETAIL:  Key (vehicle_id)=(36) already exists.
```

**Result: REFUSED by the database.**

### TEST 3 — BUSINESS RULE 2 - slot / vehicle-type match

**Attempt.** put a CAR into a BIKE bay.

**Expected.** foreign key violation on fk_session_slot_type_match (the composite key (slot_id, CAR) does not exist in slot)

**PostgreSQL returned:**

```
ERROR:  insert or update on table "parking_session" violates foreign key constraint "fk_session_slot_type_match"
DETAIL:  Key (slot_id, vehicle_type_id)=(1, 2) is not present in table "slot".
```

**Result: REFUSED by the database.**

### TEST 3b — BUSINESS RULE 2 - lying about the vehicle type

**Attempt.** claim a CAR is a BIKE so the slot type appears to match.

**Expected.** foreign key violation on fk_session_vehicle_type_match (the composite key (vehicle_id, BIKE) does not exist in vehicle)

**PostgreSQL returned:**

```
ERROR:  insert or update on table "parking_session" violates foreign key constraint "fk_session_vehicle_type_match"
DETAIL:  Key (vehicle_id, vehicle_type_id)=(1, 1) is not present in table "vehicle".
```

**Result: REFUSED by the database.**

### TEST 4 — BUSINESS RULE 3 - exit after entry

**Attempt.** stamp an exit one hour BEFORE the entry.

**Expected.** check violation on ck_session_exit_after_entry

**PostgreSQL returned:**

```
ERROR:  new row for relation "parking_session" violates check constraint "ck_session_exit_after_entry"
DETAIL:  Failing row contains (1601, TK-EB0C615F, 97, 36, 4, 2026-09-13 19:24:56.812514+05:30, 2026-09-13 18:24:56.812514+05:30, null, null, 4, null).
```

**Result: REFUSED by the database.**

### TEST 5 — BUSINESS RULE 4 - reservation window must be forward

**Attempt.** reserve until BEFORE the reservation starts.

**Expected.** check violation on ck_reservation_window

**PostgreSQL returned:**

```
ERROR:  new row for relation "reservation" violates check constraint "ck_reservation_window"
DETAIL:  Failing row contains (37, 1, 2, 1, 2026-09-14 02:57:13.327374+05:30, 2026-09-14 00:57:13.327374+05:30, held, 2026-09-13 22:57:13.327374+05:30).
```

**Result: REFUSED by the database.**

### TEST 6 — BUSINESS RULE 4 - two live holds may not overlap

**Attempt.** book a slot for a window that overlaps a live hold.

**Expected.** exclusion violation on ex_reservation_no_overlap

**PostgreSQL returned:**

```
ERROR:  conflicting key value violates exclusion constraint "ex_reservation_no_overlap"
DETAIL:  Key (slot_id, tstzrange(reserved_from, reserved_until))=(4, ["2026-09-21 15:35:03.807066+05:30","2026-09-21 17:35:03.807066+05:30")) conflicts with existing key (slot_id, tstzrange(reserved_from, reserved_until))=(4, ["2026-09-21 15:05:03.807066+05:30","2026-09-21 17:05:03.807066+05:30")).
```

**Result: REFUSED by the database.**

### TEST 7 — BUSINESS RULE 5 - a bill amount may not be negative

**Attempt.** write a bill with a negative base amount.

**Expected.** check violation on ck_bill_base_non_negative (forced past the amount-enforcing trigger with a direct UPDATE)

**PostgreSQL returned:**

```
ERROR:  new row for relation "bill" violates check constraint "ck_bill_base_non_negative"
DETAIL:  Failing row contains (3, 3, 2, 106, -500.00, 4.50, -495.50, unpaid, 2026-08-14 10:20:00+05:30).
```

**Result: REFUSED by the database.**

### TEST 8 — BUSINESS RULE 5 - a client cannot dictate the charge

**Attempt.** insert a bill claiming the parking cost 1 rupee.

**Expected.** NO error. The row is accepted but trg_bill_enforce_amounts silently replaces the amount with fn_calculate_charge output. The printed comparison is the proof.

**PostgreSQL returned:**

```
     source      |  base  |  tax  | total
 client claimed  |   1.00 |  0.00 |   1.00
 database stored | 115.00 | 20.70 | 135.70
```

**Result: accepted, then silently corrected by the trigger — which is exactly what this test exists to show.**

### TEST 9 — Referential integrity - a session needs a real slot

**Attempt.** reference a slot_id that does not exist.

**Expected.** foreign key violation

**PostgreSQL returned:**

```
ERROR:  insert or update on table "parking_session" violates foreign key constraint "fk_session_slot_type_match"
DETAIL:  Key (slot_id, vehicle_type_id)=(999999, 2) is not present in table "slot".
```

**Result: REFUSED by the database.**

### TEST 10 — Input validation - plate number format

**Attempt.** register a vehicle with the plate "HELLO".

**Expected.** check violation on ck_vehicle_plate_shape

**PostgreSQL returned:**

```
ERROR:  new row for relation "vehicle" violates check constraint "ck_vehicle_plate_shape"
DETAIL:  Failing row contains (53, 1, HELLO, 1, null, null, null, 2026-09-13 22:57:13.338545+05:30).
```

**Result: REFUSED by the database.**

### TEST 11 — Input validation - duplicate plate number

**Attempt.** register a plate that already exists.

**Expected.** unique violation on vehicle_plate_number_key

**PostgreSQL returned:**

```
ERROR:  duplicate key value violates unique constraint "vehicle_plate_number_key"
DETAIL:  Key (plate_number)=(TS09AB1234) already exists.
```

**Result: REFUSED by the database.**

### TEST 12 — Payment integrity - a payment must be positive

**Attempt.** record a payment of zero.

**Expected.** check violation on ck_payment_amount_positive

**PostgreSQL returned:**

```
ERROR:  new row for relation "payment" violates check constraint "ck_payment_amount_positive"
DETAIL:  Failing row contains (1388, 3, 0.00, cash, null, 2026-09-13 22:57:13.339396+05:30, null).
```

**Result: REFUSED by the database.**

### TEST 13 — Tariff integrity - overlapping price lists

**Attempt.** open a second tariff for a facility/type already priced.

**Expected.** exclusion violation on ex_tariff_no_overlap

**PostgreSQL returned:**

```
ERROR:  conflicting key value violates exclusion constraint "ex_tariff_no_overlap"
DETAIL:  Key (facility_id, vehicle_type_id, tstzrange(effective_from, effective_to))=(1, 1, ["2026-09-13 22:57:13.339763+05:30",)) conflicts with existing key (facility_id, vehicle_type_id, tstzrange(effective_from, effective_to))=(1, 1, ["2026-06-15 22:56:56.775443+05:30",)).
```

**Result: REFUSED by the database.**

### TEST 14 — Operator scoping - an operator must have a facility

**Attempt.** create an operator with no facility_id.

**Expected.** check violation on ck_app_user_operator_has_facility

**PostgreSQL returned:**

```
ERROR:  new row for relation "app_user" violates check constraint "ck_app_user_operator_has_facility"
DETAIL:  Failing row contains (10, rogue.operator@smartpark.in, x, Rogue Operator, operator, null, t, 2026-09-13 22:57:13.340093+05:30).
```

**Result: REFUSED by the database.**

### TEST 15 — Pass integrity - two live passes on one vehicle

**Attempt.** sell a second overlapping pass for the same vehicle/facility.

**Expected.** exclusion violation on ex_pass_no_overlap

**PostgreSQL returned:**

```
ERROR:  conflicting key value violates exclusion constraint "ex_pass_no_overlap"
DETAIL:  Key (vehicle_id, facility_id, tstzrange(valid_from, valid_to))=(2, 1, ["2026-09-09 00:00:00+05:30","2026-10-09 00:00:00+05:30")) conflicts with existing key (vehicle_id, facility_id, tstzrange(valid_from, valid_to))=(2, 1, ["2026-09-08 00:00:00+05:30","2026-10-08 00:00:00+05:30")).
```

**Result: REFUSED by the database.**

---

## 2. Row-level security — proving the policies restrict

```bash
psql -d smartpark -f db/tests/rls_tests.sql
```

PostgreSQL exempts a table's owner from its own RLS policies unless
`FORCE ROW LEVEL SECURITY` is set, so the API never queries as the owner.
It issues `SET LOCAL app.current_user_id` and `SET LOCAL ROLE` per
request, and these tests do the same — they exercise the policies exactly
as real traffic does.

### Visibility by role

| Acting as | Customers | Vehicles | Bills | Sessions |
|---|--:|--:|--:|--:|
| Table owner (RLS bypassed by ownership) | 32 | 47 | 1603 | — |
| Customer 1 — Rahul Sharma | 1 | 3 | 104 | 104 |
| **No identity set** | **0** | **0** | **0** | — |

The last row is the important one. With `app.current_user_id` unset,
`fn_current_user_id()` returns NULL, every policy evaluates false, and the
caller sees nothing. The system fails **closed**.

### Two customers see disjoint data

| Rahul Sharma (user 5) sees | Priya Nair (user 6) sees |
|---|---|
| `TS09AB1234` | `TS10CD5678` |
| `TS09EF4444` | `TS11GH5555` |
| `TS09XY7788` |  |

Plates in common: **0**. Rahul querying
`customer_id = 2` directly returns 0 rows — the row is invisible
rather than forbidden, which is correct: an error would itself
disclose that the row exists.

### Writes are restricted too

| Attempt | Result |
|---|---|
| Customer writes a vehicle onto another customer | `ERROR:  new row violates row-level security policy for table "vehicle"` |
| Customer records a payment against their own bill | `ERROR:  permission denied for table payment` |

### Operators are scoped to their own facility

```
Rohit  (operator, facility 1):
           1 |                 1215
Imran  (operator, facility 2):
           2 |                  407
```

Each operator's query returns rows for their own site only — the grouping
proves it, since a leak would show a second facility_id.

### Views honour RLS (`security_invoker = true`)

| Query | As customer 1 | As admin |
|---|--:|--:|
| `SELECT count(*) FROM v_session_duration` | 104 | 1622 |
| `SELECT count(*) FROM v_violations` | 3 | 31 |

Without `security_invoker = true` a view executes as its owner and both
columns above would read the same. That is the classic way an RLS policy
is bypassed by the convenience layer built on top of it.

---

## 3. End-to-end smoke test

```bash
./.venv/bin/python tests/e2e_smoke.py
```

Drives the running API over HTTP: sign in, search a bay, register a
customer and vehicle, reserve, gate entry onto both an allocated and a
reserved bay, gate exit, bill, payment, every report, and the
authorisation boundaries. Safe to run repeatedly.

```
========================================================================
END-TO-END SMOKE TEST
========================================================================
1. Sign in
  [PASS] operator signs in  -> role=operator
  [PASS] customer signs in  -> customer
  [PASS] wrong password rejected  -> Email or password is incorrect.
  [PASS] no token rejected  -> Sign in to continue.
2. Search a free slot
  [PASS] free-slot search returns rows  -> 46 free car bays
3. Register a customer and vehicle
  [PASS] create customer  -> {'customer_id': 33, 'full_name': 'E2E Test Driver', 'phone': '9225714999', 'email': None}
  [PASS] create vehicle  -> {'vehicle_id': 56, 'plate_number': 'TS01ZZ5714'}
4. Validation is enforced
  [PASS] bad plate rejected  -> That does not look like a valid registration number. Use the format TS09AB1234.
  [PASS] duplicate plate rejected  -> A vehicle with that registration number is already on file.
5. Reserve a slot
  [PASS] create reservation  -> {'reservation_id': 39, 'status': 'held'}
  [PASS] overlapping reservation rejected  -> That slot is already reserved for an overlapping period. Pick another slot or time.
6. Gate entry
  [PASS] gate entry allocates a slot  -> ticket TK-25C6C423 -> slot B-A-04
  [PASS] double entry rejected  -> Vehicle TS01ZZ5714 is already parked in bay B-A-04 at SmartPark Central
  [PASS] unknown plate rejected  -> No vehicle is registered with plate XX99XX9999
6b. Arrival onto a RESERVED bay
  [PASS] arrival honours the reservation  -> AP39ST5566 -> reserved bay B-A-12 (held: B-A-12)
7. Look up the open session
  [PASS] lookup finds the session  -> running charge Rs 0.0
8. Gate exit raises a bill
  [PASS] gate exit succeeds  -> bill 1607 total Rs 0.0
  [PASS] bill total = base + tax  -> 0.0 + 0.0 = 0.0
  [PASS] second exit rejected  -> No open parking session found for "TK-25C6C423"
8b. A chargeable exit (a vehicle parked for hours, not minutes)
  [PASS] found a chargeable open session  -> KA03QR6060
  [PASS] long session has a running charge  -> 496 min -> Rs 240.0
  [PASS] chargeable exit bills a real amount  -> base Rs 240.0 + tax Rs 43.2 = Rs 283.2
  [PASS] quoted charge matches the bill  -> quoted 240.0 vs billed 240.0
  [PASS] half payment marks the bill partly_paid  -> partly_paid
9. Record a payment
  [PASS] bill detail loads  -> status unpaid
  [PASS] payment recorded  -> bill now paid
  [PASS] bill marked paid by trigger  -> paid
  [PASS] negative payment rejected  -> rejected
10. Every report renders with real data
  [PASS] report: occupancy  -> 12 rows
  [PASS] report: peak hours  -> 18 rows
  [PASS] report: revenue  -> 36 rows
  [PASS] report: duration  -> 5 rows
  [PASS] report: pass usage  -> 27 rows
  [PASS] report: violations  -> 35 rows
  [PASS] report: free slots  -> 28 rows
11. Authorisation holds through the API
  [PASS] customer cannot work the gate  -> This action is restricted to staff.
  [PASS] customer cannot record payments  -> This action is restricted to staff.
  [PASS] customer sees fewer vehicles than admin  -> 3 vs 48
  [PASS] operator cannot change tariffs  -> This action is restricted to administrators.
========================================================================
ALL END-TO-END CHECKS PASSED
========================================================================
```

---

## 4. Validation and error handling

Client-side validation exists for responsiveness; the database is the real
gate. The message a user sees is the mapped constraint message from
`api/errors.py`, keyed on the PostgreSQL constraint name.

| Where | Bad input | Caught by | Message shown to the user |
|---|---|---|---|
| Gate — arrival | `HELLO` as a registration | `ck_vehicle_plate_shape` | That does not look like a valid registration number. Use the format TS09AB1234. |
| Gate — arrival | A plate not on file | `fn_gate_entry` RAISE, SQLSTATE `no_data_found` | No vehicle is registered with plate XX99XX9999 |
| Gate — arrival | A vehicle already inside | `uq_active_session_vehicle` | Vehicle TS09AB1234 is already parked and has not exited |
| Gate — arrival | Facility full for that type | `fn_allocate_slot` returns NULL → RAISE | No free slot available for this vehicle type at facility 1 |
| Gate — arrival | Operator posted to another site | `fn_gate_entry` facility guard | You are posted to facility 2, not facility 1 |
| Gate — departure | Ticket with no open session | `fn_gate_exit` RAISE | No open parking session found for "TK-XXXXXXXX" |
| Reservations | End time before start | `ck_reservation_window` | The reservation must end after it starts. |
| Reservations | Bay already held for that window | `ex_reservation_no_overlap` | That slot is already reserved for an overlapping period. Pick another slot or time. |
| Passes | Second live pass, same vehicle and site | `ex_pass_no_overlap` | This vehicle already holds a pass covering those dates at this facility. |
| Billing | Payment of zero or less | `ck_payment_amount_positive` | A payment must be greater than zero. |
| Billing | Payment exceeding the balance | client-side check before submit | That is more than the ₹236.00 outstanding. |
| Customers | Phone that is not ten digits | `ck_customer_phone_shape` | Enter a 10 digit phone number with no spaces or country code. |
| Customers | Registration already on file | `vehicle_plate_number_key` | A vehicle with that registration number is already on file. |
| Customers | Removing a vehicle with history | `ON DELETE RESTRICT` | The database's own message, surfaced verbatim |
| Settings | Daily cap below the first-hour rate | `ck_tariff_cap_sane` | The daily cap cannot be lower than the first hour rate. |
| Settings | Second tariff for a priced facility/type | `ex_tariff_no_overlap` | A tariff is already in force for this facility and vehicle type. |
| Sign in | Wrong password | bcrypt verify fails | Email or password is incorrect. |
| Sign in | Unknown email | same message, deliberately | Email or password is incorrect. *(identical, so responses cannot be used to enumerate accounts)* |
| Any screen | Expired or missing token | `api/auth.py` | Your session has expired. Sign in again. *(and a redirect to sign-in)* |
| Any screen | API not running | fetch throws | Cannot reach the server. Check that the API is running. |

---

## 5. Interface checks

| Check | Method | Result |
|---|---|---|
| Console and network | Every page loaded, console and network log read | No errors, no failed requests |
| Response time | All API endpoints timed | Dashboard 162 ms, slot map 24 ms, billing 214 ms, revenue 274 ms — inside the 400 ms Doherty threshold |
| Responsive 1280 px | Browser at 1280×900 | Two-column dashboard, full floor map |
| Responsive 768 px | Browser at 768×1024 | Sidebar collapses to a menu; `documentElement.scrollWidth === innerWidth`, so no horizontal scroll |
| Responsive 375 px | Browser at 375×812 | Four bays across, state words legible; no horizontal scroll |
| Reduced motion | `motion.js` re-imported with the preference stubbed, every helper asserted | All honour it: entrance lands at final state, list reveals at once, hover/tap binds no listeners, counters write the final value immediately, slot flash is a no-op |
| Colour is never the only cue | Inspected every state indicator | Each bay carries a word, an icon and a spine; out-of-service adds a 45° hatch; badge markers differ in shape (circle / square / diamond) |
| Keyboard | Tabbed through forms and the modal | Visible focus ring in `--accent`; modal traps focus, Escape closes, focus returns to the trigger |
| Design tokens | `grep -c '#[0-9A-Fa-f]\{6\}' web/css/app.css` | **0** — every colour in every component is a token |

---

## 6. Contrast measurements

Computed, not eyeballed. `--ink-muted` on `--canvas` is the pairing the
brief flags as most likely to fail; it passes at 5.17:1.

| Pairing | Ratio | AA normal (4.5) | AA large (3.0) |
|---|--:|:--:|:--:|
| `--ink` on `--canvas` | 13.70 | PASS | PASS |
| `--ink` on `--surface` | 14.82 | PASS | PASS |
| **`--ink-muted` on `--canvas`** | **5.17** | **PASS** | PASS |
| `--ink-muted` on `--surface` | 5.59 | PASS | PASS |
| `--ink-muted` on `--surface-sunk` | 4.86 | PASS | PASS |
| `--accent-ink` on `--canvas` | 4.52 | PASS | PASS |
| white on `--accent-solid` (buttons) | 4.58 | PASS | PASS |
| `--state-free-ink` on `--surface` | 4.88 | PASS | PASS |
| `--state-held-ink` on `--surface` | 4.90 | PASS | PASS |
| `--state-full-ink` on `--surface` | 4.87 | PASS | PASS |
| `--state-off-ink` on `--surface` | 4.95 | PASS | PASS |
| `--accent` **fill** on `--surface` | 3.84 | n/a — fill | PASS |
| `--state-free` **fill** on `--surface` | 4.02 | n/a — fill | PASS |
| `--ink-subtle` on `--canvas` | 2.92 | FAIL — see note | FAIL |

**On the two that do not meet AA for normal text.**

The brief specifies `--accent: #3F8F84` and the four state colours as
*fills*. White text on `#3F8F84` measures 3.84:1 — fine for a swatch or a
3 px spine, short of AA for a button label. Rather than change the brand
colour, `tokens.css` adds text-safe counterparts (`--accent-solid`,
`--accent-ink`, `--state-*-ink`), each the same hue darkened until it
clears 4.5:1. Fills keep the specified values; anything carrying words
uses the darkened one.

`--ink-subtle` at 2.92:1 is **decoration only** — hairlines, the aisle
label on the floor plan, disabled glyphs. It is documented as such in
`web/css/tokens.css` and never carries text a user must read.
