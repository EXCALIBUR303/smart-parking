from playwright.sync_api import sync_playwright
import sys
API = "http://127.0.0.1:8077"
with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    pg = br.new_context(viewport={"width":1440,"height":900}).new_page()
    pg.goto(f"{API}/index.html"); pg.wait_for_timeout(1200)

    # 1. Sign-in reachable by keyboard alone.
    order = []
    for _ in range(12):
        pg.keyboard.press("Tab")
        order.append(pg.evaluate("()=>{const a=document.activeElement;"
                                 "return (a.tagName+':'+(a.getAttribute('aria-label')||a.textContent||a.placeholder||'').trim().slice(0,34))}"))
    print("sign-in tab order:")
    for o in order[:8]: print("   ", o)

    # 2. Focus ring is actually painted.
    ring = pg.evaluate("""()=>{const b=document.getElementById('submit'); b.focus();
      const cs=getComputedStyle(b);
      return {outlineWidth: cs.outlineWidth, outlineStyle: cs.outlineStyle, outlineColor: cs.outlineColor};}""")
    print("focus ring on submit:", ring)

    pg.fill("#email","admin@smartpark.in"); pg.fill("#password","Parking@123"); pg.click("#submit")
    pg.wait_for_url("**/dashboard.html", timeout=15000); pg.wait_for_timeout(2500)

    # 3. Every bay is a real button, reachable and operable by keyboard.
    r = pg.evaluate("""()=>{
      const bays=[...document.querySelectorAll('.bay')];
      return { total: bays.length,
               allButtons: bays.every(b=>b.tagName==='BUTTON'),
               allLabelled: bays.every(b=>(b.getAttribute('aria-label')||'').length>10),
               sampleLabel: bays[0]?.getAttribute('aria-label') };}""")
    print("bays:", r)

    # 4. Enter on a focused bay opens the sheet; Escape closes and returns focus.
    pg.evaluate("() => document.querySelector('.bay[data-state=' + JSON.stringify('occupied') + ']').focus()")
    pg.keyboard.press("Enter"); pg.wait_for_timeout(700)
    opened = pg.evaluate("()=>!!document.querySelector('.sheet')")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(700)
    closed = pg.evaluate("()=>!document.querySelector('.sheet')")
    back = pg.evaluate("()=>document.activeElement.classList.contains('bay')")
    print(f"bay keyboard: opens={opened} closes={closed} focusReturns={back}")

    # 5. Segmented filter and level markers are operable.
    ops = pg.evaluate("""()=>{
      const seg=[...document.querySelectorAll('#state-filter button')];
      const lv=[...document.querySelectorAll('.level')];
      return { segButtons: seg.length, segHasPressed: seg.some(b=>b.getAttribute('aria-pressed')==='true'),
               levelButtons: lv.length, levelHasPressed: lv.some(b=>b.getAttribute('aria-pressed')==='true'),
               chartFocusable: document.querySelector('.chart')?.getAttribute('tabindex')==='0' };}""")
    print("controls:", ops)

    ok = (ring["outlineStyle"]=="solid" and r["allButtons"] and r["allLabelled"]
          and opened and closed and back and ops["segHasPressed"] and ops["chartFocusable"])
    print("\nVERDICT:", "KEYBOARD AND LABELLING PASS" if ok else "PROBLEM")
    br.close()
    sys.exit(0 if ok else 1)
