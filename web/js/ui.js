/* ===========================================================================
   ui.js — shell, icons, and the four async states every list must have.
   =========================================================================== */
import { auth } from './api.js';
import {
  enter, openPanel, closePanel, bindInteractive, prefersReducedMotion,
  moveIndicator, insertLive, flashBay,
} from './motion.js';

/* One line-icon set, one stroke weight (1.6), drawn inline so there is no
   icon-font request and no second icon library. */
const ICONS = {
  gauge:    'M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm0 0 3.5-3.5M4 18a9 9 0 1 1 16 0',
  grid:     'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  gate:     'M4 20V8l8-4 8 4v12M4 20h16M9 20v-6h6v6',
  calendar: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4',
  ticket:   'M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2 2 2 0 0 0 0 4 2 2 0 0 1-2 2H6a2 2 0 0 1-2-2 2 2 0 0 0 0-4Z',
  receipt:  'M6 3v18l2-1.5L10 21l2-1.5L14 21l2-1.5L18 21V3zM9 8h6M9 12h6',
  chart:    'M4 20V10M10 20V4M16 20v-7M22 20H2',
  users:    'M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 20v-2a4 4 0 0 0-3-3.87',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8-3a8 8 0 0 1-.1 1.2l2 1.6-2 3.4-2.4-1a8 8 0 0 1-2 1.2l-.4 2.6h-4l-.4-2.6a8 8 0 0 1-2-1.2l-2.4 1-2-3.4 2-1.6A8 8 0 0 1 4 12a8 8 0 0 1 .1-1.2l-2-1.6 2-3.4 2.4 1a8 8 0 0 1 2-1.2L9 3h4l.4 2.6a8 8 0 0 1 2 1.2l2.4-1 2 3.4-2 1.6c.07.4.1.8.1 1.2Z',
  search:   'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.3-4.3',
  logout:   'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  menu:     'M4 7h16M4 12h16M4 17h16',
  close:    'M6 6l12 12M18 6L6 18',
  check:    'M4 12.5 9 17.5 20 6.5',
  alert:    'M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  info:     'M12 16v-4M12 8h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z',
  car:      'M5 16h14M6.5 16V9.5l1.8-3.5h7.4l1.8 3.5V16M8 19v-3M16 19v-3',
  inbox:    'M4 13h4l1.5 3h5L16 13h4M4 13 6.5 5h11L20 13v6H4z',
  plus:     'M12 5v14M5 12h14',
  clock:    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2',
  lock:     'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4',
  ban:      'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM5.6 5.6l12.8 12.8',
  refresh:  'M3 12a9 9 0 0 1 15.5-6.2L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.2L3 16M3 21v-5h5',
  'arrow-right': 'M5 12h14M13 6l6 6-6 6',
  'arrow-down':  'M12 5v14M6 13l6 6 6-6',
  'arrow-up':    'M12 19V5M6 11l6-6 6 6',
  filter:   'M3 5h18l-7 8v6l-4 2v-8z',
};

export function icon(name, cls = '') {
  const d = ICONS[name] || ICONS.info;
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true" focusable="false"><path d="${d}"/></svg>`;
}

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));

