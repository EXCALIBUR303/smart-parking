# Demo guide — ten minutes for the review

A walkthrough that shows the working system and, at each step, the database
feature doing the work. Run the app first (`./.venv/bin/uvicorn api.main:app
--port 8077`), open http://127.0.0.1:8077, and keep a `psql -d smartpark`
window beside it. All passwords are `Parking@123`.

| # | Do this | What it proves | Point at |
|--:|---|---|---|
| 1 | Sign in as `admin@smartpark.in`. Read the dashboard cards and the live activity feed. | Every figure is a query, not a constant | `GET /api/dashboard`, `v_recent_activity` |
| 2 | **Floor map.** Click an occupied bay, then a free one. | Bay state is derived, never stored | `v_current_occupancy`; no `slot.status` column (NORMALIZATION.md §4) |
| 3 | **Gate → Arrival:** type `TS10WX1515`, press Record arrival. | Allocation is one transaction with a row lock | `fn_gate_entry` → `fn_allocate_slot` (`FOR UPDATE SKIP LOCKED`) |
| 4 | Press Record arrival again for the same plate. | One vehicle cannot hold two bays | `uq_active_session_vehicle` |
| 5 | **Gate → Departure:** look up the same plate, Confirm departure. | The charge comes from the tariff, not the client | `fn_gate_exit`, `fn_calculate_charge`, `trg_bill_enforce_amounts` |
| 6 | Look up a long-parked car (any *In lot* row from the morning), confirm, then **Record payment** for half, then try more than the balance. | Bill status follows payments; overpayment is refused | `trg_payment_sync_bill_status`, `trg_payment_within_balance` |
| 7 | **Reservations → New reservation:** book a bay, then book the same bay for an overlapping time. | No double booking | `ex_reservation_no_overlap` (GiST `EXCLUDE`) |
| 8 | **Floor map:** open a free bay and take it out of service with a note; open an occupied one and see that it cannot be. Then return the first to service. | Business logic lives in the database | `fn_set_slot_service` locks the bay and refuses an occupied or booked one (TESTING.md test 20); `ck_slot_note_only_when_out` |
| 9 | **Reports:** Peak hours, Revenue, Violations; then Vehicle history for `TS09AB1234`. Export one as CSV. | Reports are views | `v_peak_hours`, `v_revenue_daily`, `v_violations` |
| 10 | **Settings → Audit trail.** Open the newest row. | Every change is recorded with who did it | `trg_audit` → `audit_log` |
| 11 | Sign out, sign in as `rahul.sharma@example.com`. Open Customers and Billing. | Row-level security: 3 vehicles instead of 46 | `009_rls.sql`, `SET LOCAL ROLE` in `api/db.py` |
| 12 | Sign in as `ops.river@smartpark.in` and open Gate. | Operators are scoped to their facility | `p_*_operator` policies |

## In the psql window

```sql
-- Business rule 1: try to park a second car in an occupied bay
\i db/tests/constraint_tests.sql      -- 25 attempts, each refused or corrected

-- Time-driven rules: expiry, overstay, passes (rolled back afterwards)
\i db/tests/lifecycle_tests.sql

-- Joins, subqueries, windows, JSONB and the views
\i docs/database/queries.sql
```

## If something goes wrong in the room

- **No internet:** the app runs fully offline; only the animation library is
  loaded from a CDN, and without it the app still works, just without motion.
- **Demo data looks old:** `psql -d smartpark -f db/scripts/refresh_demo_history.sql`
  moves the seeded history up to the present.
- **Start clean:** `./setup.sh --reset` rebuilds the database in seconds.
