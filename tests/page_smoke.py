"""Load every page in the real browser and report console errors + failed requests."""
import sys, pathlib
from playwright.sync_api import sync_playwright
API = "http://127.0.0.1:8077"
PAGES = ["index.html","dashboard.html","slots.html","gate.html","reservations.html",
         "passes.html","billing.html","reports.html","customers.html","settings.html"]
bad = []
with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    ctx = br.new_context(viewport={"width":1440,"height":900})
    pg = ctx.new_page()
    pg.goto(f"{API}/index.html"); pg.fill("#email","admin@smartpark.in")
    pg.fill("#password","Parking@123"); pg.click("#submit")
    pg.wait_for_url("**/dashboard.html", timeout=15000)
    for name in PAGES:
        errs, fails, resp_bad = [], [], []
        # A module-resolution SyntaxError ("does not provide an export named X")
        # never reaches the console channel — it arrives as a pageerror. An
        # earlier version of this test listened only for console messages and
        # reported a completely blank page as "ok".
        h_console = lambda m, e=errs: e.append("console: " + m.text) if m.type == "error" else None
        h_pageerr = lambda x, e=errs: e.append("pageerror: " + str(x))
        h_fail    = lambda r, f=fails: f.append(r.url)
        h_resp    = lambda r, b=resp_bad: b.append(f"{r.status} {r.url}") if r.status >= 400 else None
        pg.on("console", h_console); pg.on("pageerror", h_pageerr)
        pg.on("requestfailed", h_fail); pg.on("response", h_resp)
        pg.goto(f"{API}/{name}", wait_until="domcontentloaded")
        try: pg.wait_for_load_state("networkidle", timeout=8000)
        except Exception: pass
        pg.wait_for_timeout(1800)
        panels = pg.locator(".error-state").count()
        # A page that threw during module load leaves an empty <main>, with no
        # console output at all. Assert it actually rendered.
        rendered = pg.evaluate(
            "() => (document.querySelector('#main')?.textContent || document.body.textContent || '').trim().length")
        blank = rendered < 40
        status = "ok"
        if errs or resp_bad or panels or blank:
            status = "PROBLEM"; bad.append(name)
        print(f"  {name:<22} {status:<9} errors:{len(errs)} http4xx5xx:{len(resp_bad)} "
              f"errorPanels:{panels} textLen:{rendered}")
        for e in errs[:3]: print(f"      {e[:150]}")
        for e in resp_bad[:2]: print(f"      http: {e[:130]}")
        for h, ev in ((h_console,"console"), (h_pageerr,"pageerror"),
                      (h_fail,"requestfailed"), (h_resp,"response")):
            pg.remove_listener(ev, h)
    br.close()
print("\nFAILING PAGES:", bad if bad else "none")
sys.exit(1 if bad else 0)