/* --- Formatting. Money and time in one place so no screen invents its own. */
export const money = (n) => '₹' + Number(n || 0).toLocaleString('en-IN',
  { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const moneyShort = (n) => '₹' + Number(n || 0).toLocaleString('en-IN',
  { maximumFractionDigits: 0 });

export function duration(mins) {
  const m = Math.max(0, Math.round(Number(mins) || 0));
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), r = m % 60;
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${String(r).padStart(2, '0')}m`;
  return `${r}m`;
}
export function dateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN',
    { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: true });
}
export function timeOnly(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('en-IN',
    { hour: '2-digit', minute: '2-digit', hour12: true });
}
export function dateOnly(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}
export const titleCase = (s) => String(s || '').replace(/_/g, ' ')
  .replace(/\b\w/g, (c) => c.toUpperCase());

/* --- The four async states ---------------------------------------------- */
export function skeleton(container, { rows = 5, kind = 'row' } = {}) {
  if (!container) return;
  const cls = kind === 'bay'    ? 'skeleton skeleton-bay'
            : kind === 'metric' ? 'skeleton skeleton-metric'
            : 'skeleton skeleton-row';
  container.innerHTML = `<div role="status" aria-live="polite">
    <span class="sr-only">Loading…</span>
    ${Array.from({ length: rows }, () => `<div class="${cls}"></div>`).join('')}
  </div>`;
}

/** Empty states name the next action. Never a bare "No data". */
export function empty(container, { title, body = '', action = null, iconName = 'inbox' } = {}) {
  if (!container) return;
  container.innerHTML = `
    <div class="empty">
      ${icon(iconName)}
      <div class="empty-title">${esc(title)}</div>
      ${body ? `<p>${esc(body)}</p>` : ''}
      ${action ? `<div class="empty-action">
        <a class="btn btn-primary" href="${esc(action.href)}">${esc(action.label)}</a>
      </div>` : ''}
    </div>`;
}

export function errorState(container, err, onRetry) {
  if (!container) return;
  const id = 'retry-' + Math.random().toString(36).slice(2, 8);
  container.innerHTML = `
    <div class="error-state" role="alert">
      ${icon('alert')}
      <div class="error-title">That did not load</div>
      <p>${esc(err?.message || 'Something went wrong.')}</p>
      ${onRetry ? `<div class="empty-action">
        <button class="btn" id="${id}">${icon('refresh')} Try again</button></div>` : ''}
    </div>`;
  if (onRetry) document.getElementById(id)?.addEventListener('click', onRetry);
}

export function emptyRow(tbody, colspan, title, body = '') {
  tbody.innerHTML = `<tr><td colspan="${colspan}" style="padding:0;border:0">
    <div class="empty" style="border:0;background:transparent">
      ${icon('inbox')}<div class="empty-title">${esc(title)}</div>
      ${body ? `<p>${esc(body)}</p>` : ''}
    </div></td></tr>`;
}

/* --- Toasts -------------------------------------------------------------- */
export function toast(title, body = '', kind = 'info') {
  let host = document.querySelector('.toasts');
  if (!host) {
    host = document.createElement('div');
    host.className = 'toasts';
    host.setAttribute('role', 'status');
    host.setAttribute('aria-live', 'polite');
    document.body.appendChild(host);
  }
  const el = document.createElement('div');
  el.className = `toast toast-${kind}`;
  el.innerHTML = `${icon(kind === 'error' ? 'alert' : kind === 'success' ? 'check' : 'info')}
    <div><div class="toast-title">${esc(title)}</div>
    ${body ? `<div class="toast-body">${esc(body)}</div>` : ''}</div>`;
  host.appendChild(el);
  enter(el, {});
  setTimeout(() => {
    el.style.transition = 'opacity .2s, transform .2s';
    el.style.opacity = '0'; el.style.transform = 'translateY(6px)';
    setTimeout(() => el.remove(), 220);
  }, kind === 'error' ? 6000 : 3600);
}

/* --- Modal --------------------------------------------------------------
   Focus is trapped while open and returned to the trigger on close, and Escape
   always closes. */
let openModals = 0;
export function modal({ title, body, actions = [], onMount = null, width = null }) {
  const previouslyFocused = document.activeElement;
  const scrim = document.createElement('div');
  scrim.className = 'scrim';
  scrim.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"
         ${width ? `style="width:min(${width},100%)"` : ''}>
      <div class="modal-head">
        <h2 id="modal-title">${esc(title)}</h2>
        <button class="btn btn-icon" data-close aria-label="Close dialog">${icon('close')}</button>
      </div>
      <div class="modal-body">${body}</div>
      ${actions.length ? `<div class="modal-foot">${actions.map((a, i) =>
        `<button class="btn ${a.variant ? 'btn-' + a.variant : ''}" data-action="${i}"
          ${a.type === 'submit' ? 'type="submit"' : ''}>${esc(a.label)}</button>`).join('')}</div>` : ''}
    </div>`;
  document.body.appendChild(scrim);
  document.body.style.overflow = 'hidden';
  openModals++;

  const panel = scrim.querySelector('.modal');
  openPanel(scrim, panel);

  const close = async () => {
    await closePanel(scrim, panel);
    scrim.remove();
    if (--openModals <= 0) { openModals = 0; document.body.style.overflow = ''; }
    previouslyFocused?.focus?.();
  };

  scrim.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', close));
  scrim.addEventListener('mousedown', (e) => { if (e.target === scrim) close(); });

  actions.forEach((a, i) => {
    scrim.querySelector(`[data-action="${i}"]`)?.addEventListener('click', () => a.onClick?.(close, scrim));
  });

  const focusables = () => scrim.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
  scrim.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (e.key !== 'Tab') return;
    const f = Array.from(focusables());
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  (scrim.querySelector('input, select, textarea, button:not([data-close])')
    || scrim.querySelector('[data-close]'))?.focus();

  onMount?.(scrim, close);
  bindInteractive(scrim);
  return { close, root: scrim };
}

export function confirmDialog(title, message, confirmLabel = 'Confirm') {
  return new Promise((resolve) => {
    let settled = false;
    const m = modal({
      title,
      body: `<p>${esc(message)}</p>`,
      actions: [
        { label: 'Cancel', onClick: (c) => { settled = true; resolve(false); c(); } },
        { label: confirmLabel, variant: 'primary',
          onClick: (c) => { settled = true; resolve(true); c(); } },
      ],
    });
    m.root.addEventListener('transitionend', () => {}, { once: true });
    const obs = new MutationObserver(() => {
      if (!document.body.contains(m.root)) { obs.disconnect(); if (!settled) resolve(false); }
    });
    obs.observe(document.body, { childList: true });
  });
}

/* --- Form helpers -------------------------------------------------------- */
export function fieldError(input, message) {
  const field = input.closest('.field');
  if (!field) return;
  field.dataset.invalid = message ? 'true' : 'false';
  input.setAttribute('aria-invalid', message ? 'true' : 'false');
  let el = field.querySelector('.field-error');
  if (!el) {
    el = document.createElement('div');
    el.className = 'field-error';
    el.id = (input.id || 'f') + '-error';
    field.appendChild(el);
  }
  input.setAttribute('aria-describedby', el.id);
  el.innerHTML = message ? `${icon('alert')} ${esc(message)}` : '';
}

export function clearErrors(form) {
  form.querySelectorAll('.field').forEach((f) => { f.dataset.invalid = 'false'; });
  form.querySelectorAll('.field-error').forEach((e) => { e.innerHTML = ''; });
}

/** Disable the submit button while a request is in flight, so a double-click
 *  cannot open two sessions. */
export async function submitting(btn, fn) {
  if (!btn) return fn();
  const wasDisabled = btn.disabled;
  btn.disabled = true; btn.dataset.busy = 'true';
  try { return await fn(); }
  finally { btn.disabled = wasDisabled; delete btn.dataset.busy; }
}

/* --- Shell --------------------------------------------------------------- */
const NAV = [
  { group: 'Operations', items: [
    { href: 'dashboard.html',    label: 'Dashboard',    icon: 'gauge',    key: 'D' },
    { href: 'slots.html',        label: 'Floor map',    icon: 'grid',     key: 'M' },
    { href: 'gate.html',         label: 'Gate',         icon: 'gate',     key: 'G', staff: true },
    { href: 'reservations.html', label: 'Reservations', icon: 'calendar', key: 'R' },
    { href: 'passes.html',       label: 'Passes',       icon: 'ticket',   key: 'P' },
  ]},
  { group: 'Money', items: [
    { href: 'billing.html', label: 'Billing', icon: 'receipt', key: 'B' },
    { href: 'reports.html', label: 'Reports', icon: 'chart',   key: 'A' },
  ]},
  { group: 'Records', items: [
    { href: 'customers.html', label: 'Customers', icon: 'users',    key: 'C' },
    { href: 'settings.html',  label: 'Settings',  icon: 'settings', key: 'S', admin: true },
  ]},
];

export function requireAuth() {
  if (!auth.token) { location.href = 'index.html'; return null; }
  return auth.user;
}

export function mountShell(active, { title, subtitle = '', actions = '', metrics = false } = {}) {
  const user = requireAuth();
  if (!user) return null;

  const initials = (user.name || '?').split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();
  const navHtml = NAV.map((g) => {
    const items = g.items.filter((i) =>
      (!i.staff || auth.isStaff) && (!i.admin || user.role === 'admin'));
    if (!items.length) return '';
    return `<div class="nav-group">${esc(g.group)}</div>` + items.map((i) => `
      <a class="nav-link" href="${i.href}" ${i.href === active ? 'aria-current="page"' : ''}>
        ${icon(i.icon)}<span>${esc(i.label)}</span>
        <span class="nav-key" aria-hidden="true">${esc(i.key || '')}</span></a>`).join('');
  }).join('');

  document.body.innerHTML = `
    <a class="skip-link" href="#main">Skip to content</a>
    <div class="shell">
      <aside class="rail" id="rail">
        <div class="brand">
          <div class="brand-mark" aria-hidden="true">SP</div>
          <div><div class="brand-name">SmartPark</div>
               <div class="brand-sub">Control</div></div>
        </div>
        <nav class="nav" aria-label="Main">
          <span class="nav-indicator" id="nav-indicator" aria-hidden="true"></span>
          ${navHtml}
        </nav>
        <div class="rail-foot">
          <div class="who">
            <div class="who-avatar" aria-hidden="true">${esc(initials)}</div>
            <div style="flex:1;min-width:0">
              <div class="who-name">${esc(user.name)}</div>
              <div class="who-role">${esc(user.role)}</div>
            </div>
            <button class="btn btn-icon btn-ghost" id="signout"
                    aria-label="Sign out" title="Sign out">${icon('logout')}</button>
          </div>
        </div>
      </aside>
      <div class="main">
        <header class="command">
          <div class="command-top">
            <button class="btn btn-icon menu-btn" id="menu-btn" style="display:none"
                    aria-label="Open navigation" aria-expanded="false"
                    aria-controls="rail">${icon('menu')}</button>
            <div class="command-title">
              <h1>${esc(title)}</h1>
              ${subtitle ? `<div class="sub">${esc(subtitle)}</div>` : ''}
            </div>
            <div class="command-spacer"></div>
            <div id="command-actions" style="display:flex;gap:var(--s3);align-items:center">
              ${actions}
            </div>
          </div>
          ${metrics ? '<div class="metrics" id="metrics"></div>' : ''}
        </header>
        <main class="content" id="main" tabindex="-1"></main>
      </div>
    </div>`;

  document.getElementById('signout').addEventListener('click', () => {
    auth.clear(); location.href = 'index.html';
  });

  // The active-state indicator is positioned after layout, then follows the
  // pointer across the nav so the transition is continuous rather than two
  // separate items blinking.
  const indicator = document.getElementById('nav-indicator');
  const current = document.querySelector('.nav-link[aria-current="page"]');
  const settle = () => moveIndicator(indicator, current, { instant: true });
  requestAnimationFrame(settle);
  window.addEventListener('resize', settle);
  document.querySelectorAll('.nav-link').forEach((link) => {
    link.addEventListener('pointerenter', () => moveIndicator(indicator, link));
    link.addEventListener('focus',        () => moveIndicator(indicator, link));
  });
  document.querySelector('.nav')?.addEventListener('pointerleave',
    () => moveIndicator(indicator, current));

  // Mobile rail, with a scrim so the page behind is obviously inert.
  const rail = document.getElementById('rail');
  const menuBtn = document.getElementById('menu-btn');
  let scrim = null;
  const setRail = (open) => {
    rail.dataset.open = String(open);
    menuBtn.setAttribute('aria-expanded', String(open));
    if (open && !scrim) {
      scrim = document.createElement('div');
      scrim.className = 'rail-scrim';
      scrim.addEventListener('click', () => setRail(false));
      document.body.appendChild(scrim);
    } else if (!open && scrim) { scrim.remove(); scrim = null; }
  };
  menuBtn.addEventListener('click', () => setRail(rail.dataset.open !== 'true'));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && rail.dataset.open === 'true') { setRail(false); menuBtn.focus(); }
  });

  bindInteractive(document);
  return { user, content: document.getElementById('main'),
           metrics: document.getElementById('metrics') };
}


