"""API tests against a real PostgreSQL database.

Run against a disposable copy built from the migrations, never the demo DB:

    SMARTPARK_DB=smartpark_test ./setup.sh --reset
    SMARTPARK_DATABASE_URL=postgresql:///smartpark_test ./.venv/bin/pytest tests/test_api.py -q

The tests write data (customers, bookings, bay changes) and clean up what they
can, but the audit trail is append-only by design.
"""
import datetime as dt
import os

import pytest

os.environ.setdefault("SMARTPARK_DATABASE_URL", "postgresql:///smartpark_test")

from fastapi.testclient import TestClient  # noqa: E402

from api import db as database  # noqa: E402
from api.main import app  # noqa: E402

PASSWORD = "Parking@123"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return login(client, "admin@smartpark.in")


@pytest.fixture(scope="module")
def op1(client):
    return login(client, "ops.central@smartpark.in")   # facility 1


@pytest.fixture(scope="module")
def op2(client):
    return login(client, "ops.river@smartpark.in")     # facility 2


@pytest.fixture(scope="module")
def rahul(client):
    return login(client, "rahul.sharma@example.com")   # customer


def sql(query, params=()):
    """Read test fixtures straight from the database, as the table owner."""
    with database.session_scope(privileged=True) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def free_bay(facility_id):
    return sql("""
        SELECT s.slot_id, s.vehicle_type_id FROM slot s
          JOIN zone z ON z.zone_id = s.zone_id JOIN floor fl ON fl.floor_id = z.floor_id
         WHERE fl.facility_id = %s AND s.is_active
           AND NOT EXISTS (SELECT 1 FROM parking_session ps
                            WHERE ps.slot_id = s.slot_id AND ps.exit_time IS NULL)
           AND NOT EXISTS (SELECT 1 FROM reservation r WHERE r.slot_id = s.slot_id
                            AND r.status IN ('held','confirmed') AND r.reserved_until > now())
         ORDER BY s.slot_id LIMIT 1""", (facility_id,))[0]


def window(days_ahead):
    start = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days_ahead)
    return start.isoformat(), (start + dt.timedelta(hours=2)).isoformat()


# --------------------------------------------------------------------------
# Health and errors
# --------------------------------------------------------------------------
def test_health_needs_no_sign_in(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "up"}


def test_errors_are_plain_english(client, admin):
    assert client.get("/api/customers").status_code == 401
    r = client.post("/api/auth/login", json={"email": "admin@smartpark.in", "password": "nope"})
    assert r.status_code == 401 and r.json()["detail"] == "Email or password is incorrect."


