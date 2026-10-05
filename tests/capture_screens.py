"""Capture the output screens Review 3 asks for, into docs/screens/.

Drives the system Chrome through Playwright rather than downloading a separate
Chromium. Signs in as the administrator, waits for each page's network to go
quiet AND its entrance animations to settle, then captures a full-page PNG.
"""
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

API = os.environ.get("SMARTPARK_API", "http://127.0.0.1:8077")
OUT = pathlib.Path(__file__).resolve().parents[1] / "docs" / "screens"
OUT.mkdir(parents=True, exist_ok=True)

DESKTOP = [
    ("01-sign-in",           "/index.html",                  False),
    ("01b-sign-in-filled",   "/index.html",                  False),
    ("02-dashboard",         "/dashboard.html",              True),
    ("03-slot-map",          "/slots.html",                  True),
    ("04-gate",              "/gate.html",                   True),
    ("05-reservations",      "/reservations.html",           True),
    ("06-passes",            "/passes.html",                 True),
    ("07-billing",           "/billing.html",                True),
    ("08-report-occupancy",  "/reports.html#occupancy",      True),
    ("09-report-peak-hours", "/reports.html#peak",           True),
    ("10-report-revenue",    "/reports.html#revenue",        True),
    ("11-report-duration",   "/reports.html#duration",       True),
    ("12-report-pass-usage", "/reports.html#passes",         True),
    ("13-report-violations", "/reports.html#violations",     True),
    ("14-report-free-slots", "/reports.html#free",           True),
    ("15-customers",         "/customers.html",              True),
    ("16-settings",          "/settings.html",               True),
]
MOBILE = [
    ("17-mobile-dashboard", "/dashboard.html", True),
    ("18-mobile-slot-map",  "/slots.html",     True),
]


def settle(page):
    """Wait for data AND for the entrance animations to finish, so no screen is
    captured mid-fade."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(1600)          # entrances are 0.45s, staggers under 0.7s
    try:
        page.wait_for_function(
            "() => !document.querySelector('.skeleton')", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(400)


def sign_in(page):
    page.goto(f"{API}/index.html", wait_until="domcontentloaded")
    page.fill("#email", "admin@smartpark.in")
    page.fill("#password", "Parking@123")
    page.click("#submit")
    page.wait_for_url("**/dashboard.html", timeout=15000)
    settle(page)


def capture(page, name, path, width):
    page.goto(f"{API}{path}", wait_until="domcontentloaded")
    # A hash-only change does not reload, so force the tab explicitly.
    if "#" in path:
        page.evaluate("h => { location.hash = h; window.dispatchEvent(new HashChangeEvent('hashchange')); }",
                      path.split("#")[1])
    settle(page)
    out = OUT / f"{name}.png"
    page.screenshot(path=str(out), full_page=True)
    size = out.stat().st_size // 1024
    print(f"  {name:<24} {width}px  {size} KB")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        print(f"Desktop (1440px) -> {OUT}")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  device_scale_factor=2)
        page = ctx.new_page()
        sign_in(page)
        for name, path, needs_auth in DESKTOP:
            if not needs_auth:
                # The sign-in screen must be captured signed OUT.
                anon = browser.new_context(viewport={"width": 1440, "height": 900},
                                           device_scale_factor=2)
                ap = anon.new_page()
                ap.goto(f"{API}{path}", wait_until="domcontentloaded")
                settle(ap)
                if name.endswith("filled"):
                    ap.click(".demo-chip")     # prime from a demonstration chip
                    ap.wait_for_timeout(500)
                ap.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
                print(f"  {name:<24} 1440px  "
                      f"{(OUT / f'{name}.png').stat().st_size // 1024} KB")
                anon.close()
                continue
            capture(page, name, path, 1440)
        ctx.close()

        print(f"\nMobile (375px) -> {OUT}")
        mctx = browser.new_context(viewport={"width": 375, "height": 812},
                                   device_scale_factor=2, is_mobile=True,
                                   has_touch=True)
        mp = mctx.new_page()
        sign_in(mp)
        for name, path, _ in MOBILE:
            capture(mp, name, path, 375)
        mctx.close()

        browser.close()

    files = sorted(OUT.glob("*.png"))
    print(f"\n{len(files)} screens captured into docs/screens/")
    return 0 if len(files) >= 18 else 1


if __name__ == "__main__":
    sys.exit(main())