/* ---------------------------------------------------------------------------
   The bay, rendered once here and reused by every screen that draws the map.

   Four redundant channels per state, so the map survives greyscale printing
   and colour-blind operators: FILL (solid graphite vs open outline), COLOUR,
   PATTERN (dashed edge, 45-degree hatch) and LABEL + ICON.
   --------------------------------------------------------------------------- */
export const BAY_ICON = {
  free: 'check', occupied: 'car', reserved: 'clock', out_of_service: 'ban',
};
export const BAY_WORD = {
  free: 'Free', occupied: 'Occupied', reserved: 'Reserved', out_of_service: 'Offline',
};

/* A car seen from above, seated in an occupied bay. This is the one image that
   turns the map from a grid of records into a picture of a floor: a filled bay
   already reads as "taken", but a vehicle in it reads as "a car is parked here".
   Kept to a faint watermark on the right of the bay so the plate stays legible;
   built from translucent whites so it sits INSIDE the graphite fill rather than
   on top of it. Decorative — the state is already carried by fill, colour,
   pattern, icon and label, so this is aria-hidden. */
const BAY_CAR = `<svg class="bay-car" viewBox="0 0 30 46" aria-hidden="true" focusable="false">
  <rect class="bay-car-body" x="4.5" y="2.5" width="21" height="41" rx="6.5"/>
  <path class="bay-car-glass" d="M8 9.5h14v6.5H8z"/>
  <path class="bay-car-glass" d="M8 30h14v7H8z"/>
  <path class="bay-car-roof" d="M8.5 18.5h13v9h-13z"/>
</svg>`;

