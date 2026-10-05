# Design concept and interaction logic

SmartPark v2 — the operations interface.

---

## 1. The idea in one line

**A parking structure drawn as an architectural plan, operated from a transit
control desk.**

Everything below follows from taking that literally rather than decoratively.

---

## 2. The one decision the rest hangs off

On an architectural plan, **a car is a solid object and an empty bay is an
outline.** So:

| State | How it is drawn | Why |
|---|---|---|
| **Free** | white fill, hairline edge, teal spine, tick | the absence of a thing |
| **Reserved** | dashed amber edge, corner tab, clock | spoken for, not yet filled |
| **Occupied** | **solid graphite fill, inverse text** | a car is a mass on a plan |
| **Out of service** | 45° hatch, grey | the standard plan notation for unusable |

The consequence is that **occupancy has visual weight**. A busy floor looks
dense and dark; a quiet one looks airy. An operator reads the load of the
building before reading a single number, and no legend is required to do it.

It also makes the map robust: state is carried by **four redundant channels** —
fill, colour, pattern and label+icon — so it survives greyscale printing, a
colour-blind operator, and a screen reader (every bay is a `<button>` with a
full `aria-label`).

---

## 3. What was recomposed, not restyled

### Five equal cards → one command strip

The previous dashboard had five interchangeable rounded cards. Interchangeable
is the problem: nothing said which mattered. They are now **one hairline-
segmented instrument bar** that reads left to right as a sentence about the
building — occupancy (largest, with a tick gauge), free, entries, collected,
outstanding (coral, because it is the only number that implies an action).

No boxes, no shadows. Separation is a 1px rule on a true grid line.

### A card containing a map → a recessed floor plate

The map is no longer a picture inside a card. The plate is a **darker ground
with an inner shadow and a faint 32px plan grid**, so it reads as the floor you
are looking down at. Bays sit *on* it. Zones are titled bands, each split into
two ranks with a **painted dashed aisle** between them, as on a real deck.

### A sidebar → an instrument rail

Welded to the page edge with a hard rule rather than floating. The active item
is marked by **one indicator element that translates between items**, so the
eye tracks a single object instead of watching two bars blink. Keyboard hints
(`D`, `M`, `G`…) appear on hover.

### Layout

Deliberately asymmetric: `minmax(0,1fr) 336px`. An equal split would claim the
revenue chart matters as much as the building. It does not.

---

## 4. The type and colour system

**Bricolage Grotesque** carries the display voice — variable across optical size
and width, with slightly irregular terminals that stop the interface reading as
a template. **IBM Plex Sans** runs the controls, drawn for exactly this density.
**IBM Plex Mono** with `tabular-nums` carries every number, plate, bay code and
clock, so columns align and an animated counter cannot shift the layout.

Grounds are **cool concrete**, not warm paper. Ink is charcoal. The accent is an
operational teal borrowed from wayfinding signage, with safety amber and a
restrained coral.

Two deliberate constraints:

- **Radius is tight** (3–6px). Parking structures are orthogonal, and a 12px
  radius on everything is the clearest single tell of a template dashboard.
- **Depth is used once.** Only things that genuinely float — the hover card,
  the side panel, a toast — carry a shadow. Everything else separates by tone
  and hairline.

Every colour is a token. `grep -c '#[0-9A-Fa-f]\{6\}' web/css/app.css` returns
**0**; the only literal colours outside `tokens.css` are the four in the
sign-in plan, and they are literal because Motion interpolates colour *values*
and cannot tween a custom property.

---

## 5. Interaction logic

Motion is built on the `motion` package (pinned 11.18.2) through its vanilla
entry point. Reduced motion is resolved **once**, in `web/js/motion.js`, and
consulted by all 15 helpers — no component repeats a media query, so none can
forget one.

| Behaviour | What happens | Where |
|---|---|---|
| **Bay state change** | Only bays whose state *actually changed* since the last poll animate — a 0.32s lift and colour settle. A refresh does not restage the floor | `applyBayChanges`, `flashBay` |
| **Bay hover** | A dark card gives vehicle, customer, time in, and running charge, positioned to stay on screen at the viewport edges. Suppressed on touch | `dashboard.js` `wireBays` |
| **Bay click** | A side panel opens **beside** the map, never over it — the operator keeps their place. Focus trapped, Escape closes, focus returns to the bay *re-queried by id* in case the map re-rendered | `bay-sheet.js` |
| **Counters** | Values count into place through `tabular-nums`, so nothing reflows | `countTo` |
| **Charts** | The line is plotted by `stroke-dashoffset` and the area wiped in beneath it, so a series appears measured rather than popped. Hover reads out the value; arrow keys do the same for keyboard | `charts.js`, `drawPath`, `wipeIn` |
| **Gate activity** | Only genuinely new events animate in and briefly tint; existing rows stay put | `insertLive` |
| **Navigation** | One indicator translates between items | `moveIndicator` |
| **Occupancy gauge** | 20 ticks fill in sequence, changing colour past 70% and 90% | `fillGauge` |
| **Live polling** | Every 30s, **paused while the tab is hidden**. The indicator shows the last update time and turns amber when stale | `dashboard.js` |

