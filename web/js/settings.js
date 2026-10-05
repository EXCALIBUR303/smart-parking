/* settings.js — facility structure and tariff administration (admin only). */
import { api, auth } from './api.js';
import {
  mountShell, icon, esc, money, dateOnly, titleCase, errorState, emptyRow,
  modal, toast, fieldError, clearErrors, submitting,
} from './ui.js';
import { enter, revealList, bindInteractive } from './motion.js';

const ctx = mountShell('settings.html', {
  title: 'Settings',
  subtitle: 'Facilities, vehicle types and tariffs',
});
if (ctx) init(ctx);

async function init({ content, user }) {
  if (user.role !== 'admin') {
    errorState(content, { message: 'Settings are restricted to administrator accounts.' });
    return;
  }

  content.innerHTML = `
    <section class="card" style="margin-bottom:var(--s5)">
      <div class="card-head"><h2>Facilities</h2>
        <span class="hint">Structure is seeded by migration; this is a read-only view</span></div>
      <div id="facilities"></div>
    </section>

    <section class="card" style="margin-bottom:var(--s5)">
      <div class="card-head"><h2>Vehicle types</h2></div>
      <div id="types"></div>
    </section>

    <section class="card">
      <div class="card-head"><h2>Tariffs</h2>
        <div class="spacer"></div>
        <button class="btn btn-primary btn-sm" id="new-tariff" data-interactive>
          ${icon('plus')} New tariff</button></div>
      <p class="section-note" style="margin-top:0">
        A tariff is never edited in place. Opening a new one closes the tariff it
        supersedes with an end date, so a bill raised last month can still be
        re-derived from the rates that applied then. An exclusion constraint
        stops two tariffs being in force for one facility and vehicle type at
        the same instant.
      </p>
      <div id="tariffs"></div>
    </section>`;

  enter(content.querySelector('.card'));
  content.querySelector('#new-tariff').addEventListener('click', () => newTariff(load));
  load();

  async function load() {
    let facilities, types, tariffs;
    try {
      [facilities, types, tariffs] = await Promise.all([
        api.facilities(), api.vehicleTypes(), api.tariffs()]);
    } catch (err) { errorState(content, err, load); return; }

    content.querySelector('#facilities').innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr><th scope="col">Name</th><th scope="col">Address</th>
          <th scope="col">Hours</th><th scope="col" class="num">Tax rate</th></tr></thead>
        <tbody>${facilities.map((f) => `<tr>
          <td>${esc(f.name)}</td>
          <td>${esc(f.address_line)}, ${esc(f.city)}</td>
          <td class="mono">${esc(String(f.opens_at).slice(0, 5))}–${
            esc(String(f.closes_at).slice(0, 5))}</td>
          <td class="num mono">${esc(f.tax_rate_pct)}%</td></tr>`).join('')}</tbody>
      </table></div>`;

    content.querySelector('#types').innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr><th scope="col">Code</th><th scope="col">Name</th></tr></thead>
        <tbody>${types.map((t) => `<tr>
          <td class="mono">${esc(t.code)}</td><td>${esc(t.name)}</td></tr>`).join('')}</tbody>
      </table></div>`;

    const host = content.querySelector('#tariffs');
    if (!tariffs.length) {
      host.innerHTML = '';
      emptyRow(host, 1, 'No tariffs configured', 'Add one so exits can be billed.');
      return;
    }
    host.innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr><th scope="col">Facility</th><th scope="col">Vehicle type</th>
          <th scope="col" class="num">Free</th><th scope="col" class="num">First hour</th>
          <th scope="col" class="num">Thereafter</th><th scope="col" class="num">Daily cap</th>
          <th scope="col">In force</th></tr></thead>
        <tbody>${tariffs.map((t) => `<tr${t.in_force ? '' : ' style="opacity:.62"'}>
          <td>${esc(t.facility_name)}</td>
          <td>${esc(t.vehicle_type_name)}</td>
          <td class="num mono">${t.free_minutes}m</td>
          <td class="num money">${esc(money(t.first_hour_rate))}</td>
          <td class="num money">${esc(money(t.subsequent_hour_rate))}</td>
          <td class="num money">${esc(money(t.daily_cap))}</td>
          <td>${t.in_force
            ? '<span class="badge badge-active">Current</span>'
            : `<span class="badge badge-neutral">Until ${esc(dateOnly(t.effective_to))}</span>`}
          </td></tr>`).join('')}</tbody>
      </table></div>`;
    revealList(host.querySelectorAll('tbody tr'), { step: 0.015 });
  }
}

async function newTariff(onDone) {
  let facilities, types;
  try { [facilities, types] = await Promise.all([api.facilities(), api.vehicleTypes()]); }
  catch (err) { toast('Could not open the form', err.message, 'error'); return; }

  modal({
    title: 'Open a new tariff',
    width: '620px',
    body: `
      <p style="color:var(--ink-2);font-size:var(--t-sm);margin-bottom:var(--s4)">
        The tariff currently in force for this facility and vehicle type will be
        closed with today's date. Bills already raised keep their original rates.
      </p>
      <form id="t-form" novalidate>
        <div class="form-row">
          <div class="field"><label for="t-facility">Facility</label>
            <select class="select" id="t-facility" required>${facilities.map((f) =>
              `<option value="${f.facility_id}">${esc(f.name)}</option>`).join('')}</select>
            <div class="field-error"></div></div>
          <div class="field"><label for="t-type">Vehicle type</label>
            <select class="select" id="t-type" required>${types.map((t) =>
              `<option value="${t.vehicle_type_id}">${esc(t.name)}</option>`).join('')}</select>
            <div class="field-error"></div></div>
        </div>
        <div class="field"><label for="t-name">Name</label>
          <input class="input" id="t-name" required placeholder="SmartPark Central — Car, 2026 rates">
          <div class="field-error"></div></div>
        <div class="form-row">
          <div class="field"><label for="t-free">Free minutes</label>
            <input class="input mono" type="number" id="t-free" value="15" min="0" max="1440" required>
            <div class="field-error"></div></div>
          <div class="field"><label for="t-first">First hour (₹)</label>
            <input class="input mono" type="number" id="t-first" value="40" min="0" step="1" required>
            <div class="field-error"></div></div>
        </div>
        <div class="form-row">
          <div class="field"><label for="t-next">Each hour after (₹)</label>
            <input class="input mono" type="number" id="t-next" value="25" min="0" step="1" required>
            <div class="field-error"></div></div>
          <div class="field"><label for="t-cap">Daily cap (₹)</label>
            <input class="input mono" type="number" id="t-cap" value="250" min="0" step="1" required>
            <div class="help">Cannot be lower than the first-hour rate.</div>
            <div class="field-error"></div></div>
        </div>
      </form>`,
    actions: [
      { label: 'Cancel', onClick: (c) => c() },
      { label: 'Open tariff', variant: 'primary', onClick: submit },
    ],
  });

  async function submit(close, scrim) {
    const form = scrim.querySelector('#t-form');
    clearErrors(form);
    const g = (id) => scrim.querySelector(id);
    const name = g('#t-name'), free = g('#t-free'), first = g('#t-first');
    const next = g('#t-next'), cap = g('#t-cap');

    let bad = false;
    if (!name.value.trim()) { fieldError(name, 'Give the tariff a name.'); bad = true; }
    for (const [el, label] of [[free, 'Free minutes'], [first, 'First hour'],
                               [next, 'Hourly rate'], [cap, 'Daily cap']]) {
      if (el.value === '' || Number(el.value) < 0) {
        fieldError(el, `${label} cannot be blank or negative.`); bad = true;
      }
    }
    if (!bad && Number(cap.value) < Number(first.value)) {
      fieldError(cap, 'The daily cap cannot be lower than the first-hour rate.'); bad = true;
    }
    if (bad) { scrim.querySelector('[aria-invalid="true"]')?.focus(); return; }

    const btn = scrim.querySelector('[data-action="1"]');
    await submitting(btn, async () => {
      try {
        await api.createTariff({
          facility_id: Number(g('#t-facility').value),
          vehicle_type_id: Number(g('#t-type').value),
          name: name.value.trim(),
          free_minutes: Number(free.value),
          first_hour_rate: Number(first.value),
          subsequent_hour_rate: Number(next.value),
          daily_cap: Number(cap.value),
        });
        toast('Tariff opened', 'New arrivals will be billed at these rates.', 'success');
        close(); onDone();
      } catch (err) { fieldError(name, err.message); }
    });
  }
}
