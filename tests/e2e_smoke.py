"""End-to-end smoke test: sign in -> search a slot -> reserve -> gate entry
-> gate exit -> bill generated -> payment recorded -> every report renders."""
import json, random, sys, urllib.request, urllib.error, datetime as dt

import os
API = os.environ.get("SMARTPARK_API", "http://127.0.0.1:8077")
FAIL = []

def call(method, path, body=None, token=None, expect=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")

def step(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    if not cond: FAIL.append(name)
    print(f"  [{mark}] {name}{('  -> ' + str(detail)) if detail else ''}")

print("=" * 72); print("END-TO-END SMOKE TEST"); print("=" * 72)

print("\n1. Sign in")
s, r = call("POST", "/api/auth/login", {"email": "ops.central@smartpark.in", "password": "Parking@123"})
step("operator signs in", s == 200 and "token" in r, f"role={r.get('user',{}).get('role')}")
OP = r["token"]
s, r = call("POST", "/api/auth/login", {"email": "admin@smartpark.in", "password": "Parking@123"})
AD = r["token"]
s, r = call("POST", "/api/auth/login", {"email": "rahul.sharma@example.com", "password": "Parking@123"})
CU = r["token"]
step("customer signs in", s == 200, r.get("user", {}).get("role"))
s, r = call("POST", "/api/auth/login", {"email": "admin@smartpark.in", "password": "bad"})
step("wrong password rejected", s == 401, r.get("detail"))
s, r = call("GET", "/api/dashboard?facility_id=1")
step("no token rejected", s in (401, 403), r.get("detail"))

print("\n2. Search a free slot")
s, r = call("GET", "/api/slots/free?facility_id=1&vehicle_type_id=2", token=OP)
step("free-slot search returns rows", s == 200 and len(r) > 0, f"{len(r)} free car bays")
target_slot = r[0]

print("\n3. Register a customer and vehicle")
stamp = dt.datetime.now().strftime("%H%M%S")
s, cust = call("POST", "/api/customers",
               {"full_name": "E2E Test Driver", "phone": "9" + stamp + "999"[:9]}, token=OP)
if s != 201:
    s, cust = call("POST", "/api/customers",
                   {"full_name": "E2E Test Driver", "phone": "9000" + stamp}, token=OP)
step("create customer", s == 201, cust)
plate = "TS01ZZ" + stamp[-4:]
s, veh = call("POST", "/api/vehicles",
              {"customer_id": cust["customer_id"], "plate_number": plate,
               "vehicle_type_id": 2, "make": "Test", "model": "Car"}, token=OP)
step("create vehicle", s == 201, veh)

print("\n4. Validation is enforced")
s, r = call("POST", "/api/vehicles",
            {"customer_id": cust["customer_id"], "plate_number": "HELLO", "vehicle_type_id": 2}, token=OP)
step("bad plate rejected", s in (409, 422), r.get("detail") if isinstance(r.get("detail"), str) else "422 schema")
s, r = call("POST", "/api/vehicles",
            {"customer_id": cust["customer_id"], "plate_number": plate, "vehicle_type_id": 2}, token=OP)
step("duplicate plate rejected", s == 409, r.get("detail"))

print("\n5. Reserve a slot")
now = dt.datetime.now(dt.timezone.utc)
# A window unique to this run, so repeated runs do not collide with each other.
RES_OFFSET = dt.timedelta(days=2 + random.randint(0, 60), minutes=random.randint(0, 1200))
s, res = call("POST", "/api/reservations",
              {"customer_id": cust["customer_id"], "vehicle_id": veh["vehicle_id"],
               "slot_id": target_slot["slot_id"],
               "reserved_from": (now + RES_OFFSET).isoformat(),
               "reserved_until": (now + RES_OFFSET + dt.timedelta(hours=2)).isoformat()}, token=OP)
step("create reservation", s == 201, res)
s, r = call("POST", "/api/reservations",
            {"customer_id": cust["customer_id"], "vehicle_id": veh["vehicle_id"],
             "slot_id": target_slot["slot_id"],
             "reserved_from": (now + RES_OFFSET + dt.timedelta(minutes=30)).isoformat(),
             "reserved_until": (now + RES_OFFSET + dt.timedelta(hours=3)).isoformat()}, token=OP)
step("overlapping reservation rejected", s == 409, r.get("detail"))

print("\n6. Gate entry")
s, entry = call("POST", "/api/gate/entry", {"plate": plate, "facility_id": 1}, token=OP)
step("gate entry allocates a slot", s == 200 and entry.get("ticket_no"),
     f"ticket {entry.get('ticket_no')} -> slot {entry.get('slot_code')}")
s, r = call("POST", "/api/gate/entry", {"plate": plate, "facility_id": 1}, token=OP)
step("double entry rejected", s in (400, 409), r.get("detail"))
s, r = call("POST", "/api/gate/entry", {"plate": "XX99XX9999", "facility_id": 1}, token=OP)
step("unknown plate rejected", s in (400, 404, 409), r.get("detail"))

print("\n6b. Arrival onto a RESERVED bay")
# A distinct code path in fn_gate_entry: the reservation branch, which locks the
# already-held bay instead of allocating a new one. Worth its own check - an
# OUT-parameter name collision hid in this branch and never fired in the
# allocate path, so a test that only used unreserved vehicles missed it.
now_utc = dt.datetime.now(dt.timezone.utc)
booked = None
for status in ("held", "confirmed"):
    st, resv = call("GET", f"/api/reservations?status={status}", token=OP)
    if st != 200:
        continue
    for r in resv:
        # The reservation branch only triggers for a hold covering this instant.
        frm = dt.datetime.fromisoformat(r["reserved_from"])
        til = dt.datetime.fromisoformat(r["reserved_until"])
        if not (frm <= now_utc <= til):
            continue
        # Probe as ADMIN, not as the operator. An operator's view of
        # is_parked is scoped by RLS to their own facility, so a vehicle
        # parked at the other site reads as "away" to them - correct, but
        # not the question being asked here.
        sv, vs = call("GET", f"/api/vehicles?q={r['plate_number']}", token=AD)
        match = [v for v in (vs or []) if v["plate_number"] == r["plate_number"]]
        if sv == 200 and match and not match[0]["is_parked"]:
            booked = r
            break
    if booked:
        break

if booked:
    s, e2 = call("POST", "/api/gate/entry",
                 {"plate": booked["plate_number"], "facility_id": booked["facility_id"]}, token=OP)
    step("arrival honours the reservation", s == 200 and e2.get("slot_code") == booked["slot_code"],
         f"{booked['plate_number']} -> reserved bay {e2.get('slot_code')} "
         f"(held: {booked['slot_code']})")
    if s == 200:
        call("POST", "/api/gate/exit", {"lookup": e2["ticket_no"]}, token=OP)
else:
    step("arrival honours the reservation", True,
         "skipped: no live hold whose vehicle is currently away")

print("\n7. Look up the open session")
s, look = call("GET", f"/api/gate/lookup?q={plate}", token=OP)
step("lookup finds the session", s == 200 and look.get("ticket_no") == entry["ticket_no"],
     f"running charge Rs {look.get('running_charge')}")

print("\n8. Gate exit raises a bill")
s, ex = call("POST", "/api/gate/exit", {"lookup": entry["ticket_no"]}, token=OP)
step("gate exit succeeds", s == 200 and ex.get("bill_id"),
     f"bill {ex.get('bill_id')} total Rs {ex.get('total_amount')}")
step("bill total = base + tax",
     abs(float(ex["total_amount"]) - (float(ex["base_amount"]) + float(ex["tax_amount"]))) < 0.01,
     f"{ex['base_amount']} + {ex['tax_amount']} = {ex['total_amount']}")
s, r = call("POST", "/api/gate/exit", {"lookup": entry["ticket_no"]}, token=OP)
step("second exit rejected", s in (400, 404), r.get("detail"))

print("\n8b. A chargeable exit (a vehicle parked for hours, not minutes)")
# The vehicle above left inside the 15-minute grace period, so its bill was
# correctly zero. Exit one of the long-running seeded sessions to prove the
# tariff arithmetic end to end through the API.
s, open_sessions = call("GET", "/api/sessions?facility_id=1&active_only=true&limit=50", token=OP)
# Skip pass-covered sessions: fn_calculate_charge correctly returns 0 for those,
# which is the pass working, not the tariff failing.
longest, look2 = None, None
for cand in sorted(open_sessions, key=lambda r: -r["duration_minutes"]):
    st, probe = call("GET", f"/api/gate/lookup?q={cand['plate_number']}", token=OP)
    if st == 200 and probe.get("pass_id") is None:
        longest, look2, s = cand, probe, st
        break
step("found a chargeable open session", longest is not None,
     f"{longest['plate_number'] if longest else 'none'}")
step("long session has a running charge", s == 200 and float(look2["running_charge"]) > 0,
     f"{look2['minutes_so_far']} min -> Rs {look2['running_charge']}")
s, ex2 = call("POST", "/api/gate/exit", {"lookup": longest["ticket_no"]}, token=OP)
step("chargeable exit bills a real amount", s == 200 and float(ex2["total_amount"]) > 0,
     f"base Rs {ex2['base_amount']} + tax Rs {ex2['tax_amount']} = Rs {ex2['total_amount']}")
step("quoted charge matches the bill",
     abs(float(look2["running_charge"]) - float(ex2["base_amount"])) < 1.0,
     f"quoted {look2['running_charge']} vs billed {ex2['base_amount']}")
s, part = call("POST", "/api/payments",
               {"bill_id": ex2["bill_id"], "amount": round(float(ex2["total_amount"]) / 2, 2),
                "method": "cash"}, token=OP)
step("half payment marks the bill partly_paid", part.get("status") == "partly_paid", part.get("status"))

print("\n9. Record a payment")
s, bill = call("GET", f"/api/bills/{ex2['bill_id']}", token=OP)
step("bill detail loads", s == 200, f"status {bill.get('status')}")
due = round(float(ex2["total_amount"]) - round(float(ex2["total_amount"]) / 2, 2), 2)
s, pay = call("POST", "/api/payments",
              {"bill_id": ex2["bill_id"], "amount": due, "method": "upi",
               "reference_no": "E2E-TEST"}, token=OP)
step("balance payment recorded", s == 201, f"Rs {due}, bill now {pay.get('status')}")
step("bill marked paid by trigger", pay.get("status") == "paid", pay.get("status"))
s, r = call("POST", "/api/payments",
            {"bill_id": ex2["bill_id"], "amount": 1, "method": "cash"}, token=OP)
step("payment beyond the balance rejected", s == 409, r.get("detail"))
s, r = call("POST", "/api/payments",
            {"bill_id": ex["bill_id"], "amount": -5, "method": "cash"}, token=OP)
step("negative payment rejected", s in (409, 422), "rejected")

print("\n10. Every report renders with real data")
for name, path in [
    ("occupancy",  "/api/reports/occupancy?facility_id=1"),
    ("peak hours", "/api/reports/peak-hours?facility_id=1"),
    ("revenue",    "/api/reports/revenue?facility_id=1"),
    ("duration",   "/api/reports/duration?facility_id=1"),
    ("pass usage", "/api/reports/pass-usage"),
    ("violations", "/api/reports/violations"),
    ("free slots", "/api/reports/free-slots?facility_id=1"),
]:
    s, r = call("GET", path, token=AD)
    n = len(r) if isinstance(r, list) else sum(len(v) for v in r.values() if isinstance(v, list))
    step(f"report: {name}", s == 200 and n > 0, f"{n} rows")

print("\n11. Authorisation holds through the API")
s, r = call("POST", "/api/gate/entry", {"plate": plate, "facility_id": 1}, token=CU)
step("customer cannot work the gate", s == 403, r.get("detail"))
s, r = call("POST", "/api/payments", {"bill_id": 1, "amount": 10, "method": "cash"}, token=CU)
step("customer cannot record payments", s == 403, r.get("detail"))
s, cv = call("GET", "/api/vehicles", token=CU)
s2, av = call("GET", "/api/vehicles", token=AD)
step("customer sees fewer vehicles than admin", len(cv) < len(av), f"{len(cv)} vs {len(av)}")
s, r = call("POST", "/api/tariffs", {"facility_id":1,"vehicle_type_id":2,"name":"x",
            "free_minutes":10,"first_hour_rate":10,"subsequent_hour_rate":5,"daily_cap":50}, token=OP)
step("operator cannot change tariffs", s == 403, r.get("detail"))

print("\n" + "=" * 72)
if FAIL:
    print(f"FAILED ({len(FAIL)}): " + ", ".join(FAIL)); sys.exit(1)
print("ALL END-TO-END CHECKS PASSED"); print("=" * 72)