**Timing.** Feedback 0.12–0.18s, state changes 0.32s, panels 0.26s, entrances
0.42s. Nothing exceeds 0.5s: an operator waiting on an animation is an operator
being slowed down. Spring is permitted on hover and press only — the one place
overshoot reads as physical rather than sloppy — and never on anything carrying
text.

**Stagger is budgeted, not fixed.** A 94-bay floor at a flat 25ms would take
2.4 seconds and read as a loading fault. The per-item step is capped so any
list completes inside 0.5s.

---

## 6. The sign-in

Not a split screen with an empty half. The backdrop **is the product's subject
matter**: a facility plan in SVG where bays change state every couple of
seconds and a gate scan sweeps down every twelve.

Legibility is solved the way a drawing solves it — with a **title block**. Every
architectural drawing carries one: a solid panel in a corner holding the project
name and, along the bottom, the scale and revision. Here it holds the lede and
a strip reading BAYS / IN USE / LEVELS, **recounted from the plan actually on
screen**, so the panel can never state a number the drawing contradicts.

That is a better answer than a gradient scrim faked over a busy field, and a
much better one than a video: it is a few kilobytes, has no decode cost, stops
dead under `prefers-reduced-motion`, and cannot fight the form.

Demonstration accounts are **selectable credential chips** with role badges
rather than a collapsed disclosure the reader has to discover.

---

## 7. Responsive

| Width | Composition |
|---|---|
| **1440 / 1280** | Instrument rail, five-segment command strip, map + right rail |
| **1080** | Command strip folds to 3 + 2 |
| **900** | Rail becomes an overlay with a scrim; rail items stack under the map |
| **560** | Occupancy spans full width; **"Collected" folds away entirely** — on a phone the priorities are occupancy, urgent alerts and quick bay lookup. Each control group becomes one horizontally-scrollable row instead of wrapping, which gets the map above the fold |
| **380** | Bay meta hidden; four bays across stays legible |

Verified: `documentElement.scrollWidth === innerWidth` at 375, 768 and 1440.

---

## 8. What was audited, and what it found

Every check below is a script in `tests/`, runnable against the live app.

| Audit | Result |
|---|---|
| **Contrast as rendered** (`a11y_contrast.py`) — walks the real DOM, resolves each text node against its painted ancestor, **composes every ancestor opacity** | **0 below AA** across six pages |
| **Keyboard** (`a11y_keyboard.py`) | Tab order, visible focus ring, all 94 bays are labelled buttons, Enter opens, Escape closes, focus returns |
| **Reduced motion** | All **11** helpers assert-tested with the preference stubbed |
| **Page smoke** (`page_smoke.py`) | 10/10 pages render real content, no console errors, no page errors, no 4xx/5xx |
| **Imports** (`check_imports.py`) | Every named ES-module import resolves |
| **Tokens** | 0 undefined `var()` references; 0 raw hex in components; 0 orphaned class names |

Four of these caught real defects that visual review had not:

1. **`--ink-3` carrying readable text in 5 places** — including `.bay-meta`, the
   vehicle type on every bay. My own token file documents that value as
   decoration-only at 3.05:1. 195 elements were below AA; now 0.
2. **`opacity: .75` on the aisle marking** silently lowered effective contrast
   below AA while a naive audit read it as passing. The audit now composes
   opacity, and the opacity was removed.
3. **`gate.js` importing `flashSlot`** after the export was renamed to
   `flashBay` — a hard module-load error producing a **completely blank page
   with no console output**. The first version of the smoke test reported it as
   "ok" because a module `SyntaxError` arrives as a `pageerror`, not a console
   message.
4. **Focus lost on closing the bay panel** — closing triggered a refresh that
   re-rendered the map, so focus returned to a detached node and a keyboard
   user was dumped to the top of the document.

---

## 9. What is deliberately absent

Purple or indigo · `135deg` gradients · glassmorphism or `backdrop-filter` ·
neon glow or stacked shadows · infinite background animation · emoji as icons ·
mixed icon sets · "AI-powered", "seamless", "revolutionize", "supercharge" ·
lorem ipsum. All verified at zero by grep.

The three looping animations that remain are the spinner on an in-flight
button, the skeleton pulse, and the live-status dot — all of them status
indicators, and all of them stopped by the global reduced-motion rule.
