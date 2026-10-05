# Data Dictionary

Smart Parking Lot Allocation & Billing System — DBMS PBL Project 20.

**Generated from the live schema** by `tests/gen_data_dictionary.py`, which
reads `information_schema` and `pg_catalog`. It is a report on the database
that exists, not a description maintained by hand — regenerate it after any
migration and it cannot drift.

PostgreSQL objects: **17 tables**, **33 CHECK constraints**, **36 foreign keys**, **3 exclusion constraints**, **59 indexes**, **6 enumerated types**.

---

## Enumerated types

| Type | Values |
|---|---|
| `bill_status` | 'unpaid', 'partly_paid', 'paid', 'waived' |
| `pass_status` | 'active', 'expired', 'cancelled' |
| `payment_method` | 'cash', 'card', 'upi', 'netbanking', 'pass', 'wallet' |
| `reservation_status` | 'held', 'confirmed', 'expired', 'cancelled', 'fulfilled' |
| `user_role` | 'admin', 'operator', 'customer' |
| `violation_type` | 'overstay', 'wrong_slot_type', 'no_valid_pass', 'unpaid_exit', 'reservation_no_show' |

---

## Tables

### `app_user`

Login identity and role. Drives every row-level security policy.

*Rows in the seeded database: 8. Row-level security: enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `user_id` | `bigint` | NOT NULL | — | Surrogate key. Supplied to the database each request as app.current_user_id, which every RLS policy reads. |
| 2 | `email` | `citext` | NOT NULL | — | Login identity. CITEXT, so case does not create a second account. |
| 3 | `password_hash` | `text` | NOT NULL | — | bcrypt hash, cost 12. No plaintext password is ever stored or logged. |
| 4 | `full_name` | `text` | NOT NULL | — |  |
| 5 | `role` | `user_role` | NOT NULL | `'customer'::user_role` | admin | operator | customer. The API also SET ROLEs into the matching database role, and fn_current_role() reads that rather than this column. |
| 6 | `facility_id` | `bigint` | nullable | — | Required for operators, forbidden for admins and customers (ck_app_user_operator_has_facility). |
| 7 | `is_active` | `boolean` | NOT NULL | `true` | FALSE blocks sign-in without deleting the audit trail on sessions and payments. |
| 8 | `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `app_user_pkey` | PRIMARY KEY | `PRIMARY KEY (user_id)` |  |
| `app_user_email_key` | UNIQUE | `UNIQUE (email)` |  |
| `fk_app_user_facility` | FOREIGN KEY | `FOREIGN KEY (facility_id) REFERENCES facility(facility_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `ck_app_user_email_shape` | CHECK | `CHECK ((email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'::citext))` |  |
| `ck_app_user_name_not_blank` | CHECK | `CHECK ((length(btrim(full_name)) > 0))` |  |
| `ck_app_user_operator_has_facility` | CHECK | `CHECK (((role = 'operator'::user_role) = (facility_id IS NOT NULL)))` |  |

**RLS policies:** `p_user_admin_all` (ALL), `p_user_self_read` (SELECT)


### `audit_log`

Append-only change history written by trigger. changes holds the full row for INSERT/DELETE and {column: {from, to}} for UPDATE.

*Rows in the seeded database: 11. Row-level security: not enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `audit_id` | `bigint` | NOT NULL | — | Surrogate key, in insertion order. |
| 2 | `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` | When the change was committed by the statement that made it. |
| 3 | `actor_user_id` | `bigint` | nullable | — | The signed-in user (app.current_user_id) who made the change. NULL for a direct database session; SET NULL if the user is later removed, so history survives. |
| 4 | `actor_role` | `user_role` | nullable | — | Role of the actor at the time, kept even if the user's role changes later. |
| 5 | `table_name` | `text` | NOT NULL | — | Table the changed row belongs to. |
| 6 | `row_id` | `bigint` | NOT NULL | — | Primary key of the changed row in table_name. |
| 7 | `action` | `text` | NOT NULL | — | INSERT, UPDATE or DELETE. |
| 8 | `changes` | `jsonb` | NOT NULL | — | INSERT/DELETE: the whole row. UPDATE: only the columns that changed, as {column: {from, to}}. |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `audit_log_pkey` | PRIMARY KEY | `PRIMARY KEY (audit_id)` |  |
| `fk_audit_actor` | FOREIGN KEY | `FOREIGN KEY (actor_user_id) REFERENCES app_user(user_id) ON UPDATE CASCADE ON DELETE SET NULL` |  |
| `ck_audit_action` | CHECK | `CHECK ((action = ANY (ARRAY['INSERT'::text, 'UPDATE'::text, 'DELETE'::text])))` | The three DML verbs only. |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_audit_occurred` | `public.audit_log USING btree (occurred_at DESC)` |  |
| `ix_audit_row` | `public.audit_log USING btree (table_name, row_id)` |  |


### `bill`

One bill per completed session. base_amount is overwritten from fn_calculate_charge by trigger; total_amount is generated.

*Rows in the seeded database: 1611. Row-level security: enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `bill_id` | `bigint` | NOT NULL | — |  |
| 2 | `session_id` | `bigint` | NOT NULL | — | UNIQUE: exactly one bill per session. |
| 3 | `tariff_id` | `bigint` | NOT NULL | — | The price list this figure came from. ON DELETE RESTRICT so an old bill stays explainable. |
| 4 | `billable_minutes` | `integer` | NOT NULL | — | Minutes parked, written by trg_bill_enforce_amounts. |
| 5 | `base_amount` | `numeric(10,2)` | NOT NULL | — | Parking charge. Whatever a client sends is DISCARDED and replaced with fn_calculate_charge(session_id) by trigger - business rule 5. |
| 6 | `tax_amount` | `numeric(10,2)` | NOT NULL | — | base_amount times the facility tax rate, computed by the same trigger. |
| 7 | `total_amount` | `numeric(10,2)` | nullable | `GENERATED` | GENERATED ALWAYS AS (base_amount + tax_amount) STORED, so the arithmetic cannot be wrong. |
| 8 | `status` | `bill_status` | NOT NULL | `'unpaid'::bill_status` | Derived from the sum of payments by trg_payment_sync_bill_status; never set directly, so a bill cannot read paid with no money behind it. |
| 9 | `generated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `bill_pkey` | PRIMARY KEY | `PRIMARY KEY (bill_id)` |  |
| `bill_session_id_key` | UNIQUE | `UNIQUE (session_id)` |  |
| `fk_bill_session` | FOREIGN KEY | `FOREIGN KEY (session_id) REFERENCES parking_session(session_id) ON UPDATE CASCADE ON DELETE CASCADE` |  |
| `fk_bill_tariff` | FOREIGN KEY | `FOREIGN KEY (tariff_id) REFERENCES tariff(tariff_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `ck_bill_base_non_negative` | CHECK | `CHECK ((base_amount >= (0)::numeric))` |  |
| `ck_bill_minutes_non_negative` | CHECK | `CHECK ((billable_minutes >= 0))` |  |
| `ck_bill_tax_non_negative` | CHECK | `CHECK ((tax_amount >= (0)::numeric))` |  |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_bill_status_generated` | `public.bill USING btree (status, generated_at DESC)` | billing list filtered by status, newest first. |

**RLS policies:** `p_bill_admin` (ALL), `p_bill_operator` (ALL), `p_bill_own` (SELECT)


### `customer`

A parking customer. user_id is NULL for walk-ins recorded at the gate.

*Rows in the seeded database: 31. Row-level security: enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `customer_id` | `bigint` | NOT NULL | — |  |
| 2 | `user_id` | `bigint` | nullable | — | Login, if the customer has one. NULL for a walk-in recorded at the gate. |
| 3 | `full_name` | `text` | NOT NULL | — |  |
| 4 | `phone` | `text` | NOT NULL | — | Ten digits, no country code. UNIQUE, and the operator search key. |
| 5 | `email` | `citext` | nullable | — | Optional. CITEXT and UNIQUE. |
| 6 | `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `customer_pkey` | PRIMARY KEY | `PRIMARY KEY (customer_id)` |  |
| `customer_email_key` | UNIQUE | `UNIQUE (email)` |  |
| `customer_phone_key` | UNIQUE | `UNIQUE (phone)` |  |
| `customer_user_id_key` | UNIQUE | `UNIQUE (user_id)` |  |
| `fk_customer_user` | FOREIGN KEY | `FOREIGN KEY (user_id) REFERENCES app_user(user_id) ON UPDATE CASCADE ON DELETE SET NULL` |  |
| `ck_customer_email_shape` | CHECK | `CHECK (((email IS NULL) OR (email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'::citext)))` | Basic shape check: something@something.tld, no spaces. |
| `ck_customer_name_not_blank` | CHECK | `CHECK ((length(btrim(full_name)) > 0))` |  |
| `ck_customer_phone_shape` | CHECK | `CHECK ((phone ~ '^[0-9]{10}$'::text))` |  |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_customer_user` | `public.customer USING btree (user_id)` | RLS policies resolving app_user -> customer on every customer-scoped query. |

**RLS policies:** `p_customer_admin` (ALL), `p_customer_operator` (ALL), `p_customer_self` (SELECT)


### `facility`

A parking building. Owns floors, tariffs and operators.

*Rows in the seeded database: 5. Row-level security: not enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `facility_id` | `bigint` | NOT NULL | — | Surrogate key. |
| 2 | `name` | `text` | NOT NULL | — | Trading name; UNIQUE, so it is also a candidate key. |
| 3 | `address_line` | `text` | NOT NULL | — |  |
| 4 | `city` | `text` | NOT NULL | — |  |
| 5 | `opens_at` | `time without time zone` | NOT NULL | `'00:00:00'::time without time zone` | Local opening time. 00:00-23:59 for a 24 hour site. |
| 6 | `closes_at` | `time without time zone` | NOT NULL | `'23:59:00'::time without time zone` |  |
| 7 | `tax_rate_pct` | `numeric(5,2)` | NOT NULL | `18.00` | Percentage added to every bill raised here. Held on the facility, not on the bill: see NORMALIZATION.md 3NF(a). |
| 8 | `is_active` | `boolean` | NOT NULL | `true` | FALSE retires a site without deleting its history. |
| 9 | `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `facility_pkey` | PRIMARY KEY | `PRIMARY KEY (facility_id)` |  |
| `facility_name_key` | UNIQUE | `UNIQUE (name)` |  |
| `ck_facility_name_not_blank` | CHECK | `CHECK ((length(btrim(name)) > 0))` |  |
| `ck_facility_tax_rate` | CHECK | `CHECK (((tax_rate_pct >= (0)::numeric) AND (tax_rate_pct <= (100)::numeric)))` |  |


### `floor`

A level within a facility. level_number 0 is ground, negatives are basements.

*Rows in the seeded database: 5. Row-level security: not enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `floor_id` | `bigint` | NOT NULL | — |  |
| 2 | `facility_id` | `bigint` | NOT NULL | — |  |
| 3 | `level_number` | `integer` | NOT NULL | — | Storey number. 0 is ground, negative values are basements. UNIQUE per facility. |
| 4 | `name` | `text` | NOT NULL | — | Human label shown on the floor tabs, e.g. "Basement". |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `floor_pkey` | PRIMARY KEY | `PRIMARY KEY (floor_id)` |  |
| `uq_floor_facility_level` | UNIQUE | `UNIQUE (facility_id, level_number)` |  |
| `fk_floor_facility` | FOREIGN KEY | `FOREIGN KEY (facility_id) REFERENCES facility(facility_id) ON UPDATE CASCADE ON DELETE CASCADE` |  |
| `ck_floor_level_range` | CHECK | `CHECK (((level_number >= '-5'::integer) AND (level_number <= 50)))` |  |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_floor_facility` | `public.floor USING btree (facility_id)` |  |


### `parking_pass`

A purchased pass. Active-ness is derived from the date window and cancelled_at, not stored.

*Rows in the seeded database: 54. Row-level security: enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `pass_id` | `bigint` | NOT NULL | — |  |
| 2 | `customer_id` | `bigint` | NOT NULL | — |  |
| 3 | `vehicle_id` | `bigint` | NOT NULL | — |  |
| 4 | `pass_type_id` | `bigint` | NOT NULL | — |  |
| 5 | `facility_id` | `bigint` | NOT NULL | — |  |
| 6 | `valid_from` | `timestamp with time zone` | NOT NULL | — | Start of cover. A session entering inside the window bills at zero. |
| 7 | `valid_to` | `timestamp with time zone` | NOT NULL | — | End of cover, exclusive. |
| 8 | `price_paid` | `numeric(10,2)` | NOT NULL | — | What this customer was charged. Deliberately NOT a copy of pass_type.price: the two must diverge when the shelf price changes. See NORMALIZATION.md section 5. |
| 9 | `cancelled_at` | `timestamp with time zone` | nullable | — | Set on cancellation. Stored because cancellation is an event that cannot be inferred from the dates; active/expired state IS inferred. |
| 10 | `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `parking_pass_pkey` | PRIMARY KEY | `PRIMARY KEY (pass_id)` |  |
| `fk_pass_customer` | FOREIGN KEY | `FOREIGN KEY (customer_id) REFERENCES customer(customer_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `fk_pass_facility` | FOREIGN KEY | `FOREIGN KEY (facility_id) REFERENCES facility(facility_id) ON UPDATE CASCADE ON DELETE CASCADE` |  |
| `fk_pass_type` | FOREIGN KEY | `FOREIGN KEY (pass_type_id) REFERENCES pass_type(pass_type_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `fk_pass_vehicle` | FOREIGN KEY | `FOREIGN KEY (vehicle_id) REFERENCES vehicle(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `fk_pass_vehicle_owner` | FOREIGN KEY | `FOREIGN KEY (vehicle_id, customer_id) REFERENCES vehicle(vehicle_id, customer_id)` | Ownership: a pass can only cover the buying customer's own vehicle. |
| `ck_pass_price` | CHECK | `CHECK ((price_paid >= (0)::numeric))` |  |
| `ck_pass_window` | CHECK | `CHECK ((valid_to > valid_from))` |  |
| `ex_pass_no_overlap` | EXCLUDE | `EXCLUDE USING gist (vehicle_id WITH =, facility_id WITH =, tstzrange(valid_from, valid_to) WITH &&) WHERE ((cancelled_at IS NULL))` |  |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_pass_vehicle_window` | `public.parking_pass USING btree (vehicle_id, valid_from, valid_to) WHERE (cancelled_at IS NULL)` | valid-pass check during gate entry. |

**RLS policies:** `p_pass_admin` (ALL), `p_pass_operator` (ALL), `p_pass_own` (ALL)


### `parking_session`

A vehicle occupying a slot. Active when exit_time IS NULL; there is deliberately no status column.

*Rows in the seeded database: 1629. Row-level security: enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `session_id` | `bigint` | NOT NULL | — | Surrogate key. |
| 2 | `ticket_no` | `text` | NOT NULL | — | Printed ticket reference, TK- plus 8 hex characters. UNIQUE, and one of the two gate lookup keys. |
| 3 | `slot_id` | `bigint` | NOT NULL | — |  |
| 4 | `vehicle_id` | `bigint` | NOT NULL | — |  |
| 5 | `vehicle_type_id` | `bigint` | NOT NULL | — | Carried so the two composite foreign keys can compare the bay type against the vehicle type. Pinned to both simultaneously, so it cannot drift. See NORMALIZATION.md section 5. |
| 6 | `entry_time` | `timestamp with time zone` | NOT NULL | `now()` | Arrival. Also selects which tariff applies. |
| 7 | `exit_time` | `timestamp with time zone` | nullable | — | Departure. NULL means still parked - this column IS the session status, which is why no status column exists. |
| 8 | `reservation_id` | `bigint` | nullable | — | The booking this arrival fulfilled, if any. UNIQUE: a reservation is fulfilled at most once. |
| 9 | `pass_id` | `bigint` | nullable | — | The pass covering this stay, if any. When set, fn_calculate_charge returns zero. |
| 10 | `entry_operator_id` | `bigint` | nullable | — | Who admitted the vehicle. SET NULL on staff deletion so the session survives. |
| 11 | `exit_operator_id` | `bigint` | nullable | — | Who released the bay. |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `parking_session_pkey` | PRIMARY KEY | `PRIMARY KEY (session_id)` |  |
| `parking_session_reservation_id_key` | UNIQUE | `UNIQUE (reservation_id)` |  |
| `parking_session_ticket_no_key` | UNIQUE | `UNIQUE (ticket_no)` |  |
| `fk_session_entry_operator` | FOREIGN KEY | `FOREIGN KEY (entry_operator_id) REFERENCES app_user(user_id) ON UPDATE CASCADE ON DELETE SET NULL` |  |
| `fk_session_exit_operator` | FOREIGN KEY | `FOREIGN KEY (exit_operator_id) REFERENCES app_user(user_id) ON UPDATE CASCADE ON DELETE SET NULL` |  |
| `fk_session_pass` | FOREIGN KEY | `FOREIGN KEY (pass_id) REFERENCES parking_pass(pass_id) ON UPDATE CASCADE ON DELETE SET NULL` |  |
| `fk_session_reservation` | FOREIGN KEY | `FOREIGN KEY (reservation_id) REFERENCES reservation(reservation_id) ON UPDATE CASCADE ON DELETE SET NULL` |  |
| `fk_session_slot_type_match` | FOREIGN KEY | `FOREIGN KEY (slot_id, vehicle_type_id) REFERENCES slot(slot_id, vehicle_type_id) ON UPDATE CASCADE ON DELETE RESTRICT` | BUSINESS RULE 2: composite FK making a car-in-bike-bay session structurally impossible. |
| `fk_session_vehicle_type_match` | FOREIGN KEY | `FOREIGN KEY (vehicle_id, vehicle_type_id) REFERENCES vehicle(vehicle_id, vehicle_type_id) ON UPDATE CASCADE ON DELETE RESTRICT` | Pins parking_session.vehicle_type_id to the vehicle's real type, so the copied column cannot drift. |
| `ck_session_exit_after_entry` | CHECK | `CHECK (((exit_time IS NULL) OR (exit_time > entry_time)))` | BUSINESS RULE 3: exit must be strictly later than entry. |
| `ck_session_ticket_shape` | CHECK | `CHECK ((ticket_no ~ '^TK-[0-9A-Z]{6,12}$'::text))` |  |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_session_entry_time` | `public.parking_session USING btree (entry_time DESC)` | recent-activity feed and all date-windowed session reports. |
| `ix_session_open_by_slot` | `public.parking_session USING btree (slot_id) WHERE (exit_time IS NULL)` | v_current_occupancy slot -> open session join. |
| `ix_session_open_by_vehicle` | `public.parking_session USING btree (vehicle_id) WHERE (exit_time IS NULL)` | open-session lookup by vehicle in fn_gate_entry / fn_gate_exit. |
| `uq_active_session_slot` | `public.parking_session USING btree (slot_id) WHERE (exit_time IS NULL)` | BUSINESS RULE 1: at most one open session per slot. |
| `uq_active_session_vehicle` | `public.parking_session USING btree (vehicle_id) WHERE (exit_time IS NULL)` | BUSINESS RULE 1 (mirror): a vehicle cannot occupy two slots at once. |

**RLS policies:** `p_session_admin` (ALL), `p_session_operator` (ALL), `p_session_own` (SELECT)


### `pass_type`

Sellable pass products. A pass is an instance of a pass_type bought by a customer.

*Rows in the seeded database: 15. Row-level security: not enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `pass_type_id` | `bigint` | NOT NULL | — |  |
| 2 | `code` | `text` | NOT NULL | — |  |
| 3 | `name` | `text` | NOT NULL | — |  |
| 4 | `duration_days` | `integer` | NOT NULL | — | How long a pass of this product runs from its start date. |
| 5 | `price` | `numeric(10,2)` | NOT NULL | — | Current shelf price. What a customer actually paid is parking_pass.price_paid. |
| 6 | `vehicle_type_id` | `bigint` | NOT NULL | — |  |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `pass_type_pkey` | PRIMARY KEY | `PRIMARY KEY (pass_type_id)` |  |
| `pass_type_code_key` | UNIQUE | `UNIQUE (code)` |  |
| `fk_pass_type_vehicle_type` | FOREIGN KEY | `FOREIGN KEY (vehicle_type_id) REFERENCES vehicle_type(vehicle_type_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `ck_pass_type_duration` | CHECK | `CHECK (((duration_days >= 1) AND (duration_days <= 366)))` |  |
| `ck_pass_type_price` | CHECK | `CHECK ((price >= (0)::numeric))` |  |


### `payment`

A recorded receipt against a bill. Several payments may settle one bill (partly_paid). No payment credentials are stored.

*Rows in the seeded database: 1398. Row-level security: enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `payment_id` | `bigint` | NOT NULL | — |  |
| 2 | `bill_id` | `bigint` | NOT NULL | — |  |
| 3 | `amount` | `numeric(10,2)` | NOT NULL | — | Money received. CHECK > 0. Several payments may settle one bill, giving partly_paid. |
| 4 | `method` | `payment_method` | NOT NULL | — | How it was taken. Recorded only - no gateway is integrated. |
| 5 | `reference_no` | `text` | nullable | — | Free-text receipt or terminal reference. NEVER a card number, CVV or UPI credential: none are collected anywhere in this system. |
| 6 | `paid_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| 7 | `received_by` | `bigint` | nullable | — | Operator who took the payment. |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `payment_pkey` | PRIMARY KEY | `PRIMARY KEY (payment_id)` |  |
| `fk_payment_bill` | FOREIGN KEY | `FOREIGN KEY (bill_id) REFERENCES bill(bill_id) ON UPDATE CASCADE ON DELETE CASCADE` |  |
| `fk_payment_received_by` | FOREIGN KEY | `FOREIGN KEY (received_by) REFERENCES app_user(user_id) ON UPDATE CASCADE ON DELETE SET NULL` |  |
| `ck_payment_amount_positive` | CHECK | `CHECK ((amount > (0)::numeric))` |  |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_payment_bill` | `public.payment USING btree (bill_id)` | payment rollup per bill in v_revenue_daily and the status trigger. |
| `ix_payment_paid_at` | `public.payment USING btree (paid_at DESC)` | payments over time and method breakdown. |

**RLS policies:** `p_payment_admin` (ALL), `p_payment_operator` (ALL), `p_payment_own` (SELECT)


### `reservation`

A slot held for a future arrival. Stale holds are expired by fn_expire_stale_reservations.

*Rows in the seeded database: 32. Row-level security: enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `reservation_id` | `bigint` | NOT NULL | — |  |
| 2 | `customer_id` | `bigint` | NOT NULL | — |  |
| 3 | `vehicle_id` | `bigint` | NOT NULL | — |  |
| 4 | `slot_id` | `bigint` | NOT NULL | — |  |
| 5 | `reserved_from` | `timestamp with time zone` | NOT NULL | — | Start of the hold. The bay is blocked for the whole window. |
| 6 | `reserved_until` | `timestamp with time zone` | NOT NULL | — | End of the hold. Must be later than reserved_from (business rule 4). |
| 7 | `status` | `reservation_status` | NOT NULL | `'held'::reservation_status` | held and confirmed block the bay and participate in ex_reservation_no_overlap; expired, cancelled and fulfilled are history and do not. |
| 8 | `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| 9 | `vehicle_type_id` | `bigint` | NOT NULL | — | Join column for the two type-match foreign keys; forced equal to both the slot's and the vehicle's type. |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `reservation_pkey` | PRIMARY KEY | `PRIMARY KEY (reservation_id)` |  |
| `fk_reservation_customer` | FOREIGN KEY | `FOREIGN KEY (customer_id) REFERENCES customer(customer_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `fk_reservation_slot` | FOREIGN KEY | `FOREIGN KEY (slot_id) REFERENCES slot(slot_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `fk_reservation_slot_type_match` | FOREIGN KEY | `FOREIGN KEY (slot_id, vehicle_type_id) REFERENCES slot(slot_id, vehicle_type_id)` | BUSINESS RULE 2 at booking time: the bay's vehicle type must equal reservation.vehicle_type_id. |
| `fk_reservation_vehicle` | FOREIGN KEY | `FOREIGN KEY (vehicle_id) REFERENCES vehicle(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `fk_reservation_vehicle_owner` | FOREIGN KEY | `FOREIGN KEY (vehicle_id, customer_id) REFERENCES vehicle(vehicle_id, customer_id)` | Ownership: a customer can only book with their own vehicle. Composite FK onto vehicle(vehicle_id, customer_id). |
| `fk_reservation_vehicle_type_match` | FOREIGN KEY | `FOREIGN KEY (vehicle_id, vehicle_type_id) REFERENCES vehicle(vehicle_id, vehicle_type_id)` | Pins reservation.vehicle_type_id to the vehicle's real type, so the copied column cannot drift. |
| `ck_reservation_window` | CHECK | `CHECK ((reserved_until > reserved_from))` |  |
| `ex_reservation_no_overlap` | EXCLUDE | `EXCLUDE USING gist (slot_id WITH =, tstzrange(reserved_from, reserved_until) WITH &&) WHERE ((status = ANY (ARRAY['held'::reservation_status, 'conf…` | BUSINESS RULE 4: no two live reservations may overlap on one slot. |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_reservation_slot_window` | `public.reservation USING gist (slot_id, tstzrange(reserved_from, reserved_until)) WHERE (status = ANY (ARRAY['held'::reservation_status, 'confirmed'::reservation_status]))` | live-hold overlap checks in fn_allocate_slot and v_current_occupancy. |
| `ix_reservation_status_until` | `public.reservation USING btree (status, reserved_until)` | reservations list filter and the expiry sweep. |

**RLS policies:** `p_reservation_admin` (ALL), `p_reservation_operator` (ALL), `p_reservation_own` (ALL)


### `slot`

One parking space. Occupancy is NOT stored here - it is derived from parking_session via v_current_occupancy.

*Rows in the seeded database: 134. Row-level security: not enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `slot_id` | `bigint` | NOT NULL | — | Surrogate key. |
| 2 | `zone_id` | `bigint` | NOT NULL | — |  |
| 3 | `code` | `text` | NOT NULL | — | Bay number painted on the floor, e.g. B-A-07. UNIQUE within its zone. |
| 4 | `vehicle_type_id` | `bigint` | NOT NULL | — | What this bay is built for. Half of the composite key that makes business rule 2 structural. |
| 5 | `is_active` | `boolean` | NOT NULL | `true` | FALSE = out of service. fn_allocate_slot never returns an inactive bay. |
| 6 | `grid_row` | `smallint` | nullable | — | Position on the floor plan, so the map renders as a plan rather than a list. |
| 7 | `grid_col` | `smallint` | nullable | — | Position on the floor plan. NULL where a bay has no mapped position. |
| 8 | `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| 9 | `service_note` | `text` | nullable | — | Why the bay is out of service. Only allowed while is_active is FALSE. |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `slot_pkey` | PRIMARY KEY | `PRIMARY KEY (slot_id)` |  |
| `uq_slot_id_vehicle_type` | UNIQUE | `UNIQUE (slot_id, vehicle_type_id)` | Target for the composite FK on parking_session that makes slot/vehicle type mismatch structurally impossible. |
| `uq_slot_zone_code` | UNIQUE | `UNIQUE (zone_id, code)` |  |
| `fk_slot_vehicle_type` | FOREIGN KEY | `FOREIGN KEY (vehicle_type_id) REFERENCES vehicle_type(vehicle_type_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `fk_slot_zone` | FOREIGN KEY | `FOREIGN KEY (zone_id) REFERENCES zone(zone_id) ON UPDATE CASCADE ON DELETE CASCADE` |  |
| `ck_slot_code_shape` | CHECK | `CHECK ((code ~ '^[A-Z0-9-]{2,16}$'::text))` |  |
| `ck_slot_note_only_when_out` | CHECK | `CHECK (((service_note IS NULL) OR ((NOT is_active) AND ((char_length(service_note) >= 1) AND (char_length(service_note) <= 200)))))` | A service note describes why a bay is out of service, so it may exist only while is_active is FALSE. |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_slot_type` | `public.slot USING btree (vehicle_type_id)` |  |
| `ix_slot_zone` | `public.slot USING btree (zone_id)` | slot -> zone -> floor -> facility chain behind the floor map. |


### `tariff`

Versioned price list. Superseded rows are closed with effective_to so historical bills stay reproducible.

*Rows in the seeded database: 11. Row-level security: not enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `tariff_id` | `bigint` | NOT NULL | — |  |
| 2 | `facility_id` | `bigint` | NOT NULL | — |  |
| 3 | `vehicle_type_id` | `bigint` | NOT NULL | — |  |
| 4 | `name` | `text` | NOT NULL | — |  |
| 5 | `free_minutes` | `integer` | NOT NULL | `15` | Grace period. Leaving within this many minutes costs nothing. |
| 6 | `first_hour_rate` | `numeric(10,2)` | NOT NULL | — | Charge for the first chargeable hour, usually dearer than later hours. |
| 7 | `subsequent_hour_rate` | `numeric(10,2)` | NOT NULL | — | Charge for each hour after the first. |
| 8 | `daily_cap` | `numeric(10,2)` | NOT NULL | — | Maximum charge per 24 hours, so an overnight stay cannot run away. |
| 9 | `effective_from` | `timestamp with time zone` | NOT NULL | `now()` | Start of this price list. fn_calculate_charge picks the row covering the session entry_time. |
| 10 | `effective_to` | `timestamp with time zone` | nullable | — | End of this price list; NULL means in force. Superseding a tariff closes the old row rather than overwriting it, so old bills stay reproducible. |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `tariff_pkey` | PRIMARY KEY | `PRIMARY KEY (tariff_id)` |  |
| `fk_tariff_facility` | FOREIGN KEY | `FOREIGN KEY (facility_id) REFERENCES facility(facility_id) ON UPDATE CASCADE ON DELETE CASCADE` |  |
| `fk_tariff_vehicle_type` | FOREIGN KEY | `FOREIGN KEY (vehicle_type_id) REFERENCES vehicle_type(vehicle_type_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `ck_tariff_cap_sane` | CHECK | `CHECK ((daily_cap >= first_hour_rate))` |  |
| `ck_tariff_free_minutes` | CHECK | `CHECK (((free_minutes >= 0) AND (free_minutes <= 1440)))` |  |
| `ck_tariff_rates_non_negative` | CHECK | `CHECK (((first_hour_rate >= (0)::numeric) AND (subsequent_hour_rate >= (0)::numeric) AND (daily_cap >= (0)::numeric)))` |  |
| `ck_tariff_window_valid` | CHECK | `CHECK (((effective_to IS NULL) OR (effective_to > effective_from)))` |  |
| `ex_tariff_no_overlap` | EXCLUDE | `EXCLUDE USING gist (facility_id WITH =, vehicle_type_id WITH =, tstzrange(effective_from, effective_to) WITH &&)` | Guarantees fn_calculate_charge finds exactly one applicable tariff for any instant. |


### `vehicle`

A customer vehicle. plate_number is UNIQUE and is the operator search key.

*Rows in the seeded database: 46. Row-level security: enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `vehicle_id` | `bigint` | NOT NULL | — |  |
| 2 | `customer_id` | `bigint` | NOT NULL | — | Owner. ON DELETE RESTRICT: a vehicle with parking history cannot vanish with its owner. |
| 3 | `plate_number` | `text` | NOT NULL | — | Registration, uppercase and unspaced, e.g. TS09AB1234. UNIQUE, indexed, and the primary lookup at the gate. |
| 4 | `vehicle_type_id` | `bigint` | NOT NULL | — | What this vehicle is. The other half of the composite key behind business rule 2. |
| 5 | `make` | `text` | nullable | — |  |
| 6 | `model` | `text` | nullable | — |  |
| 7 | `colour` | `text` | nullable | — |  |
| 8 | `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `vehicle_pkey` | PRIMARY KEY | `PRIMARY KEY (vehicle_id)` |  |
| `uq_vehicle_id_customer` | UNIQUE | `UNIQUE (vehicle_id, customer_id)` |  |
| `uq_vehicle_id_vehicle_type` | UNIQUE | `UNIQUE (vehicle_id, vehicle_type_id)` |  |
| `vehicle_plate_number_key` | UNIQUE | `UNIQUE (plate_number)` |  |
| `fk_vehicle_customer` | FOREIGN KEY | `FOREIGN KEY (customer_id) REFERENCES customer(customer_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `fk_vehicle_vehicle_type` | FOREIGN KEY | `FOREIGN KEY (vehicle_type_id) REFERENCES vehicle_type(vehicle_type_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `ck_vehicle_plate_shape` | CHECK | `CHECK ((plate_number ~ '^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$'::text))` | Indian registration format, e.g. MH12AB1234, stored unspaced and uppercase. |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_vehicle_customer` | `public.vehicle USING btree (customer_id)` |  |
| `ix_vehicle_plate_upper` | `public.vehicle USING btree (upper(plate_number))` | gate lookup by plate, case-insensitively. |

**RLS policies:** `p_vehicle_admin` (ALL), `p_vehicle_operator` (ALL), `p_vehicle_own` (ALL)


### `vehicle_type`

Vehicle categories. Referenced by slot, vehicle, tariff and pass_type.

*Rows in the seeded database: 5. Row-level security: not enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `vehicle_type_id` | `bigint` | NOT NULL | — |  |
| 2 | `code` | `text` | NOT NULL | — | Short uppercase key: CAR, BIKE, SUV, EV, TRUCK. |
| 3 | `name` | `text` | NOT NULL | — |  |
| 4 | `footprint_units` | `smallint` | NOT NULL | `1` | Relative bay size, 1-4. Drives the footprint drawn on the map. |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `vehicle_type_pkey` | PRIMARY KEY | `PRIMARY KEY (vehicle_type_id)` |  |
| `vehicle_type_code_key` | UNIQUE | `UNIQUE (code)` |  |
| `ck_vehicle_type_code_shape` | CHECK | `CHECK ((code ~ '^[A-Z]{2,10}$'::text))` |  |
| `ck_vehicle_type_footprint` | CHECK | `CHECK (((footprint_units >= 1) AND (footprint_units <= 4)))` |  |


### `violation`

Logged infringements: overstay, wrong slot type, no valid pass, unpaid exit, reservation no-show.

*Rows in the seeded database: 52. Row-level security: enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `violation_id` | `bigint` | NOT NULL | — |  |
| 2 | `kind` | `violation_type` | NOT NULL | — | overstay | wrong_slot_type | no_valid_pass | unpaid_exit | reservation_no_show. |
| 3 | `session_id` | `bigint` | nullable | — | The stay it arose from, where there was one. |
| 4 | `vehicle_id` | `bigint` | NOT NULL | — |  |
| 5 | `slot_id` | `bigint` | nullable | — |  |
| 6 | `detected_at` | `timestamp with time zone` | NOT NULL | `now()` | When it was noticed. Overstays are logged automatically by fn_gate_exit. |
| 7 | `penalty_amount` | `numeric(10,2)` | NOT NULL | `0` | Fine levied. Zero where the violation is recorded but not charged for. |
| 8 | `notes` | `text` | nullable | — |  |
| 9 | `resolved_at` | `timestamp with time zone` | nullable | — | NULL while outstanding. Must not precede detected_at. |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `violation_pkey` | PRIMARY KEY | `PRIMARY KEY (violation_id)` |  |
| `fk_violation_session` | FOREIGN KEY | `FOREIGN KEY (session_id) REFERENCES parking_session(session_id) ON UPDATE CASCADE ON DELETE SET NULL` |  |
| `fk_violation_slot` | FOREIGN KEY | `FOREIGN KEY (slot_id) REFERENCES slot(slot_id) ON UPDATE CASCADE ON DELETE SET NULL` |  |
| `fk_violation_vehicle` | FOREIGN KEY | `FOREIGN KEY (vehicle_id) REFERENCES vehicle(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT` |  |
| `ck_violation_penalty` | CHECK | `CHECK ((penalty_amount >= (0)::numeric))` |  |
| `ck_violation_resolved_after` | CHECK | `CHECK (((resolved_at IS NULL) OR (resolved_at >= detected_at)))` |  |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_violation_detected` | `public.violation USING btree (detected_at DESC)` |  |
| `ix_violation_unresolved` | `public.violation USING btree (kind, detected_at DESC) WHERE (resolved_at IS NULL)` | outstanding-violations list by kind. |

**RLS policies:** `p_violation_admin` (ALL), `p_violation_operator` (ALL), `p_violation_own` (SELECT)


### `zone`

A block of slots on one floor, e.g. Zone A. Used for aisle grouping in the slot map.

*Rows in the seeded database: 10. Row-level security: not enabled.*

| # | Column | Type | Null | Default | Description |
|--:|---|---|---|---|---|
| 1 | `zone_id` | `bigint` | NOT NULL | — |  |
| 2 | `floor_id` | `bigint` | NOT NULL | — |  |
| 3 | `code` | `text` | NOT NULL | — | Single letter block identifier, unique within the floor. Used for aisle grouping on the slot map. |
| 4 | `name` | `text` | NOT NULL | — |  |

**Constraints**

| Name | Kind | Definition | Note |
|---|---|---|---|
| `zone_pkey` | PRIMARY KEY | `PRIMARY KEY (zone_id)` |  |
| `uq_zone_floor_code` | UNIQUE | `UNIQUE (floor_id, code)` |  |
| `fk_zone_floor` | FOREIGN KEY | `FOREIGN KEY (floor_id) REFERENCES floor(floor_id) ON UPDATE CASCADE ON DELETE CASCADE` |  |
| `ck_zone_code_shape` | CHECK | `CHECK ((code ~ '^[A-Z]{1,3}$'::text))` |  |

**Indexes** (beyond those backing the constraints above)

| Name | Definition | Serves |
|---|---|---|
| `ix_zone_floor` | `public.zone USING btree (floor_id)` |  |


---

## Views

| View | security_invoker | Purpose |
|---|:--:|---|
| `v_current_occupancy` | yes | Live state of every slot. Drives the floor map. Occupancy is derived here, never stored. |
| `v_free_slots` | yes | Report: free slots. Subset of v_current_occupancy. |
| `v_pass_usage` | yes | Report: pass usage. LATERAL subquery aggregating the sessions each pass covered. |
| `v_peak_hours` | yes | Report: peak hours. GROUP BY hour with a RANK() window over the aggregate. |
| `v_recent_activity` | yes | Report: every gate, payment, booking and violation event as one stream (UNION ALL of five branches). |
| `v_revenue_daily` | yes | Report: daily revenue. Separates billed from collected so the receivable is visible. |
| `v_session_duration` | yes | Report: session duration with CASE bucketing and a LEFT JOIN to bill. |
| `v_violations` | yes | Report: violations, joined out to vehicle, customer, slot and session. |

`security_invoker = true` on every view means row-level security is
evaluated as the querying role. Without it a view runs as its owner and
becomes a way around the policies it appears to respect.

---

## Functions

| Function | Security | Purpose |
|---|---|---|
| `fn_allocate_slot(p_facility_id bigint, p_vehicle_type_id bigint, p_at timestamp with time zone)` | DEFINER | Picks the nearest free slot and row-locks it with SELECT ... FOR UPDATE SKIP LOCKED. Returns NULL when full. |
| `fn_applicable_tariff(p_session_id bigint)` | INVOKER |  |
| `fn_audit_row()` | DEFINER |  |
| `fn_bill_enforce_amounts()` | INVOKER | Overwrites any client-supplied bill amount with the value from fn_calculate_charge. |
| `fn_calculate_charge(p_session_id bigint)` | INVOKER | BUSINESS RULE 5: the only place a parking charge is computed. Reads the tariff in force at entry_time. |
| `fn_current_customer_id()` | INVOKER |  |
| `fn_current_facility_id()` | INVOKER |  |
| `fn_current_role()` | INVOKER |  |
| `fn_current_user_id()` | INVOKER |  |
| `fn_expire_stale_reservations()` | INVOKER | BUSINESS RULE 4: idempotent sweep that expires lapsed holds and logs no-shows. |
| `fn_gate_entry(p_plate text, p_facility_id bigint, p_operator_id bigint)` | DEFINER | Atomic arrival: resolve vehicle, honour reservation or allocate a locked slot, attach pass, open session. |
| `fn_gate_exit(p_lookup text, p_operator_id bigint)` | DEFINER | Atomic departure: lock session, stamp exit, raise bill from fn_calculate_charge, log overstay. |
| `fn_payment_sync_bill_status()` | INVOKER |  |
| `fn_payment_within_balance()` | INVOKER | Refuses a payment that would take a bill past its total. Locks the bill row so concurrent payments serialise. |
| `fn_reservation_prepare()` | INVOKER |  |
| `fn_set_slot_service(p_slot_id bigint, p_in_service boolean, p_note text)` | INVOKER | Take a bay out of service or return it. Refuses an occupied or held bay; operators are limited to their facility. |
