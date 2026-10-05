"""Keyboard and screen-reader checks for the shared components added in the
merge: data table, actions menu, tabs, dialogs, shortcuts and the skip link.

Run with the API on :8077 and Google Chrome installed:
    ./.venv/bin/python tests/a11y_components.py
"""
import sys
from playwright.sync_api import sync_playwright

API = "http://127.0.0.1:8077"
checks = []


def check(name, ok, detail=""):
    checks.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{('  -> ' + str(detail)) if detail else ''}")


with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    pg = br.new_context(viewport={"width": 1440, "height": 900}).new_page()
    pg.goto(f"{API}/index.html")
    pg.fill("#email", "admin@smartpark.in"); pg.fill("#password", "Parking@123"); pg.click("#submit")
    pg.wait_for_url("**/dashboard.html", timeout=15000)

    print("\nSkip link and landmarks")
    pg.goto(f"{API}/customers.html"); pg.wait_for_timeout(1800)
    pg.keyboard.press("Tab")
    first = pg.evaluate("() => document.activeElement.textContent.trim()")
    check("first Tab lands on the skip link", first == "Skip to content", first)
    pg.keyboard.press("Enter"); pg.wait_for_timeout(200)
    check("skip link moves focus to main", pg.evaluate("() => document.activeElement.id") == "main")
    check("breadcrumb is a labelled nav",
          pg.evaluate("() => !!document.querySelector('nav.crumbs[aria-label=Breadcrumb] [aria-current=page]')"))

    print("\nData table")
    pg.focus("th[data-col='3'] .dt-sort"); pg.keyboard.press("Enter"); pg.wait_for_timeout(150)
    sort1 = pg.get_attribute("th[data-col='3']", "aria-sort")
    pg.keyboard.press("Enter"); pg.wait_for_timeout(150)
    sort2 = pg.get_attribute("th[data-col='3']", "aria-sort")
    check("header sorts by keyboard and reports aria-sort", (sort1, sort2) == ("ascending", "descending"),
          f"{sort1} -> {sort2}")
    check("table exposes ARIA roles", pg.evaluate(
        "() => !!document.querySelector('.dt table[role=table] tbody[role=rowgroup] tr[role=row] td[role=cell]')"))
    pg.keyboard.press("/")
    check("'/' focuses the page search", pg.evaluate("() => document.activeElement.matches('.dt-search input')"))
    pg.keyboard.type("zzzz"); pg.wait_for_timeout(400)
    check("no-match state is announced via the live count",
          pg.evaluate("() => document.querySelector('.dt-count').getAttribute('aria-live')") == "polite")
    pg.fill(".dt-search input", ""); pg.wait_for_timeout(300)

    print("\nActions menu")
    pg.focus("[data-dt-menu]"); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
    opened = pg.evaluate("() => ({ menu: !!document.querySelector('.menu[role=menu]'),"
                         " expanded: document.querySelector('[data-dt-menu][aria-expanded=true]') !== null,"
                         " focus: document.activeElement.getAttribute('role') })")
    check("Enter opens the menu with focus on the first item",
          opened["menu"] and opened["expanded"] and opened["focus"] == "menuitem", opened)
    pg.keyboard.press("ArrowDown")
    second = pg.evaluate("() => document.activeElement.textContent.trim()")
    check("ArrowDown moves between items", second == "Edit details", second)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    check("Escape closes and returns focus to the trigger", pg.evaluate(
        "() => !document.querySelector('.menu') && document.activeElement.hasAttribute('data-dt-menu')"))

    print("\nDialog")
    pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
    pg.keyboard.press("ArrowDown"); pg.keyboard.press("Enter"); pg.wait_for_timeout(600)
    dlg = pg.evaluate("() => { const m = document.querySelector('.scrim .modal'); return m && {"
                      " modal: m.getAttribute('aria-modal'), labelled: !!document.getElementById(m.getAttribute('aria-labelledby')),"
                      " focusInside: m.contains(document.activeElement) }; }")
    check("edit dialog is modal, labelled, and takes focus", dlg and dlg["modal"] == "true"
          and dlg["labelled"] and dlg["focusInside"], dlg)
    for _ in range(12):
        pg.keyboard.press("Tab")
    check("Tab stays trapped inside the dialog",
          pg.evaluate("() => document.querySelector('.scrim .modal').contains(document.activeElement)"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
    check("Escape closes the dialog", pg.evaluate("() => !document.querySelector('.scrim')"))

    print("\nTabs")
    pg.goto(f"{API}/billing.html"); pg.wait_for_timeout(1800)
    pg.focus("#tab-bills"); pg.keyboard.press("ArrowRight"); pg.wait_for_timeout(300)
    tab = pg.evaluate("() => ({ focus: document.activeElement.id,"
                      " selected: document.querySelector('#tab-ledger').getAttribute('aria-selected'),"
                      " roving: [...document.querySelectorAll('[role=tab]')].map(t => t.tabIndex).join(''),"
                      " panelShown: !document.getElementById('panel-ledger').hidden })")
    check("ArrowRight selects the next tab with a roving tabindex",
          tab == {"focus": "tab-ledger", "selected": "true", "roving": "-10", "panelShown": True}, tab)

    print("\nShortcuts")
    pg.keyboard.press("Escape")
    pg.evaluate("() => document.activeElement.blur()")
    pg.keyboard.press("?"); pg.wait_for_timeout(400)
    check("'?' opens the shortcut list", pg.evaluate(
        "() => document.querySelector('.scrim #modal-title')?.textContent") == "Keyboard shortcuts")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(400)
    pg.keyboard.press("g"); pg.keyboard.press("c"); pg.wait_for_url("**/customers.html", timeout=5000)
    check("G then C navigates to Customers", pg.url.endswith("/customers.html"), pg.url)

    print("\nReduced motion")
    rm = br.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce").new_page()
    rm.goto(f"{API}/index.html")
    rm.fill("#email", "admin@smartpark.in"); rm.fill("#password", "Parking@123"); rm.click("#submit")
    rm.wait_for_url("**/dashboard.html", timeout=15000); rm.wait_for_timeout(1200)
    still = rm.evaluate("() => [...document.querySelectorAll('.metric-value')].map(e => e.textContent.trim())")
    check("figures appear at their final value with no count-up", all(v and v != "0" for v in still), still)
    br.close()

print(f"\n{sum(checks)}/{len(checks)} component checks passed")
sys.exit(0 if all(checks) else 1)
