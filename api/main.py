"""Smart Parking Lot Allocation & Billing System - HTTP API.

The API is deliberately thin. Every business rule, every amount and every
concurrency guarantee lives in PostgreSQL (see db/migrations/). This layer
authenticates the caller, tells the database who they are so row-level
security applies, calls a function or runs a query, and maps errors.

Run:  ./.venv/bin/uvicorn api.main:app --reload --port 8000
"""
import datetime as dt
from decimal import Decimal
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
import psycopg
import os

from . import db as database
from .auth import current_user, hash_password, make_token, require_admin, require_staff, verify_password
from .config import WEB_DIR
from .errors import as_http

app = FastAPI(title="Smart Parking API", version="1.0.0")


@app.on_event("startup")
def _startup():
    database.open_pool()


@app.on_event("shutdown")
def _shutdown():
    database.close_pool()


def json_safe(value):
    """Decimals and datetimes to JSON-friendly primitives."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def ok(payload, status_code: int = 200):
    """JSONResponse carries its own status, which silently overrides a route
    decorator's status_code. Creation endpoints therefore pass 201 here."""
    return JSONResponse(json_safe(payload), status_code=status_code)


# ===========================================================================
# Request models. Validation here is for responsiveness; the database
# constraints in db/migrations are the real gate, and they run regardless of
# what any client sends.
# ===========================================================================
class LoginIn(BaseModel):
    email: str
    password: str


class GateEntryIn(BaseModel):
    plate: str = Field(min_length=4, max_length=16)
    facility_id: int

    @field_validator("plate")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.replace(" ", "").replace("-", "").upper()


class GateExitIn(BaseModel):
    lookup: str = Field(min_length=3, max_length=32)

    @field_validator("lookup")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.strip().upper()


class CustomerIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(pattern=r"^[0-9]{10}$")
    email: Optional[str] = None


class VehicleIn(BaseModel):
    customer_id: int
    plate_number: str
    vehicle_type_id: int
    make: Optional[str] = None
    model: Optional[str] = None
    colour: Optional[str] = None

    @field_validator("plate_number")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.replace(" ", "").replace("-", "").upper()


class ReservationIn(BaseModel):
    customer_id: int
    vehicle_id: int
    slot_id: int
    reserved_from: dt.datetime
    reserved_until: dt.datetime


class PassIn(BaseModel):
    customer_id: int
    vehicle_id: int
    pass_type_id: int
    facility_id: int
    valid_from: dt.datetime


class PaymentIn(BaseModel):
    bill_id: int
    amount: float = Field(gt=0)
    method: str
    reference_no: Optional[str] = None

    @field_validator("method")
    @classmethod
    def known_method(cls, v: str) -> str:
        allowed = {"cash", "card", "upi", "netbanking", "pass", "wallet"}
        if v not in allowed:
            raise ValueError(f"method must be one of {sorted(allowed)}")
        return v


class TariffIn(BaseModel):
    facility_id: int
    vehicle_type_id: int
    name: str
    free_minutes: int = Field(ge=0, le=1440)
    first_hour_rate: float = Field(ge=0)
    subsequent_hour_rate: float = Field(ge=0)
    daily_cap: float = Field(ge=0)


# ===========================================================================
# Authentication
# ===========================================================================
@app.post("/api/auth/login")
def login(body: LoginIn):
    # privileged=True: we cannot SET ROLE before we know who this is, and the
    # password hash is not reachable under any application role's policies.
    with database.session_scope(privileged=True) as cur:
        cur.execute(
            "SELECT user_id, email, password_hash, full_name, role, facility_id, is_active "
            "FROM app_user WHERE email = %s",
            (body.email.strip(),),
        )
        user = cur.fetchone()

    if not user or not user["is_active"] or not verify_password(body.password, user["password_hash"]):
        # One message for both cases, so the response cannot be used to
        # enumerate which email addresses exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")

    return ok({
        "token": make_token(user),
        "user": {
            "user_id": user["user_id"],
            "name": user["full_name"],
            "email": str(user["email"]),
            "role": user["role"],
            "facility_id": user["facility_id"],
        },
    })


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return ok(user)