export function bayHTML(s, { interactive: inter = true } = {}) {
  const word = BAY_WORD[s.slot_state] || titleCase(s.slot_state);
  const meta = s.slot_state === 'occupied' ? (s.plate_number || '')
    : s.slot_state === 'reserved' ? 'Held'
    : (s.vehicle_type_code || '');
  const label = `Bay ${s.slot_code}, ${word}` +
    (s.plate_number ? `, vehicle ${s.plate_number}` : '') +
    `, built for ${s.vehicle_type_name || s.vehicle_type_code || 'any vehicle'}`;
  const tag = inter ? 'button' : 'div';
  return `<${tag} class="bay" ${inter ? 'type="button" data-interactive' : ''}
      data-state="${esc(s.slot_state)}" data-slot-id="${s.slot_id}"
      ${inter ? `aria-label="${esc(label)}. Show details."` : `role="img" aria-label="${esc(label)}"`}>
    ${s.slot_state === 'occupied' ? BAY_CAR : ''}
    <span class="bay-code mono">${esc(s.slot_code)}</span>
    <span class="bay-state">${icon(BAY_ICON[s.slot_state] || 'info')}${esc(word)}</span>
    <span class="bay-meta">${esc(meta)}</span>
  </${tag}>`;
}

/* Group a flat slot list into floor -> zone bands, preserving plan order. */
export function groupByZone(slots) {
  const m = new Map();
  for (const s of slots) {
    const key = `${String(s.level_number).padStart(3, '0')}|${s.floor_name}|${s.zone_code}`;
    if (!m.has(key)) m.set(key, []);
    m.get(key).push(s);
  }
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

/* One zone drawn as two ranks of bays with a painted aisle between them. */
export function zoneHTML([key, group], opts = {}) {
  const [, floorName, zoneCode] = key.split('|');
  const free = group.filter((s) => s.slot_state === 'free').length;
  const occupied = group.filter((s) => s.slot_state === 'occupied').length;
  const pct = group.length ? Math.round((occupied / group.length) * 100) : 0;
  const half = Math.ceil(group.length / 2);
  return `<section class="zone" aria-label="${esc(floorName)} Zone ${esc(zoneCode)}">
    <div class="zone-head">
      <span class="zone-name">${esc(floorName)} · Zone ${esc(zoneCode)}</span>
      <span class="zone-meta">${free}/${group.length} free</span>
      <span class="zone-fill">
        <span class="label" style="font-size:var(--t-2xs)">${pct}%</span>
        <span class="zone-fill-bar"><i style="width:${pct}%"></i></span>
      </span>
    </div>
    <div class="rank">${group.slice(0, half).map((s) => bayHTML(s, opts)).join('')}</div>
    <div class="aisle" aria-hidden="true"><span>aisle</span></div>
    <div class="rank">${group.slice(half).map((s) => bayHTML(s, opts)).join('')}</div>
  </section>`;
}

/** Remembers the operator's facility choice between screens. */
export const facility = {
  get() { try { return Number(localStorage.getItem('smartpark.facility')) || null; } catch { return null; } },
  set(id) { try { localStorage.setItem('smartpark.facility', String(id)); } catch {} },
};

export { prefersReducedMotion, insertLive, flashBay };
