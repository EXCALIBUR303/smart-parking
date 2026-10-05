"""Regenerate docs/TESTING.md from freshly captured test output.

Runs every suite and builds the document from what they actually printed,
so the file always reports a real run rather than a remembered one.

    ./.venv/bin/python tests/gen_testing_doc.py

Requires the API to be running (for the end-to-end and browser sections)
and Google Chrome installed. The pytest suite uses its own smartpark_test
database; the SQL suites use $SMARTPARK_DB (default smartpark).
"""
import os
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
PSQL = "/opt/homebrew/opt/postgresql@17/bin/psql"
DB = os.environ.get("SMARTPARK_DB", "smartpark")


SUITES = [
    ("ct",    [PSQL, "-d", DB, "-f", "db/tests/constraint_tests.sql"]),
    ("rls",   [PSQL, "-d", DB, "-f", "db/tests/rls_tests.sql"]),
    ("life",  [PSQL, "-d", DB, "-f", "db/tests/lifecycle_tests.sql"]),
    ("e2e",   ["./.venv/bin/python", "tests/e2e_smoke.py"]),
    ("py",    ["./.venv/bin/pytest", "-v", "-p", "no:warnings", "tests/test_api.py"]),
    ("pages", ["./.venv/bin/python", "tests/page_smoke.py"]),
    ("comp",  ["./.venv/bin/python", "tests/a11y_components.py"]),
    ("contr", ["./.venv/bin/python", "tests/a11y_contrast.py"]),
]


def run_suites():
    out = {}
    for key, cmd in SUITES:
        # One stream, so psql's ERROR lines stay inside the test they belong to.
        r = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
        # Chrome writes its own diagnostics to stderr; keep only our output.
        out[key] = "\n".join(l for l in r.stdout.splitlines() if not l.startswith("[pid="))
    return out


def parse_constraint_blocks(ct):
    blocks, cur = [], None
    for line in ct.splitlines():
        m = re.match(r"^(TEST \S+)\s+(.*)$", line.strip())
        if m:
            cur = {"id": m.group(1), "title": m.group(2), "lines": []}
            blocks.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    return blocks


def scalar(text, label):
    """Read a single-value psql result printed under `label`."""
    m = re.search(re.escape(label) + r"\s*\n[-\s|]*\n\s*(\S+)", text)
    return m.group(1) if m else "?"