# --------------------------------------------------------------------------
# Customers: create, edit, delete
# --------------------------------------------------------------------------
def test_customer_lifecycle(client, admin, op1):
    bad = client.post("/api/customers", headers=op1,
                      json={"full_name": "Test Person", "phone": "9000000001", "email": "not-an-email"})
    assert bad.status_code == 422

    made = client.post("/api/customers", headers=op1,
                       json={"full_name": "Test Person", "phone": "9000000001", "email": ""})
    assert made.status_code == 201, made.text
    cid = made.json()["customer_id"]
    assert made.json()["email"] is None

    edited = client.patch(f"/api/customers/{cid}", headers=op1,
                          json={"full_name": "  Test Person Renamed ", "email": "tp@example.com"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["full_name"] == "Test Person Renamed"

    taken_phone = sql("SELECT phone FROM customer WHERE customer_id <> %s LIMIT 1", (cid,))[0]["phone"]
    clash = client.patch(f"/api/customers/{cid}", headers=op1, json={"phone": taken_phone})
    assert clash.status_code == 409
    assert clash.json() == {"detail": "A customer with that phone number already exists.",
                            "rule": "customer_phone_key"}

    assert client.patch(f"/api/customers/{cid}", headers=op1, json={}).status_code == 422
    assert client.delete(f"/api/customers/{cid}", headers=op1).status_code == 403
    assert client.delete(f"/api/customers/{cid}", headers=admin).status_code == 200
    assert client.delete(f"/api/customers/{cid}", headers=admin).status_code == 404


def test_customer_with_vehicles_cannot_be_deleted(client, admin):
    r = client.delete("/api/customers/1", headers=admin)
    assert r.status_code == 409
    assert r.json()["detail"] == "This record still has vehicles on file, so it cannot be deleted."


# --------------------------------------------------------------------------
# Vehicles
# --------------------------------------------------------------------------
def test_vehicle_edit_respects_ownership(client, rahul):
    mine = client.get("/api/vehicles", headers=rahul).json()[0]
    r = client.patch(f"/api/vehicles/{mine['vehicle_id']}", headers=rahul, json={"colour": "Teal"})
    assert r.status_code == 200 and r.json()["colour"] == "Teal"

    theirs = sql("SELECT vehicle_id FROM vehicle WHERE customer_id <> 1 LIMIT 1")[0]["vehicle_id"]
    r = client.patch(f"/api/vehicles/{theirs}", headers=rahul, json={"colour": "Red"})
    assert r.status_code == 404


def test_vehicle_with_history_reports_the_real_reason(client, admin):
    # Before the error mapper was rewritten this case said "The vehicle type
    # does not match the vehicle on file", naming the wrong rule entirely.
    vid = sql("""SELECT ps.vehicle_id FROM parking_session ps
                  WHERE NOT EXISTS (SELECT 1 FROM parking_pass pp WHERE pp.vehicle_id = ps.vehicle_id)
                    AND NOT EXISTS (SELECT 1 FROM reservation r WHERE r.vehicle_id = ps.vehicle_id)
                    AND NOT EXISTS (SELECT 1 FROM violation vi WHERE vi.vehicle_id = ps.vehicle_id)
                  LIMIT 1""")[0]["vehicle_id"]
    r = client.delete(f"/api/vehicles/{vid}", headers=admin)
    assert r.status_code == 409
    assert r.json()["detail"] == "This record still has parking history, so it cannot be deleted."


# --------------------------------------------------------------------------
# Reservations: the integrity rules added in migration 013
# --------------------------------------------------------------------------
def test_reservation_rejects_someone_elses_vehicle(client, admin):
    v = sql("SELECT vehicle_id, customer_id, vehicle_type_id FROM vehicle ORDER BY vehicle_id LIMIT 1")[0]
    bay = sql("SELECT slot_id FROM slot WHERE vehicle_type_id = %s AND is_active LIMIT 1",
              (v["vehicle_type_id"],))[0]
    start, end = window(90)
    r = client.post("/api/reservations", headers=admin, json={
        "customer_id": v["customer_id"] + 1, "vehicle_id": v["vehicle_id"],
        "slot_id": bay["slot_id"], "reserved_from": start, "reserved_until": end})
    assert r.status_code == 409 and r.json()["rule"] == "fk_reservation_vehicle_owner"


def test_reservation_rejects_wrong_bay_type(client, admin):
    v = sql("SELECT vehicle_id, customer_id, vehicle_type_id FROM vehicle ORDER BY vehicle_id LIMIT 1")[0]
    bay = sql("SELECT slot_id FROM slot WHERE vehicle_type_id <> %s AND is_active LIMIT 1",
              (v["vehicle_type_id"],))[0]
    start, end = window(91)
    r = client.post("/api/reservations", headers=admin, json={
        "customer_id": v["customer_id"], "vehicle_id": v["vehicle_id"],
        "slot_id": bay["slot_id"], "reserved_from": start, "reserved_until": end})
    assert r.status_code == 409 and r.json()["rule"] == "fk_reservation_slot_type_match"


def test_customer_can_list_reservations(client, rahul):
    # Regression: this was a 500 until the SAVEPOINT fix around the expiry sweep.
    r = client.get("/api/reservations", headers=rahul)
    assert r.status_code == 200
    assert {row["customer_id"] for row in r.json()} <= {1}


# --------------------------------------------------------------------------
# Bay servicing
# --------------------------------------------------------------------------
def test_bay_service_round_trip(client, op1, admin):
    bay = free_bay(1)
    sid = bay["slot_id"]

    assert client.patch(f"/api/slots/{sid}/service", headers=op1,
                        json={"in_service": False}).status_code == 422

    out = client.patch(f"/api/slots/{sid}/service", headers=op1,
                       json={"in_service": False, "note": "Drain cover lifted"})
    assert out.status_code == 200, out.text
    assert out.json()["slot_state"] == "out_of_service"
    assert out.json()["service_note"] == "Drain cover lifted"

    owner = sql("SELECT customer_id, vehicle_id FROM vehicle WHERE vehicle_type_id = %s LIMIT 1",
                (bay["vehicle_type_id"],))[0]
    start, end = window(92)
    booked = client.post("/api/reservations", headers=admin, json={
        **owner, "slot_id": sid, "reserved_from": start, "reserved_until": end})
    assert booked.status_code == 409 and booked.json()["rule"] == "trg_reservation_prepare"

    back = client.patch(f"/api/slots/{sid}/service", headers=op1, json={"in_service": True})
    assert back.status_code == 200 and back.json()["service_note"] is None

    trail = client.get("/api/audit?table=slot&limit=5", headers=admin).json()
    assert any(a["row_id"] == sid and a["actor_role"] == "operator" for a in trail)


def test_bay_service_refusals(client, op1, op2, rahul):
    occupied = sql("""SELECT ps.slot_id FROM parking_session ps
                        JOIN slot s ON s.slot_id = ps.slot_id JOIN zone z ON z.zone_id = s.zone_id
                        JOIN floor fl ON fl.floor_id = z.floor_id
                       WHERE ps.exit_time IS NULL AND fl.facility_id = 1 LIMIT 1""")[0]["slot_id"]
    r = client.patch(f"/api/slots/{occupied}/service", headers=op1,
                     json={"in_service": False, "note": "x"})
    assert r.status_code == 409 and "has a vehicle in it" in r.json()["detail"]

    elsewhere = free_bay(1)["slot_id"]
    r = client.patch(f"/api/slots/{elsewhere}/service", headers=op2,
                     json={"in_service": False, "note": "x"})
    assert r.status_code == 403 and r.json()["detail"] == "You can only manage bays at your own facility."

    assert client.patch(f"/api/slots/{elsewhere}/service", headers=rahul,
                        json={"in_service": False, "note": "x"}).status_code == 403


# --------------------------------------------------------------------------
# Payments
# --------------------------------------------------------------------------
def test_payment_cannot_exceed_the_balance(client, op1):
    bill = sql("""SELECT b.bill_id, b.total_amount FROM bill b
                    JOIN parking_session ps ON ps.session_id = b.session_id
                    JOIN slot s ON s.slot_id = ps.slot_id JOIN zone z ON z.zone_id = s.zone_id
                    JOIN floor fl ON fl.floor_id = z.floor_id
                   WHERE fl.facility_id = 1 AND b.status = 'unpaid' AND b.total_amount > 2
                     AND NOT EXISTS (SELECT 1 FROM payment p WHERE p.bill_id = b.bill_id)
                   LIMIT 1""")[0]
    total = float(bill["total_amount"])
    r = client.post("/api/payments", headers=op1,
                    json={"bill_id": bill["bill_id"], "amount": total + 1, "method": "cash"})
    assert r.status_code == 409 and r.json()["rule"] == "trg_payment_within_balance"
    assert f"₹{total:.2f} still owed" in r.json()["detail"]

    r = client.post("/api/payments", headers=op1,
                    json={"bill_id": bill["bill_id"], "amount": total, "method": "upi"})
    assert r.status_code == 201 and r.json()["status"] == "paid"


def test_a_free_stay_is_settled_not_unpaid():
    # A ₹0 bill can never receive a payment, so it must not be left "unpaid".
    stuck = sql("SELECT count(*) AS n FROM bill WHERE total_amount = 0 AND status = 'unpaid'")[0]["n"]
    assert stuck == 0


# --------------------------------------------------------------------------
# Ledger, activity, audit, reports, dashboard
# --------------------------------------------------------------------------
def test_payments_are_scoped_to_the_operators_facility(client, op2, rahul):
    r = client.get("/api/payments?days=60", headers=op2)
    assert r.status_code == 200
    rows = r.json()["payments"]
    assert rows and {p["facility_id"] for p in rows} == {2}
    assert client.get("/api/payments", headers=rahul).status_code == 403


def test_activity_feed_is_newest_first_and_private(client, rahul):
    rows = client.get("/api/activity?facility_id=1&limit=50", headers=rahul).json()
    mine = {v["plate_number"] for v in client.get("/api/vehicles", headers=rahul).json()}
    assert rows and {r["plate_number"] for r in rows} <= mine
    times = [r["occurred_at"] for r in rows]
    assert times == sorted(times, reverse=True)


def test_audit_is_admin_only(client, op1):
    assert client.get("/api/audit", headers=op1).status_code == 403


def test_vehicle_history_report(client, admin):
    plate = sql("""SELECT v.plate_number FROM parking_session ps
                     JOIN vehicle v ON v.vehicle_id = ps.vehicle_id LIMIT 1""")[0]["plate_number"]
    r = client.get(f"/api/reports/vehicle-history?plate={plate.lower()}", headers=admin)
    assert r.status_code == 200
    body = r.json()
    assert body["vehicle"]["plate_number"] == plate and body["totals"]["stays"] == len(body["stays"]) > 0
    assert client.get("/api/reports/vehicle-history?plate=ZZ00ZZ0000", headers=admin).status_code == 404


def test_dashboard_figures_are_scoped(client, admin):
    d = client.get("/api/dashboard?facility_id=2", headers=admin).json()
    expected = sql("SELECT count(*) AS n FROM v_violations WHERE NOT is_resolved AND facility_id = 2")[0]["n"]
    assert d["violations"]["open_violations"] == expected
    assert "avg_stay_minutes" in d["stays_7d"]
