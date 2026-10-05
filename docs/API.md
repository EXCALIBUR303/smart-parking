# API reference

All endpoints live under `/api` in [`api/main.py`](../api/main.py). FastAPI also
serves interactive documentation at **http://127.0.0.1:8077/docs** while the
application is running.

**Authentication.** `POST /api/auth/login` returns a token; every other call
except `/api/health` sends it as `Authorization: Bearer <token>`.

**Who may call it.** *Signed in* means any role. Row-level security then decides
which **rows** come back: a customer sees only their own vehicles, bills,
bookings and passes; an operator sees only their facility. *Staff* means admin
or operator. Role checks in the API are a first line; the database role
(`SET LOCAL ROLE parking_<role>`) and RLS policies are the real boundary.

**Errors.** A refused request returns `{"detail": "<plain-English reason>",
"rule": "<constraint or trigger name>"}`, mapped from the PostgreSQL error in
[`api/errors.py`](../api/errors.py): 409 for a broken rule, 403 for a privilege,
404 for a missing row, 422 for malformed input.

## Sign-in and reference data

| Method | Path | Who | Does |
|---|---|---|---|
| POST | `/api/auth/login` | public | Verifies the bcrypt hash, returns a token |
| GET | `/api/auth/me` | signed in | The signed-in user |
| GET | `/api/health` | public | Database reachability |
| GET | `/api/facilities` | signed in | Facilities |
| GET | `/api/vehicle-types` | signed in | Vehicle types |
| GET | `/api/floors` | signed in | Floors and zones |
| GET | `/api/tariffs` | signed in | Tariff versions, with which is in force |
| POST | `/api/tariffs` | admin | New tariff version; `ex_tariff_no_overlap` refuses two in force |
| GET | `/api/pass-types` | signed in | Pass products |

## Bays and the gate

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/api/slots` | signed in | Every bay with its live state (`v_current_occupancy`) |
| GET | `/api/slots/free` | signed in | Free bays by facility and vehicle type (`v_free_slots`) |
| PATCH | `/api/slots/{id}/service` | staff | `fn_set_slot_service`: take a bay out of service with a note, or return it |
| POST | `/api/gate/entry` | staff | `fn_gate_entry`: honours a reservation or allocates and locks a bay, attaches a live pass, issues a ticket |
| GET | `/api/gate/lookup?q=` | staff | Open session by ticket or plate, with the running charge from `fn_calculate_charge` |
| POST | `/api/gate/exit` | staff | `fn_gate_exit`: closes the session, raises the bill, logs an overstay |
| GET | `/api/sessions` | signed in | Sessions (`v_session_duration`), optionally open ones only |

## Reservations and passes

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/api/reservations` | signed in | Reservations; runs `fn_expire_stale_reservations()` first |
| POST | `/api/reservations` | signed in | Book a bay; overlap, bay type and vehicle ownership are checked by constraints |
| PATCH | `/api/reservations/{id}` | signed in | Change status to held, confirmed or cancelled |
| GET | `/api/passes` | signed in | Passes with their derived state |
| POST | `/api/passes` | signed in | Buy a pass; `ex_pass_no_overlap` refuses a second live pass |
| DELETE | `/api/passes/{id}` | signed in | Cancel (sets `cancelled_at`; the row is kept) |

## Billing

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/api/bills` | signed in | Bills, filterable by status and searchable by bill, plate or name |
| GET | `/api/bills/{id}` | signed in | One bill with its session, tariff and payments (the invoice) |
| POST | `/api/payments` | staff | Record a payment; `trg_payment_within_balance` refuses overpayment, `trg_payment_sync_bill_status` updates the bill |
| GET | `/api/payments` | staff | Payments ledger with totals by method |

## Customers and vehicles

| Method | Path | Who | Does |
|---|---|---|---|
| GET | `/api/customers` | signed in | Customers (a customer sees only themself) |
| POST | `/api/customers` | staff | Add a customer |
| PATCH | `/api/customers/{id}` | staff | Edit name, phone, email |
| DELETE | `/api/customers/{id}` | admin | Remove; refused while vehicles or history exist (`ON DELETE RESTRICT`) |
| GET | `/api/vehicles` | signed in | Vehicles |
| POST | `/api/vehicles` | signed in | Register a vehicle; plate shape and uniqueness checked by constraints |
| PATCH | `/api/vehicles/{id}` | signed in | Edit plate, make, model, colour |
| DELETE | `/api/vehicles/{id}` | signed in | Remove; refused while it has sessions, bookings or passes |

## Reports and monitoring

Each report reads one view, so the figure on screen is the figure the database
computes.

| Method | Path | Who | Reads |
|---|---|---|---|
| GET | `/api/reports/occupancy` | signed in | `v_current_occupancy` |
| GET | `/api/reports/peak-hours` | signed in | `v_peak_hours` |
| GET | `/api/reports/revenue` | signed in | `v_revenue_daily` |
| GET | `/api/reports/duration` | signed in | `v_session_duration` |
| GET | `/api/reports/pass-usage` | signed in | `v_pass_usage` |
| GET | `/api/reports/violations` | signed in | `v_violations` |
| GET | `/api/reports/free-slots` | signed in | `v_free_slots` |
| GET | `/api/reports/vehicle-history?plate=` | signed in | One vehicle's sessions, bills, passes and violations |
| GET | `/api/activity` | signed in | `v_recent_activity`: entries, exits, payments, bookings, violations |
| GET | `/api/audit` | admin | `audit_log`, filterable by table |
| GET | `/api/dashboard` | signed in | The dashboard figures, scoped to a facility |