# ===========================================================================
# Reference data
# ===========================================================================
@app.get("/api/facilities")
def facilities(user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute(
            "SELECT facility_id, name, address_line, city, opens_at, closes_at, tax_rate_pct "
            "FROM facility WHERE is_active ORDER BY facility_id"
        )
        return ok(cur.fetchall())


@app.get("/api/vehicle-types")
def vehicle_types(user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("SELECT vehicle_type_id, code, name FROM vehicle_type ORDER BY vehicle_type_id")
        return ok(cur.fetchall())


@app.get("/api/floors")
def floors(facility_id: int = Query(...), user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute(
            "SELECT floor_id, level_number, name FROM floor WHERE facility_id = %s "
            "ORDER BY level_number",
            (facility_id,),
        )
        return ok(cur.fetchall())


@app.get("/api/tariffs")
def tariffs(user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("""
            SELECT t.tariff_id, t.facility_id, f.name AS facility_name,
                   t.vehicle_type_id, vt.name AS vehicle_type_name, vt.code AS vehicle_type_code,
                   t.name, t.free_minutes, t.first_hour_rate, t.subsequent_hour_rate,
                   t.daily_cap, t.effective_from, t.effective_to,
                   (t.effective_to IS NULL) AS in_force
              FROM tariff t
              JOIN facility f ON f.facility_id = t.facility_id
              JOIN vehicle_type vt ON vt.vehicle_type_id = t.vehicle_type_id
             ORDER BY t.effective_to NULLS FIRST, f.name, vt.vehicle_type_id
        """)
        return ok(cur.fetchall())


@app.post("/api/tariffs", status_code=201)
def create_tariff(body: TariffIn, user: dict = Depends(require_admin)):
    """Open a new tariff, closing the one it supersedes.

    Both statements run in one transaction: the exclusion constraint
    ex_tariff_no_overlap would reject the insert if the close had not
    committed, so they cannot be separated.
    """
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute(
                "UPDATE tariff SET effective_to = now() "
                "WHERE facility_id = %s AND vehicle_type_id = %s AND effective_to IS NULL",
                (body.facility_id, body.vehicle_type_id),
            )
            cur.execute("""
                INSERT INTO tariff (facility_id, vehicle_type_id, name, free_minutes,
                                    first_hour_rate, subsequent_hour_rate, daily_cap)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING tariff_id
            """, (body.facility_id, body.vehicle_type_id, body.name, body.free_minutes,
                  body.first_hour_rate, body.subsequent_hour_rate, body.daily_cap))
            return ok(cur.fetchone(), 201)
    except Exception as exc:
        raise as_http(exc)


@app.get("/api/pass-types")
def pass_types(user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("""
            SELECT pt.pass_type_id, pt.code, pt.name, pt.duration_days, pt.price,
                   pt.vehicle_type_id, vt.code AS vehicle_type_code, vt.name AS vehicle_type_name
              FROM pass_type pt JOIN vehicle_type vt ON vt.vehicle_type_id = pt.vehicle_type_id
             ORDER BY pt.duration_days, vt.vehicle_type_id
        """)
        return ok(cur.fetchall())


# ===========================================================================
# Slots - the live floor map and the search
# ===========================================================================
@app.get("/api/slots")
def slots(
    facility_id: int = Query(...),
    floor_id: Optional[int] = None,
    vehicle_type_id: Optional[int] = None,
    state: Optional[str] = None,
    user: dict = Depends(current_user),
):
    """Live occupancy, straight out of v_current_occupancy."""
    sql = ["SELECT * FROM v_current_occupancy WHERE facility_id = %s"]
    params = [facility_id]
    if floor_id:
        sql.append("AND floor_id = %s"); params.append(floor_id)
    if vehicle_type_id:
        sql.append("AND vehicle_type_id = %s"); params.append(vehicle_type_id)
    if state and state != "all":
        sql.append("AND slot_state = %s"); params.append(state)
    sql.append("ORDER BY level_number, zone_code, slot_code")

    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute(" ".join(sql), params)
        rows = cur.fetchall()
        cur.execute("""
            SELECT slot_state, count(*) AS n FROM v_current_occupancy
             WHERE facility_id = %s GROUP BY slot_state
        """, (facility_id,))
        counts = {r["slot_state"]: r["n"] for r in cur.fetchall()}
    return ok({"slots": rows, "counts": counts})


@app.get("/api/slots/free")
def free_slots(
    facility_id: int = Query(...),
    vehicle_type_id: Optional[int] = None,
    floor_id: Optional[int] = None,
    user: dict = Depends(current_user),
):
    sql = ["SELECT * FROM v_free_slots WHERE facility_id = %s"]
    params = [facility_id]
    if vehicle_type_id:
        sql.append("AND vehicle_type_id = %s"); params.append(vehicle_type_id)
    if floor_id:
        sql.append("AND floor_id = %s"); params.append(floor_id)
    sql.append("ORDER BY level_number, zone_code, slot_code")
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute(" ".join(sql), params)
        return ok(cur.fetchall())


# ===========================================================================
# Gate operations - thin wrappers over the transactional functions
# ===========================================================================
@app.post("/api/gate/entry")
def gate_entry(body: GateEntryIn, user: dict = Depends(require_staff)):
    """One call, one transaction, one row lock. See fn_gate_entry in 006."""
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute("SELECT * FROM fn_gate_entry(%s, %s, %s)",
                        (body.plate, body.facility_id, user["user_id"]))
            row = cur.fetchone()
            cur.execute("""
                SELECT v.plate_number, c.full_name AS customer_name, vt.name AS vehicle_type_name
                  FROM vehicle v
                  JOIN customer c ON c.customer_id = v.customer_id
                  JOIN vehicle_type vt ON vt.vehicle_type_id = v.vehicle_type_id
                 WHERE v.plate_number = %s
            """, (body.plate,))
            extra = cur.fetchone() or {}
            cur.execute("SELECT entry_time FROM parking_session WHERE session_id = %s",
                        (row["session_id"],))
            row.update(extra)
            row.update(cur.fetchone() or {})
            return ok(row)
    except Exception as exc:
        raise as_http(exc)


@app.get("/api/gate/lookup")
def gate_lookup(q: str = Query(min_length=3), user: dict = Depends(require_staff)):
    """Preview an open session before committing to the exit.

    running_charge comes from fn_calculate_charge, the same function the final
    bill uses, so the figure the operator quotes is the figure that is billed.
    """
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("""
            SELECT ps.session_id, ps.ticket_no, ps.entry_time, ps.pass_id,
                   s.code AS slot_code, v.plate_number, vt.name AS vehicle_type_name,
                   c.full_name AS customer_name, c.phone AS customer_phone,
                   fl.facility_id, f.tax_rate_pct,
                   fn_calculate_charge(ps.session_id) AS running_charge,
                   FLOOR(EXTRACT(EPOCH FROM (now() - ps.entry_time))/60)::int AS minutes_so_far
              FROM parking_session ps
              JOIN slot s ON s.slot_id = ps.slot_id
              JOIN zone z ON z.zone_id = s.zone_id
              JOIN floor fl ON fl.floor_id = z.floor_id
              JOIN facility f ON f.facility_id = fl.facility_id
              JOIN vehicle v ON v.vehicle_id = ps.vehicle_id
              JOIN vehicle_type vt ON vt.vehicle_type_id = ps.vehicle_type_id
              JOIN customer c ON c.customer_id = v.customer_id
             WHERE ps.exit_time IS NULL
               AND (ps.ticket_no = %s OR v.plate_number = %s)
             LIMIT 1
        """, (q.strip().upper(), q.strip().upper().replace(" ", "").replace("-", "")))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f'No vehicle is currently parked under "{q}".')
    return ok(row)


@app.post("/api/gate/exit")
def gate_exit(body: GateExitIn, user: dict = Depends(require_staff)):
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute("SELECT * FROM fn_gate_exit(%s, %s)", (body.lookup, user["user_id"]))
            return ok(cur.fetchone())
    except Exception as exc:
        raise as_http(exc)


@app.get("/api/sessions")
def sessions(
    facility_id: Optional[int] = None,
    active_only: bool = False,
    limit: int = Query(50, le=500),
    user: dict = Depends(current_user),
):
    sql = ["SELECT * FROM v_session_duration WHERE 1=1"]
    params = []
    if facility_id:
        sql.append("AND facility_id = %s"); params.append(facility_id)
    if active_only:
        sql.append("AND is_active")
    sql.append("ORDER BY entry_time DESC LIMIT %s"); params.append(limit)
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute(" ".join(sql), params)
        return ok(cur.fetchall())


# ===========================================================================
# Reservations
# ===========================================================================
@app.get("/api/reservations")
def reservations(status_filter: Optional[str] = Query(None, alias="status"),
                 user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        # Idempotent sweep, per BUSINESS RULE 4. Safe to run on every read.
        # SAVEPOINT protects the outer transaction: if the customer role lacks
        # EXECUTE on this function, the error rolls back only the savepoint so
        # the subsequent SELECT can still run (psycopg3 aborts the whole
        # transaction on any unhandled exception, including a caught one).
        try:
            cur.execute("SAVEPOINT before_expire")
            cur.execute("SELECT fn_expire_stale_reservations()")
            cur.execute("RELEASE SAVEPOINT before_expire")
        except psycopg.Error:
            cur.execute("ROLLBACK TO SAVEPOINT before_expire")
        sql = ["""
            SELECT r.reservation_id, r.status, r.reserved_from, r.reserved_until, r.created_at,
                   c.customer_id, c.full_name AS customer_name, c.phone,
                   v.plate_number, vt.name AS vehicle_type_name,
                   s.slot_id, s.code AS slot_code, z.code AS zone_code,
                   fl.name AS floor_name, fl.facility_id
              FROM reservation r
              JOIN customer c ON c.customer_id = r.customer_id
              JOIN vehicle  v ON v.vehicle_id  = r.vehicle_id
              JOIN vehicle_type vt ON vt.vehicle_type_id = v.vehicle_type_id
              JOIN slot  s  ON s.slot_id  = r.slot_id
              JOIN zone  z  ON z.zone_id  = s.zone_id
              JOIN floor fl ON fl.floor_id = z.floor_id
             WHERE 1=1
        """]
        params = []
        if status_filter and status_filter != "all":
            sql.append("AND r.status = %s::reservation_status"); params.append(status_filter)
        sql.append("ORDER BY r.reserved_from DESC LIMIT 200")
        cur.execute(" ".join(sql), params)
        return ok(cur.fetchall())


@app.post("/api/reservations", status_code=201)
def create_reservation(body: ReservationIn, user: dict = Depends(current_user)):
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute("""
                INSERT INTO reservation (customer_id, vehicle_id, slot_id, reserved_from, reserved_until)
                VALUES (%s,%s,%s,%s,%s) RETURNING reservation_id, status
            """, (body.customer_id, body.vehicle_id, body.slot_id,
                  body.reserved_from, body.reserved_until))
            return ok(cur.fetchone(), 201)
    except Exception as exc:
        raise as_http(exc)


@app.patch("/api/reservations/{reservation_id}")
def update_reservation(reservation_id: int, new_status: str = Query(..., alias="status"),
                       user: dict = Depends(current_user)):
    if new_status not in ("held", "confirmed", "cancelled"):
        raise HTTPException(400, "Status must be held, confirmed or cancelled.")
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute(
                "UPDATE reservation SET status = %s::reservation_status "
                "WHERE reservation_id = %s RETURNING reservation_id, status",
                (new_status, reservation_id),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Reservation not found, or not yours to change.")
        return ok(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise as_http(exc)


# ===========================================================================
# Passes
# ===========================================================================
@app.get("/api/passes")
def passes(user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("SELECT * FROM v_pass_usage ORDER BY valid_to DESC LIMIT 200")
        return ok(cur.fetchall())


@app.post("/api/passes", status_code=201)
def buy_pass(body: PassIn, user: dict = Depends(current_user)):
    """Sell a pass. Duration and price are read from pass_type, never from the
    client, so a caller cannot buy a month for the price of a day."""
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute("SELECT duration_days, price FROM pass_type WHERE pass_type_id = %s",
                        (body.pass_type_id,))
            pt = cur.fetchone()
            if not pt:
                raise HTTPException(404, "That pass product does not exist.")
            cur.execute("""
                INSERT INTO parking_pass (customer_id, vehicle_id, pass_type_id, facility_id,
                                          valid_from, valid_to, price_paid)
                VALUES (%s,%s,%s,%s,%s, %s + (%s || ' days')::interval, %s)
                RETURNING pass_id, valid_from, valid_to, price_paid
            """, (body.customer_id, body.vehicle_id, body.pass_type_id, body.facility_id,
                  body.valid_from, body.valid_from, pt["duration_days"], pt["price"]))
            return ok(cur.fetchone(), 201)
    except HTTPException:
        raise
    except Exception as exc:
        raise as_http(exc)


@app.delete("/api/passes/{pass_id}")
def cancel_pass(pass_id: int, user: dict = Depends(current_user)):
    """Cancellation is a soft close - the row stays for the usage report."""
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute(
                "UPDATE parking_pass SET cancelled_at = now() "
                "WHERE pass_id = %s AND cancelled_at IS NULL RETURNING pass_id",
                (pass_id,),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Pass not found, or already cancelled.")
        return ok(row)
    except HTTPException:
        raise
    except Exception as exc:
        raise as_http(exc)


# ===========================================================================
# Billing and payments
# ===========================================================================
@app.get("/api/bills")
def bills(status_filter: Optional[str] = Query(None, alias="status"),
          limit: int = Query(100, le=500), user: dict = Depends(current_user)):
    sql = ["""
        SELECT b.bill_id, b.session_id, b.billable_minutes, b.base_amount, b.tax_amount,
               b.total_amount, b.status, b.generated_at,
               ps.ticket_no, ps.entry_time, ps.exit_time,
               v.plate_number, c.full_name AS customer_name,
               s.code AS slot_code, fl.facility_id, f.name AS facility_name,
               COALESCE(pd.paid, 0) AS amount_paid,
               b.total_amount - COALESCE(pd.paid, 0) AS amount_due
          FROM bill b
          JOIN parking_session ps ON ps.session_id = b.session_id
          JOIN vehicle  v  ON v.vehicle_id = ps.vehicle_id
          JOIN customer c  ON c.customer_id = v.customer_id
          JOIN slot     s  ON s.slot_id = ps.slot_id
          JOIN zone     z  ON z.zone_id = s.zone_id
          JOIN floor    fl ON fl.floor_id = z.floor_id
          JOIN facility f  ON f.facility_id = fl.facility_id
          LEFT JOIN LATERAL (SELECT SUM(amount) AS paid FROM payment
                              WHERE bill_id = b.bill_id) pd ON TRUE
         WHERE 1=1
    """]
    params = []
    if status_filter and status_filter != "all":
        sql.append("AND b.status = %s::bill_status"); params.append(status_filter)
    sql.append("ORDER BY b.generated_at DESC LIMIT %s"); params.append(limit)
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute(" ".join(sql), params)
        rows = cur.fetchall()
        cur.execute("""
            SELECT b.status, count(*) AS n, COALESCE(SUM(b.total_amount),0) AS amount
              FROM bill b GROUP BY b.status
        """)
        summary = {r["status"]: {"count": r["n"], "amount": r["amount"]} for r in cur.fetchall()}
    return ok({"bills": rows, "summary": summary})


@app.get("/api/bills/{bill_id}")
def bill_detail(bill_id: int, user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("""
            SELECT b.*, ps.ticket_no, ps.entry_time, ps.exit_time,
                   v.plate_number, vt.name AS vehicle_type_name,
                   c.full_name AS customer_name, c.phone AS customer_phone,
                   s.code AS slot_code, f.name AS facility_name,
                   f.address_line, f.city, f.tax_rate_pct,
                   t.name AS tariff_name, t.first_hour_rate, t.subsequent_hour_rate,
                   t.daily_cap, t.free_minutes
              FROM bill b
              JOIN parking_session ps ON ps.session_id = b.session_id
              JOIN vehicle v  ON v.vehicle_id = ps.vehicle_id
              JOIN vehicle_type vt ON vt.vehicle_type_id = ps.vehicle_type_id
              JOIN customer c ON c.customer_id = v.customer_id
              JOIN slot  s  ON s.slot_id = ps.slot_id
              JOIN zone  z  ON z.zone_id = s.zone_id
              JOIN floor fl ON fl.floor_id = z.floor_id
              JOIN facility f ON f.facility_id = fl.facility_id
              JOIN tariff t ON t.tariff_id = b.tariff_id
             WHERE b.bill_id = %s
        """, (bill_id,))
        bill = cur.fetchone()
        if not bill:
            raise HTTPException(404, "Bill not found.")
        cur.execute(
            "SELECT payment_id, amount, method, reference_no, paid_at "
            "FROM payment WHERE bill_id = %s ORDER BY paid_at", (bill_id,))
        bill["payments"] = cur.fetchall()
    return ok(bill)


@app.post("/api/payments", status_code=201)
def record_payment(body: PaymentIn, user: dict = Depends(require_staff)):
    """Record a receipt. No gateway, no card data - method, reference, amount.

    bill.status is not set here: trg_payment_sync_bill_status derives it from
    the sum of payments, so a bill cannot be marked paid without money behind it.
    """
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute("""
                INSERT INTO payment (bill_id, amount, method, reference_no, received_by)
                VALUES (%s,%s,%s::payment_method,%s,%s)
                RETURNING payment_id, bill_id, amount, method, paid_at
            """, (body.bill_id, body.amount, body.method, body.reference_no, user["user_id"]))
            row = cur.fetchone()
            cur.execute("SELECT status, total_amount FROM bill WHERE bill_id = %s", (body.bill_id,))
            row.update(cur.fetchone() or {})
            return ok(row, 201)
    except Exception as exc:
        raise as_http(exc)


# ===========================================================================
# Customers and vehicles
# ===========================================================================
@app.get("/api/customers")
def customers(q: Optional[str] = None, user: dict = Depends(current_user)):
    sql = ["""
        SELECT c.customer_id, c.full_name, c.phone, c.email, c.created_at,
               COUNT(v.vehicle_id) AS vehicle_count
          FROM customer c
          LEFT JOIN vehicle v ON v.customer_id = c.customer_id
         WHERE 1=1
    """]
    params = []
    if q:
        sql.append("AND (c.full_name ILIKE %s OR c.phone LIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    sql.append("GROUP BY c.customer_id ORDER BY c.full_name")
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute(" ".join(sql), params)
        return ok(cur.fetchall())


@app.post("/api/customers", status_code=201)
def create_customer(body: CustomerIn, user: dict = Depends(require_staff)):
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute(
                "INSERT INTO customer (full_name, phone, email) VALUES (%s,%s,%s) "
                "RETURNING customer_id, full_name, phone, email",
                (body.full_name.strip(), body.phone, (body.email or None)),
            )
            return ok(cur.fetchone(), 201)
    except Exception as exc:
        raise as_http(exc)


@app.get("/api/vehicles")
def vehicles(customer_id: Optional[int] = None, q: Optional[str] = None,
             user: dict = Depends(current_user)):
    sql = ["""
        SELECT v.vehicle_id, v.plate_number, v.make, v.model, v.colour,
               v.vehicle_type_id, vt.name AS vehicle_type_name, vt.code AS vehicle_type_code,
               c.customer_id, c.full_name AS customer_name, c.phone,
               EXISTS (SELECT 1 FROM parking_session ps
                        WHERE ps.vehicle_id = v.vehicle_id AND ps.exit_time IS NULL) AS is_parked
          FROM vehicle v
          JOIN vehicle_type vt ON vt.vehicle_type_id = v.vehicle_type_id
          JOIN customer c ON c.customer_id = v.customer_id
         WHERE 1=1
    """]
    params = []
    if customer_id:
        sql.append("AND v.customer_id = %s"); params.append(customer_id)
    if q:
        sql.append("AND v.plate_number ILIKE %s"); params.append(f"%{q.upper()}%")
    sql.append("ORDER BY v.plate_number")
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute(" ".join(sql), params)
        return ok(cur.fetchall())


@app.post("/api/vehicles", status_code=201)
def create_vehicle(body: VehicleIn, user: dict = Depends(current_user)):
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute("""
                INSERT INTO vehicle (customer_id, plate_number, vehicle_type_id, make, model, colour)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING vehicle_id, plate_number
            """, (body.customer_id, body.plate_number, body.vehicle_type_id,
                  body.make, body.model, body.colour))
            return ok(cur.fetchone(), 201)
    except Exception as exc:
        raise as_http(exc)


@app.delete("/api/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: int, user: dict = Depends(current_user)):
    try:
        with database.session_scope(user["user_id"], user["role"]) as cur:
            cur.execute("DELETE FROM vehicle WHERE vehicle_id = %s RETURNING vehicle_id",
                        (vehicle_id,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Vehicle not found.")
        return ok(row)
    except HTTPException:
        raise
    except Exception as exc:
        # A vehicle with parking history is protected by ON DELETE RESTRICT.
        raise as_http(exc)


# ===========================================================================
# Reports - one endpoint per view named in the project statement
# ===========================================================================
@app.get("/api/reports/occupancy")
def report_occupancy(facility_id: int = Query(...), user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("""
            SELECT floor_name, level_number, zone_code,
                   COUNT(*)                                            AS total,
                   COUNT(*) FILTER (WHERE slot_state = 'occupied')      AS occupied,
                   COUNT(*) FILTER (WHERE slot_state = 'free')          AS free,
                   COUNT(*) FILTER (WHERE slot_state = 'reserved')      AS reserved,
                   COUNT(*) FILTER (WHERE slot_state = 'out_of_service')AS out_of_service,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE slot_state='occupied') / COUNT(*), 1)
                                                                        AS occupancy_pct
              FROM v_current_occupancy
             WHERE facility_id = %s
             GROUP BY floor_name, level_number, zone_code
             ORDER BY level_number, zone_code
        """, (facility_id,))
        by_zone = cur.fetchall()
        cur.execute("""
            SELECT vehicle_type_name,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE slot_state='occupied') AS occupied
              FROM v_current_occupancy WHERE facility_id = %s
             GROUP BY vehicle_type_name ORDER BY total DESC
        """, (facility_id,))
        by_type = cur.fetchall()
    return ok({"by_zone": by_zone, "by_type": by_type})


@app.get("/api/reports/peak-hours")
def report_peak(facility_id: int = Query(...), user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute(
            "SELECT * FROM v_peak_hours WHERE facility_id = %s ORDER BY hour_of_day",
            (facility_id,))
        return ok(cur.fetchall())


@app.get("/api/reports/revenue")
def report_revenue(facility_id: int = Query(...), days: int = Query(30, le=365),
                   user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("""
            SELECT * FROM v_revenue_daily
             WHERE facility_id = %s AND revenue_date >= CURRENT_DATE - %s::int
             ORDER BY revenue_date
        """, (facility_id, days))
        daily = cur.fetchall()
        cur.execute("""
            SELECT p.method, COUNT(*) AS n, SUM(p.amount) AS amount
              FROM payment p
              JOIN bill b ON b.bill_id = p.bill_id
              JOIN parking_session ps ON ps.session_id = b.session_id
              JOIN slot s ON s.slot_id = ps.slot_id
              JOIN zone z ON z.zone_id = s.zone_id
              JOIN floor fl ON fl.floor_id = z.floor_id
             WHERE fl.facility_id = %s
             GROUP BY p.method ORDER BY amount DESC
        """, (facility_id,))
        by_method = cur.fetchall()
    return ok({"daily": daily, "by_method": by_method})


@app.get("/api/reports/duration")
def report_duration(facility_id: int = Query(...), user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("""
            SELECT duration_bucket, COUNT(*) AS sessions,
                   ROUND(AVG(duration_minutes)) AS avg_minutes,
                   ROUND(COALESCE(SUM(total_amount),0), 2) AS revenue
              FROM v_session_duration
             WHERE facility_id = %s AND NOT is_active
             GROUP BY duration_bucket
             ORDER BY CASE duration_bucket
                        WHEN 'under_30m' THEN 1 WHEN '30m_2h' THEN 2
                        WHEN '2h_8h' THEN 3 WHEN '8h_24h' THEN 4 ELSE 5 END
        """, (facility_id,))
        return ok(cur.fetchall())


@app.get("/api/reports/pass-usage")
def report_pass_usage(user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("SELECT * FROM v_pass_usage ORDER BY pass_state, valid_to DESC")
        return ok(cur.fetchall())


@app.get("/api/reports/violations")
def report_violations(user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("SELECT * FROM v_violations ORDER BY detected_at DESC LIMIT 200")
        rows = cur.fetchall()
        cur.execute("""
            SELECT kind, COUNT(*) AS n,
                   COUNT(*) FILTER (WHERE is_resolved) AS resolved,
                   COALESCE(SUM(penalty_amount),0) AS penalties
              FROM v_violations GROUP BY kind ORDER BY n DESC
        """)
        summary = cur.fetchall()
    return ok({"violations": rows, "summary": summary})


@app.get("/api/reports/free-slots")
def report_free_slots(facility_id: int = Query(...), user: dict = Depends(current_user)):
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("""
            SELECT floor_name, level_number, zone_code, vehicle_type_name,
                   COUNT(*) AS free_count,
                   string_agg(slot_code, ', ' ORDER BY slot_code) AS slot_codes
              FROM v_free_slots WHERE facility_id = %s
             GROUP BY floor_name, level_number, zone_code, vehicle_type_name
             ORDER BY level_number, zone_code, vehicle_type_name
        """, (facility_id,))
        return ok(cur.fetchall())


@app.get("/api/dashboard")
def dashboard(facility_id: int = Query(...), user: dict = Depends(current_user)):
    """Every figure here is a query result. Nothing on this endpoint is a
    constant, an estimate or a placeholder."""
    with database.session_scope(user["user_id"], user["role"]) as cur:
        cur.execute("""
            SELECT COUNT(*)                                        AS total_slots,
                   COUNT(*) FILTER (WHERE slot_state='occupied')   AS occupied,
                   COUNT(*) FILTER (WHERE slot_state='free')       AS free,
                   COUNT(*) FILTER (WHERE slot_state='reserved')   AS reserved,
                   COUNT(*) FILTER (WHERE slot_state='out_of_service') AS out_of_service
              FROM v_current_occupancy WHERE facility_id = %s
        """, (facility_id,))
        slots_row = cur.fetchone()

        cur.execute("""
            SELECT COALESCE(SUM(b.total_amount),0) AS billed_today,
                   COALESCE((SELECT SUM(p.amount) FROM payment p
                              JOIN bill b2 ON b2.bill_id = p.bill_id
                              JOIN parking_session ps2 ON ps2.session_id = b2.session_id
                              JOIN slot s2 ON s2.slot_id = ps2.slot_id
                              JOIN zone z2 ON z2.zone_id = s2.zone_id
                              JOIN floor f2 ON f2.floor_id = z2.floor_id
                             WHERE f2.facility_id = %s
                               AND p.paid_at >= date_trunc('day', now())), 0) AS collected_today,
                   COUNT(*) AS bills_today
              FROM bill b
              JOIN parking_session ps ON ps.session_id = b.session_id
              JOIN slot s ON s.slot_id = ps.slot_id
              JOIN zone z ON z.zone_id = s.zone_id
              JOIN floor fl ON fl.floor_id = z.floor_id
             WHERE fl.facility_id = %s AND b.generated_at >= date_trunc('day', now())
        """, (facility_id, facility_id))
        money = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS entries_today
              FROM parking_session ps
              JOIN slot s ON s.slot_id = ps.slot_id
              JOIN zone z ON z.zone_id = s.zone_id
              JOIN floor fl ON fl.floor_id = z.floor_id
             WHERE fl.facility_id = %s AND ps.entry_time >= date_trunc('day', now())
        """, (facility_id,))
        entries = cur.fetchone()

        cur.execute("""
            SELECT COALESCE(SUM(b.total_amount - COALESCE(pd.paid,0)),0) AS outstanding
              FROM bill b
              LEFT JOIN LATERAL (SELECT SUM(amount) AS paid FROM payment WHERE bill_id=b.bill_id) pd ON TRUE
              JOIN parking_session ps ON ps.session_id = b.session_id
              JOIN slot s ON s.slot_id = ps.slot_id
              JOIN zone z ON z.zone_id = s.zone_id
              JOIN floor fl ON fl.floor_id = z.floor_id
             WHERE fl.facility_id = %s AND b.status <> 'paid'
        """, (facility_id,))
        outstanding = cur.fetchone()

        cur.execute("""
            SELECT (b.generated_at AT TIME ZONE 'Asia/Kolkata')::date AS d,
                   SUM(b.total_amount) AS revenue
              FROM bill b
              JOIN parking_session ps ON ps.session_id = b.session_id
              JOIN slot s ON s.slot_id = ps.slot_id
              JOIN zone z ON z.zone_id = s.zone_id
              JOIN floor fl ON fl.floor_id = z.floor_id
             WHERE fl.facility_id = %s AND b.generated_at >= now() - INTERVAL '14 days'
             GROUP BY 1 ORDER BY 1
        """, (facility_id,))
        trend = cur.fetchall()

        cur.execute("""
            SELECT ps.ticket_no, v.plate_number, s.code AS slot_code,
                   ps.entry_time, ps.exit_time, (ps.exit_time IS NULL) AS is_active
              FROM parking_session ps
              JOIN vehicle v ON v.vehicle_id = ps.vehicle_id
              JOIN slot s ON s.slot_id = ps.slot_id
              JOIN zone z ON z.zone_id = s.zone_id
              JOIN floor fl ON fl.floor_id = z.floor_id
             WHERE fl.facility_id = %s
             -- exit_time > entry_time is guaranteed by ck_session_exit_after_entry,
             -- so COALESCE is the same ordering as GREATEST and is cheaper.
             ORDER BY COALESCE(ps.exit_time, ps.entry_time) DESC
             LIMIT 8
        """, (facility_id,))
        recent = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*) AS open_violations FROM v_violations WHERE NOT is_resolved
        """)
        viol = cur.fetchone()

    return ok({
        "slots": slots_row,
        "money": money,
        "entries": entries,
        "outstanding": outstanding,
        "trend": trend,
        "recent": recent,
        "violations": viol,
    })


# ===========================================================================
# Static front-end. Mounted last so it never shadows an /api route.
# ===========================================================================
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
