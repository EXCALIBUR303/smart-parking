"""Capture the output screens for Review 3 and the report, into docs/screens/.

Drives the system Chrome through Playwright at a laptop viewport (1440 x 900).
Signs in as the administrator, waits for each page's data and entrance
animations to settle, then captures the page. Some screens need an action first
(open a dialog, switch a tab, run the gate); those are the `act` callbacks.

The gate screens record a real arrival for PLATE, so run this against a demo
database, not one whose data matters:

    ./.venv/bin/python tests/capture_screens.py
"""
import json
import os
import pathlib
import sys
import urllib.request

from playwright.sync_api import sync_playwright

API = os.environ.get("SMARTPARK_API", "http://127.0.0.1:8077")
PLATE = os.environ.get("SMARTPARK_SCREEN_PLATE", "TS09AB1234")   # a seeded car, not parked
OUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "screens"
VIEW = {"width": 1440, "height": 900}


def api(method, path, body=None, token=None):
    req = urllib.request.Request(f"{API}{path}", method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"content-type": "application/json",
                                          **({"authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError:
        return None


def chargeable_plate(token):
    """The longest open stay at Central that no pass covers, so the departure
    screens show the tariff at work rather than a free stay."""
    open_now = api("GET", "/api/sessions?facility_id=1&active_only=true&limit=100", token=token) or []
    for s in sorted(open_now, key=lambda r: -r["duration_minutes"]):
        probe = api("GET", f"/api/gate/lookup?q={s['plate_number']}", token=token)
        if probe and probe.get("pass_id") is None and s["plate_number"] != PLATE:
            return s["plate_number"]
    raise SystemExit("No chargeable open session to show at the exit gate")


EXIT_PLATE = None


def settle(page):
    """Wait for data AND for the entrance animations to finish."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    try:
        page.wait_for_function("() => !document.querySelector('.skeleton')", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(1200)


def tab(tab_id):
    return lambda p: (p.click(f"#tab-{tab_id}"), settle(p))


def gate_entry(p):
    p.fill("#plate", PLATE)
    p.click("#entry-submit")
    p.wait_for_selector("#entry-result dl", timeout=10000)
    settle(p)


def gate_exit(p):
    p.fill("#lookup", EXIT_PLATE)
    p.click("#lookup-submit")
    p.wait_for_selector("#exit-result .btn-primary", timeout=10000)
    settle(p)


def confirm_exit(p):
    """Confirm the departure: the bill is raised from the tariff."""
    gate_exit(p)
    p.click("#exit-result .btn-primary")
    p.wait_for_selector(".scrim .modal", timeout=10000)
    settle(p)


def vehicle_history(p):
    p.click("#tab-vehicle"); settle(p)
    p.fill("#hist-plate", PLATE)
    p.click("#hist-form button[type=submit]")
    settle(p)


def open_first_row(p):
    p.click(".dt tbody tr[role=row]")
    p.wait_for_selector(".scrim .modal, .scrim .sheet", timeout=8000)
    settle(p)


def open_bay(p):
    p.click(".bay[data-state='occupied']")
    p.wait_for_selector(".sheet", timeout=8000)
    settle(p)


def click_then_settle(sel):
    def act(p):
        p.click(sel)
        p.wait_for_selector(".scrim", timeout=8000)
        settle(p)
    return act


SCREENS = [
    # name                   path                  action            full page
    # Viewport captures: a fixed sidebar does not extend in a full-page shot.
    ("02-dashboard",         "/dashboard.html",    None, False),
    ("03-floor-map",         "/slots.html",        None, False),
    ("04-bay-sheet",         "/slots.html",        open_bay,         False),
    ("05-gate-entry",        "/gate.html",         gate_entry, False),
    ("06-gate-exit-quote",   "/gate.html",         gate_exit, False),
    ("06b-gate-exit-billed", "/gate.html",         confirm_exit, False),
    ("07-reservations",      "/reservations.html", None, False),
    ("08-new-reservation",   "/reservations.html", click_then_settle("#new"), False),
    ("09-passes",            "/passes.html",       None, False),
    ("10-billing",           "/billing.html",      None, False),
    ("11-invoice",           "/billing.html",      open_first_row,   False),
    ("12-payments-ledger",   "/billing.html",      tab("ledger"), False),
    ("13-report-occupancy",  "/reports.html",      None, False),
    ("14-report-peak-hours", "/reports.html",      tab("peak"), False),
    ("15-report-revenue",    "/reports.html",      tab("revenue"), False),
    ("16-report-duration",   "/reports.html",      tab("duration"), False),
    ("17-report-pass-usage", "/reports.html",      tab("passes"), False),
    ("18-report-violations", "/reports.html",      tab("violations"), False),
    ("19-report-free-slots", "/reports.html",      tab("free"), False),
    ("20-vehicle-history",   "/reports.html",      vehicle_history, False),
    ("21-customers",         "/customers.html",    None, False),
    ("22-customer-vehicles", "/customers.html",    open_first_row,   False),
    ("23-settings-tariffs",  "/settings.html",     None, False),
    ("24-audit-trail",       "/settings.html",     tab("audit"), False),
]


def save(page, name, full):
    out = OUT / f"{name}.png"
    page.screenshot(path=str(out), full_page=full)
    print(f"  {name:<24} {out.stat().st_size // 1024} KB")


def signed_in_page(browser):
    ctx = browser.new_context(viewport=VIEW, device_scale_factor=1.5)
    page = ctx.new_page()
    page.goto(f"{API}/index.html", wait_until="domcontentloaded")
    page.fill("#email", "admin@smartpark.in")
    page.fill("#password", "Parking@123")
    page.click("#submit")
    page.wait_for_url("**/dashboard.html", timeout=15000)
    return page


def main():
    global EXIT_PLATE
    token = api("POST", "/api/auth/login",
                {"email": "admin@smartpark.in", "password": "Parking@123"})["token"]
    api("POST", "/api/gate/exit", {"lookup": PLATE}, token)   # in case a run left it parked
    EXIT_PLATE = chargeable_plate(token)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    failed = []
    with sync_playwright() as p:
        # The sign-in screen, captured signed out.
        browser = p.chromium.launch(channel="chrome", headless=True)
        ap = browser.new_context(viewport=VIEW, device_scale_factor=1.5).new_page()
        ap.goto(f"{API}/index.html", wait_until="domcontentloaded")
        settle(ap)
        save(ap, "01-sign-in", False)
        browser.close()

        # A fresh browser per screen: headless Chrome on macOS was found to
        # crash after about ten large full-page captures in one process.
        for name, path, act, full in SCREENS:
            browser = p.chromium.launch(channel="chrome", headless=True)
            try:
                page = signed_in_page(browser)
                page.goto(f"{API}{path}", wait_until="domcontentloaded")
                settle(page)
                if act:
                    act(page)
                save(page, name, full)
            except Exception as e:                       # report and carry on
                failed.append(name)
                print(f"  {name:<24} FAILED: {str(e).splitlines()[0]}")
            finally:
                browser.close()

    api("POST", "/api/gate/exit", {"lookup": PLATE}, token)   # leave the demo car out again
    print(f"\n{len(list(OUT.glob('*.png')))} screens in docs/screens/"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