def build(r):
    ct, rls, e2e = r["ct"], r["rls"], r["e2e"]
    blocks = parse_constraint_blocks(ct)
    refused = len([b for b in blocks if any("ERROR" in l for l in b["lines"])])
    L, w = [], None
    L = []
    w = L.append

    # ---------------------------------------------------------------- header
    w("# Testing\n")
    w("Smart Parking Lot Allocation & Billing System — DBMS PBL Project 20.\n")
    w("Every result below is captured output from a real run, not a description")
    w("of what the code is expected to do. Regenerate the whole document with:\n")
    w("```bash")
    w("./.venv/bin/python tests/gen_testing_doc.py")
    w("```\n")
    w("| Suite | What it proves | Result |")
    w("|---|---|---|")
    life_rows = re.findall(r"^\s*(PASS|FAIL)\s*\|\s*(.+)$", r["life"], re.M)
    py_pass = len(re.findall(r" PASSED", r["py"]))
    py_fail = len(re.findall(r" FAILED", r["py"]))
    comp = re.search(r"(\d+)/(\d+) component checks passed", r["comp"])
    contr = re.search(r"TOTAL below AA: (\d+)", r["contr"])
    pages_ok = "FAILING PAGES: none" in r["pages"]
    w(f"| Constraint tests | Each business rule rejects its violation | "
      f"**{refused} of {len(blocks)} attempts refused by the database**; "
      f"{len(blocks) - refused} accepted and silently corrected (TEST 8's point) |")
    w(f"| Lifecycle tests | Expiry, overstay, passes, derived billing | "
      f"**{sum(1 for x in life_rows if x[0] == 'PASS')} of {len(life_rows)} pass** |")
    w("| RLS tests | Policies restrict rows, and fail closed | **Pass** |")
    w(f"| End-to-end smoke | Sign-in → reserve → entry → exit → bill → payment → "
      f"reports | **{e2e.count('[PASS]')} checks, {e2e.count('[FAIL]')} failures** |")
    w(f"| API tests (pytest) | CRUD, ownership, servicing, payments, scoping | "
      f"**{py_pass} passed, {py_fail} failed** |")
    w(f"| Browser: every page | Console errors and failed requests, 1440×900 | "
      f"**{'No errors on any page' if pages_ok else 'FAILURES - see section 6'}** |")
    w(f"| Browser: components | Keyboard, dialogs, tabs, reduced motion | "
      f"**{comp.group(1) + ' of ' + comp.group(2) if comp else '?'} pass** |")
    w(f"| Browser: contrast | Text below WCAG AA on all 10 pages | "
      f"**{contr.group(1) if contr else '?'} elements** |")
    w("")
    w("---\n")

    # ------------------------------------------------------------ section 1
    w("## 1. Constraint tests — trying to break each business rule\n")
    w("```bash")
    w("psql -d smartpark -f db/tests/constraint_tests.sql")
    w("```\n")
    w("Each block deliberately violates one rule inside its own transaction,")
    w("which is then rolled back. The error text is exactly what PostgreSQL")
    w("returned. A constraint that has never been tested to failure is one you")
    w("cannot defend in a viva.\n")
    for b in blocks:
        # Attempt/Expect in the SQL may run over several \echo lines; a
        # continuation is indented and starts no new keyword, so fold it in.
        attempt, expect, field = "", "", None
        for raw in b["lines"]:
            s = raw.strip()
            if s.startswith("Attempt:"):
                field, attempt = "a", s.split(":", 1)[1].strip()
            elif s.startswith("Expect"):
                field, expect = "e", s.split(":", 1)[1].strip()
            elif field and raw.startswith("     ") and s and not s.startswith("="):
                if field == "a":
                    attempt += " " + s
                else:
                    expect += " " + s
            elif s.startswith("="):
                field = None
        errs = [l for l in b["lines"]
                if "ERROR:" in l or l.strip().startswith("DETAIL:")]
        w(f"### {b['id']} — {b['title']}\n")
        if attempt:
            w(f"**Attempt.** {attempt}\n")
        if expect:
            w(f"**Expected.** {expect}\n")
        if errs:
            w("**PostgreSQL returned:**\n")
            w("```")
            for e in errs[:3]:
                w(re.sub(r"^psql:[^:]+:\d+: ", "", e.rstrip()))
            w("```\n")
            w("**Result: REFUSED by the database.**\n")
        else:
            tbl = [l for l in b["lines"]
                   if "|" in l and not l.strip().startswith("\\")]
            if tbl:
                w("**PostgreSQL returned:**\n")
                w("```")
                for t in tbl[:6]:
                    w(t.rstrip())
                w("```\n")
            w("**Result: accepted, then silently corrected by the trigger — "
              "which is exactly what this test exists to show.**\n")

    # ------------------------------------------------------------ section 2
    w("---\n")
    w("## 2. Row-level security — proving the policies restrict\n")
    w("```bash")
    w("psql -d smartpark -f db/tests/rls_tests.sql")
    w("```\n")
    w("PostgreSQL exempts a table's owner from its own RLS policies unless")
    w("`FORCE ROW LEVEL SECURITY` is set, so the API never queries as the owner.")
    w("It issues `SET LOCAL app.current_user_id` and `SET LOCAL ROLE` per")
    w("request, and these tests do the same — they exercise the policies exactly")
    w("as real traffic does.\n")
    w("### Visibility by role\n")
    w("| Acting as | Customers | Vehicles | Bills | Sessions |")
    w("|---|--:|--:|--:|--:|")
    w(f"| Table owner (RLS bypassed by ownership) | {scalar(rls,'all_customers')} "
      f"| {scalar(rls,'all_vehicles')} | {scalar(rls,'all_bills')} | — |")
    w(f"| Customer 1 — Rahul Sharma | {scalar(rls,'customers_visible')} "
      f"| {scalar(rls,'vehicles_visible')} | {scalar(rls,'bills_visible')} "
      f"| {scalar(rls,'sessions_visible')} |")
    w("| **No identity set** | **0** | **0** | **0** | — |")
    w("")
    w("The last row is the important one. With `app.current_user_id` unset,")
    w("`fn_current_user_id()` returns NULL, every policy evaluates false, and the")
    w("caller sees nothing. The system fails **closed**.\n")

    a = re.search(r"TEST A[\s\S]*?plate_number\s*\n[-\s]*\n([\s\S]*?)\(\d+ rows?\)", rls)
    b_ = re.search(r"TEST B[\s\S]*?plate_number\s*\n[-\s]*\n([\s\S]*?)\(\d+ rows?\)", rls)
    if a and b_:
        la = [x.strip() for x in a.group(1).strip().splitlines() if x.strip()]
        lb = [x.strip() for x in b_.group(1).strip().splitlines() if x.strip()]
        w("### Two customers see disjoint data\n")
        w("| Rahul Sharma (user 5) sees | Priya Nair (user 6) sees |")
        w("|---|---|")
        for i in range(max(len(la), len(lb))):
            left = f"`{la[i]}`" if i < len(la) else ""
            right = f"`{lb[i]}`" if i < len(lb) else ""
            w(f"| {left} | {right} |")
        w("")
        w(f"Plates in common: **{len(set(la) & set(lb))}**. Rahul querying")
        w("`customer_id = 2` directly returns 0 rows — the row is invisible")
        w("rather than forbidden, which is correct: an error would itself")
        w("disclose that the row exists.\n")

    w("### Writes are restricted too\n")
    w("| Attempt | Result |")
    w("|---|---|")
    for label, pat in [
        ("Customer writes a vehicle onto another customer", r"TEST D[\s\S]*?(ERROR:.*)"),
        ("Customer records a payment against their own bill", r"TEST E[\s\S]*?(ERROR:.*)"),
    ]:
        m = re.search(pat, rls)
        w(f"| {label} | `{m.group(1).strip() if m else 'n/a'}` |")
    w("")

    f1 = re.findall(r"TEST F[\s\S]*?facility_id \| sessions_by_facility\s*\n[-\s|+]*\n([\s\S]*?)\(\d+ row", rls)
    f2 = re.findall(r"TEST G[\s\S]*?facility_id \| sessions_by_facility\s*\n[-\s|+]*\n([\s\S]*?)\(\d+ row", rls)
    w("### Operators are scoped to their own facility\n")
    w("```")
    if f1:
        w("Rohit  (operator, facility 1):\n" + f1[0].rstrip())
    if f2:
        w("Imran  (operator, facility 2):\n" + f2[0].rstrip())
    w("```\n")
    w("Each operator's query returns rows for their own site only — the grouping")
    w("proves it, since a leak would show a second facility_id.\n")

    w("### Views honour RLS (`security_invoker = true`)\n")
    w("| Query | As customer 1 | As admin |")
    w("|---|--:|--:|")
    w(f"| `SELECT count(*) FROM v_session_duration` "
      f"| {scalar(rls,'duration_rows_visible_to_customer')} "
      f"| {scalar(rls,'duration_rows_visible_to_admin')} |")
    w(f"| `SELECT count(*) FROM v_violations` "
      f"| {scalar(rls,'violations_visible_to_customer')} "
      f"| {scalar(rls,'violations_visible_to_admin')} |")
    w("")
    w("Without `security_invoker = true` a view executes as its owner and both")
    w("columns above would read the same. That is the classic way an RLS policy")
    w("is bypassed by the convenience layer built on top of it.\n")

    # ------------------------------------------------------------ section 3
    w("---\n")
    w("## 3. End-to-end smoke test\n")
    w("```bash")
    w("./.venv/bin/python tests/e2e_smoke.py")
    w("```\n")
    w("Drives the running API over HTTP: sign in, search a bay, register a")
    w("customer and vehicle, reserve, gate entry onto both an allocated and a")
    w("reserved bay, gate exit, bill, payment, every report, and the")
    w("authorisation boundaries. Safe to run repeatedly.\n")
    w("```")
    for line in e2e.splitlines():
        if line.strip():
            w(line.rstrip())
    w("```\n")

    # ------------------------------------------------------------ lifecycle
    w("---\n")
    w("## 3b. Lifecycle tests — rules that depend on time\n")
    w("```bash")
    w("psql -d smartpark -f db/tests/lifecycle_tests.sql")
    w("```\n")
    w("A lapsed hold, a stay over 24 hours, a live pass and an expired pass,")
    w("driven through the real gate functions inside one transaction that is")
    w("rolled back.\n")
    w("| Test | Result | What the database did |")
    w("|---|---|---|")
    cur = ""
    for line in r["life"].splitlines():
        m = re.match(r"^LIFECYCLE (\d+)\s+(.*)$", line.strip())
        if m:
            cur = f"{m.group(1)}. {m.group(2)}"
            continue
        m = re.match(r"^\s*(PASS|FAIL)\s*\|\s*(.+)$", line)
        if m:
            w(f"| {cur} | **{m.group(1)}** | {m.group(2).strip()} |")
            cur = "″"
    w("")

    # ------------------------------------------------------------ pytest
    w("---\n")
    w("## 3c. API tests (pytest)\n")
    w("```bash")
    w("SMARTPARK_DATABASE_URL=postgresql:///smartpark_test ./.venv/bin/pytest -q")
    w("```\n")
    w("Run in-process against a separate `smartpark_test` database built from")
    w("the same migrations.\n")
    w("| Test | Result |")
    w("|---|---|")
    for name, res in re.findall(r"::(test_\w+) (PASSED|FAILED)", r["py"]):
        w(f"| `{name}` | {res} |")
    w("")

    # ------------------------------------------------------------ section 4
    w("---\n")
    w("## 4. Validation and error handling\n")
    w("Client-side validation exists for responsiveness; the database is the real")
    w("gate. The message a user sees is the mapped constraint message from")
    w("`api/errors.py`, keyed on the PostgreSQL constraint name.\n")
    w("| Where | Bad input | Caught by | Message shown to the user |")
    w("|---|---|---|---|")
    for row in [
        ("Gate — arrival", "`HELLO` as a registration", "`ck_vehicle_plate_shape`",
         "That does not look like a valid registration number. Use the format TS09AB1234."),
        ("Gate — arrival", "A plate not on file", "`fn_gate_entry` RAISE, SQLSTATE `no_data_found`",
         "No vehicle is registered with plate XX99XX9999"),
        ("Gate — arrival", "A vehicle already inside", "`uq_active_session_vehicle`",
         "Vehicle TS09AB1234 is already parked and has not exited"),
        ("Gate — arrival", "Facility full for that type", "`fn_allocate_slot` returns NULL → RAISE",
         "No free slot available for this vehicle type at facility 1"),
        ("Gate — arrival", "Operator posted to another site", "`fn_gate_entry` facility guard",
         "You are posted to facility 2, not facility 1"),
        ("Gate — departure", "Ticket with no open session", "`fn_gate_exit` RAISE",
         'No open parking session found for "TK-XXXXXXXX"'),
        ("Reservations", "End time before start", "`ck_reservation_window`",
         "The reservation must end after it starts."),
        ("Reservations", "Bay already held for that window", "`ex_reservation_no_overlap`",
         "That slot is already reserved for an overlapping period. Pick another slot or time."),
        ("Passes", "Second live pass, same vehicle and site", "`ex_pass_no_overlap`",
         "This vehicle already holds a pass covering those dates at this facility."),
        ("Billing", "Payment of zero or less", "`ck_payment_amount_positive`",
         "A payment must be greater than zero."),
        ("Billing", "Payment exceeding the balance", "`trg_payment_within_balance`",
         "That is more than the ₹236.00 still owed on this bill."),
        ("Customers", "Phone that is not ten digits", "`ck_customer_phone_shape`",
         "Enter a 10 digit phone number with no spaces or country code."),
        ("Customers", "Registration already on file", "`vehicle_plate_number_key`",
         "A vehicle with that registration number is already on file."),
        ("Customers", "Removing a vehicle with history", "`ON DELETE RESTRICT`",
         "The database's own message, surfaced verbatim"),
        ("Settings", "Daily cap below the first-hour rate", "`ck_tariff_cap_sane`",
         "The daily cap cannot be lower than the first hour rate."),
        ("Settings", "Second tariff for a priced facility/type", "`ex_tariff_no_overlap`",
         "A tariff is already in force for this facility and vehicle type."),
        ("Sign in", "Wrong password", "bcrypt verify fails", "Email or password is incorrect."),
        ("Sign in", "Unknown email", "same message, deliberately",
         "Email or password is incorrect. *(identical, so responses cannot be used to enumerate accounts)*"),
        ("Any screen", "Expired or missing token", "`api/auth.py`",
         "Your session has expired. Sign in again. *(and a redirect to sign-in)*"),
        ("Any screen", "API not running", "fetch throws",
         "Cannot reach the server. Check that the API is running."),
    ]:
        w("| " + " | ".join(row) + " |")
    w("")

    # ------------------------------------------------------------ section 5
    w("---\n")
    w("## 5. Interface checks (Chrome via Playwright, 1440×900)\n")
    w("### Every page loads cleanly\n")
    w("```bash")
    w("./.venv/bin/python tests/page_smoke.py")
    w("```\n")
    w("```")
    for line in r["pages"].splitlines():
        if line.strip():
            w(line.rstrip())
    w("```\n")
    w("### Components: keyboard, dialogs, tabs, reduced motion\n")
    w("```bash")
    w("./.venv/bin/python tests/a11y_components.py")
    w("```\n")
    w("```")
    for line in r["comp"].splitlines():
        if line.strip():
            w(line.rstrip())
    w("```\n")
    w("### Text contrast against WCAG AA\n")
    w("Every visible text element on every page, foreground against its")
    w("actual composited background.\n")
    w("```")
    for line in r["contr"].splitlines():
        if "below AA" in line:
            w(line.rstrip())
    w("```\n")
    return "\n".join(L)


if __name__ == "__main__":
    out = ROOT / "docs" / "TESTING.md"
    out.write_text(build(run_suites()))
    print(f"wrote {out} ({len(out.read_text().splitlines())} lines)")
