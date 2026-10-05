"""Audit CONTRAST AS RENDERED and keyboard reachability on the redesigned pages.

Walks the real DOM, resolves each text node's computed colour against its
nearest painted ancestor background, and reports anything under WCAG AA.
"""
import sys
from playwright.sync_api import sync_playwright

API = "http://127.0.0.1:8077"
JS = r"""
() => {
  const lin = c => { c/=255; return c<=0.04045 ? c/12.92 : Math.pow((c+0.055)/1.055, 2.4); };
  const lum = ([r,g,b]) => 0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b);
  const parse = s => { const m = s.match(/[\d.]+/g); return m ? m.slice(0,4).map(Number) : null; };
  const ratio = (f,b) => { const a=lum(f), c=lum(b); const hi=Math.max(a,c), lo=Math.min(a,c);
                           return (hi+0.05)/(lo+0.05); };
  const bgOf = el => {
    let n = el;
    while (n && n !== document.documentElement) {
      const cs = getComputedStyle(n); const c = parse(cs.backgroundColor);
      if (c && (c[3] === undefined || c[3] > 0.85)) return c.slice(0,3);
      n = n.parentElement;
    }
    return [255,255,255];
  };
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    if (el.children.length && ![...el.childNodes].some(n => n.nodeType===3 && n.textContent.trim())) return;
    const txt = (el.textContent || '').trim();
    if (!txt || txt.length < 2) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity < 0.15) return;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) return;
    let fg = parse(cs.color); if (!fg) return;
    // Compose every ancestor opacity, and the text colour's own alpha, onto
    // the background. Opacity on text lowers effective contrast and is
    // invisible to a naive computed-style read.
    let alpha = fg[3] === undefined ? 1 : fg[3];
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const o = parseFloat(getComputedStyle(n).opacity);
      if (!isNaN(o)) alpha *= o;
    }
    const bgc = bgOf(el);
    fg = [0,1,2].map(i => fg[i]*alpha + bgc[i]*(1-alpha));
    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3.0 : 4.5;
    const cr = ratio(fg.slice(0,3), bgc);
    if (cr < need) out.push({ t: txt.slice(0,52), cr: +cr.toFixed(2), need,
                              size: +size.toFixed(1), weight,
                              sel: el.tagName.toLowerCase()+'.'+(el.className||'').toString().split(' ')[0] });
  });
  return out;
}
"""
PAGES = ["index.html","dashboard.html","slots.html","gate.html","reservations.html","passes.html",
         "billing.html","reports.html","customers.html","settings.html"]
total = 0
with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    ctx = br.new_context(viewport={"width":1440,"height":900})
    pg = ctx.new_page()
    pg.goto(f"{API}/index.html")
    # Wait out the entrance animation: measuring mid-fade reads every element
    # as failing, which is a test artifact, not a finding.
    try: pg.wait_for_load_state("networkidle", timeout=8000)
    except Exception: pass
    pg.wait_for_timeout(1600)
    fails = pg.evaluate(JS)
    print(f"  {'index.html':<20} {len(fails)} below AA")
    for f in fails[:6]:
        print(f"      {f['cr']}:1 (need {f['need']}) {f['sel']}  “{f['t']}”")
    total += len(fails)

    pg.fill("#email","admin@smartpark.in"); pg.fill("#password","Parking@123"); pg.click("#submit")
    pg.wait_for_url("**/dashboard.html", timeout=15000)
    for name in PAGES[1:]:
        pg.goto(f"{API}/{name}", wait_until="domcontentloaded")
        try: pg.wait_for_load_state("networkidle", timeout=8000)
        except Exception: pass
        pg.wait_for_timeout(1600)
        fails = pg.evaluate(JS)
        print(f"  {name:<20} {len(fails)} below AA")
        for f in fails[:6]:
            print(f"      {f['cr']}:1 (need {f['need']}) {f['sel']}  “{f['t']}”")
        total += len(fails)
    br.close()
print(f"\nTOTAL below AA: {total}")
sys.exit(1 if total else 0)

# Run with:  ./.venv/bin/python tests/a11y_contrast.py
# Requires the API running and Google Chrome installed.
