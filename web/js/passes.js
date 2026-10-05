/* passes.js — sell, validate and cancel parking passes. */
import { api, auth } from './api.js';
import {
  mountShell, icon, esc, money, moneyShort, dateOnly, duration, titleCase,
  emptyRow, errorState, modal, toast, fieldError, clearErrors, submitting, confirmDialog,
} from './ui.js';
import { enter, revealList, countTo, bindInteractive } from './motion.js';

const ctx = mountShell('passes.html', {
  title: 'Passes',
  subtitle: 'Season tickets and their usage',
});
if (ctx) init(ctx);

async function init({ content }) {
  content.innerHTML = `
    <div class="toolbar">
      <label class="sr-only" for="state">State</label>
      <select class="select" id="state" style="max-width:190px">
        <option value="all">All passes</option>
        <option value="active">Active</option>
        <option value="scheduled">Scheduled</option>
        <option value="expired">Expired</option>
        <option value="cancelled">Cancelled</option>
      </select>
      <div class="spacer"></div>
      <button class="btn btn-primary" id="sell" data-interactive>${icon('plus')} Sell a pass</button>
    </div>
    <div id="stats" class="stat-row"></div>
    <p class="section-note">
      A pass covers every stay it spans, so those sessions bill at zero. One
      vehicle cannot hold two live passes at the same facility over the same
      dates — the database rejects the overlap.
    </p>
    <section class="card">
      <div class="table-wrap">
        <table><caption class="sr-only">Passes</caption>
          <thead><tr>
            <th scope="col">Customer</th><th scope="col">Vehicle</th><th scope="col">Product</th>
            <th scope="col">Valid</th><th scope="col" class="num">Paid</th>
            <th scope="col" class="num">Used</th><th scope="col">State</th><th scope="col"></th>
          </tr></thead><tbody id="rows"></tbody></table>
      </div>
    </section>`;

  const sel = content.querySelector('#state');
  sel.addEventListener('change', render);
  content.querySelector('#sell').addEventListener('click', () => sellPass(load));
  enter(content.querySelector('.card'));

  let all = [];
  load();

  async function load() {
    const tbody = content.querySelector('#rows');
    tbody.innerHTML = `<tr><td colspan="8" style="padding:var(--s4);border:0">
      <div class="skeleton skeleton-row"></div><div class="skeleton skeleton-row"></div></td></tr>`;
    try { all = await api.passes(); }
    catch (err) {
      tbody.innerHTML = '<tr><td colspan="8" style="padding:0;border:0"></td></tr>';
      errorState(tbody.querySelector('td'), err, load); return;
    }
    renderStats();
    render();
  }

  function renderStats() {
    const n = (s) => all.filter((p) => p.pass_state === s).length;
    const revenue = all.filter((p) => p.pass_state !== 'cancelled')
                       .reduce((a, p) => a + Number(p.price_paid || 0), 0);
    const host = content.querySelector('#stats');
    host.innerHTML = `
      <div class="stat"><div class="stat-label">${icon('ticket')} Active now</div>
        <div class="stat-value" data-count="${n('active')}">0</div>
        <div class="stat-foot">${n('scheduled')} starting later</div></div>
      <div class="stat"><div class="stat-label">${icon('clock')} Expired</div>
        <div class="stat-value" data-count="${n('expired')}">0</div>
        <div class="stat-foot">${n('cancelled')} cancelled</div></div>
      <div class="stat stat-accent"><div class="stat-label">${icon('receipt')} Pass revenue</div>
        <div class="stat-value" data-count="${revenue}" data-money="1">₹0</div>
        <div class="stat-foot">across ${all.length} passes sold</div></div>
      <div class="stat"><div class="stat-label">${icon('car')} Stays covered</div>
        <div class="stat-value" data-count="${all.reduce((a, p) => a + Number(p.sessions_used || 0), 0)}">0</div>
        <div class="stat-foot">sessions billed at zero</div></div>`;
    revealList(host.querySelectorAll('.stat'));
    host.querySelectorAll('[data-count]').forEach((el) => countTo(el, Number(el.dataset.count),
      { format: el.dataset.money ? moneyShort : (v) => Math.round(v).toLocaleString('en-IN') }));
  }

  function render() {
    const tbody = content.querySelector('#rows');
    const rows = sel.value === 'all' ? all : all.filter((p) => p.pass_state === sel.value);
    if (!rows.length) {
      emptyRow(tbody, 8,
        sel.value === 'all' ? 'No passes sold yet' : `No ${sel.value} passes`,
        sel.value === 'all' ? 'Use Sell a pass to issue the first one.'
                            : 'Try a different state filter.');
      return;
    }
    tbody.innerHTML = rows.map((p) => `<tr>
      <td>${esc(p.customer_name)}</td>
      <td class="plate">${esc(p.plate_number)}</td>
      <td>${esc(p.pass_type_name)}</td>
      <td class="mono" style="white-space:nowrap">${esc(dateOnly(p.valid_from))}
        <span style="color:var(--ink-2)">→</span> ${esc(dateOnly(p.valid_to))}
        ${p.pass_state === 'active' ? `<div style="color:var(--ink-2);font-size:var(--t-xs)">${
          p.days_remaining} days left</div>` : ''}</td>
      <td class="num money">${esc(money(p.price_paid))}</td>
      <td class="num mono">${p.sessions_used}
        <div style="color:var(--ink-2);font-size:var(--t-xs)">${
          esc(duration(p.minutes_used))}</div></td>
      <td><span class="badge badge-${esc(p.pass_state)}">${esc(titleCase(p.pass_state))}</span></td>
      <td style="text-align:right">
        ${(p.pass_state === 'active' || p.pass_state === 'scheduled')
          ? `<button class="btn btn-sm btn-danger" data-cancel="${p.pass_id}"
               data-interactive>Cancel</button>` : ''}</td>
    </tr>`).join('');
    revealList(tbody.querySelectorAll('tr'), { step: 0.018 });
    bindInteractive(tbody);
    tbody.querySelectorAll('[data-cancel]').forEach((b) => b.addEventListener('click', async () => {
      if (!await confirmDialog('Cancel this pass?',
        'The pass stops covering stays from now on. It stays on record for the usage report.',
        'Cancel pass')) return;
      try {
        await api.cancelPass(b.dataset.cancel);
        toast('Pass cancelled', 'Future stays will be billed at tariff.', 'success');
        load();
      } catch (err) { toast('Could not cancel the pass', err.message, 'error'); }
    }));
  }
}

async function sellPass(onDone) {
  let customers, passTypes, facilities;
  try {
    [customers, passTypes, facilities] = await Promise.all([
      api.customers(), api.passTypes(), api.facilities()]);
  } catch (err) { toast('Could not open the form', err.message, 'error'); return; }

  const today = new Date();
  const local = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000)
                        .toISOString().slice(0, 10);

  modal({
    title: 'Sell a pass',
    width: '600px',
    body: `
      <form id="pass-form" novalidate>
        <div class="field">
          <label for="p-customer">Customer</label>
          <select class="select" id="p-customer" required>
            <option value="">Choose a customer…</option>
            ${customers.map((c) => `<option value="${c.customer_id}">${esc(c.full_name)} — ${
              esc(c.phone)}</option>`).join('')}
          </select><div class="field-error"></div>
        </div>
        <div class="field">
          <label for="p-vehicle">Vehicle</label>
          <select class="select" id="p-vehicle" required disabled>
            <option value="">Choose a customer first</option></select>
          <div class="field-error"></div>
        </div>
        <div class="field">
          <label for="p-type">Pass product</label>
          <select class="select" id="p-type" required disabled>
            <option value="">Choose a vehicle first</option></select>
          <div class="help">Only products matching that vehicle type are listed.
            Price and duration come from the product, not from this form.</div>
          <div class="field-error"></div>
        </div>
        <div class="form-row">
          <div class="field">
            <label for="p-facility">Facility</label>
            <select class="select" id="p-facility" required>
              ${facilities.map((f) => `<option value="${f.facility_id}">${
                esc(f.name)}</option>`).join('')}
            </select><div class="field-error"></div>
          </div>
          <div class="field">
            <label for="p-from">Valid from</label>
            <input class="input" type="date" id="p-from" value="${local(today)}" required>
            <div class="field-error"></div>
          </div>
        </div>
        <div id="p-summary"></div>
      </form>`,
    actions: [
      { label: 'Cancel', onClick: (c) => c() },
      { label: 'Sell pass', variant: 'primary', onClick: submit },
    ],
    onMount(scrim) {
      const cSel = scrim.querySelector('#p-customer');
      const vSel = scrim.querySelector('#p-vehicle');
      const tSel = scrim.querySelector('#p-type');
      const summary = scrim.querySelector('#p-summary');

      cSel.addEventListener('change', async () => {
        vSel.disabled = true; tSel.disabled = true; summary.innerHTML = '';
        tSel.innerHTML = '<option value="">Choose a vehicle first</option>';
        if (!cSel.value) { vSel.innerHTML = '<option value="">Choose a customer first</option>'; return; }
        vSel.innerHTML = '<option value="">Loading…</option>';
        try {
          const vs = await api.vehicles({ customer_id: cSel.value });
          if (!vs.length) {
            vSel.innerHTML = '<option value="">No vehicles on file for this customer</option>';
            return;
          }
          vSel.innerHTML = '<option value="">Choose a vehicle…</option>' + vs.map((v) =>
            `<option value="${v.vehicle_id}" data-type="${v.vehicle_type_id}">${
              esc(v.plate_number)} — ${esc(v.vehicle_type_name)}</option>`).join('');
          vSel.disabled = false;
        } catch (err) { vSel.innerHTML = `<option value="">${esc(err.message)}</option>`; }
      });

      vSel.addEventListener('change', () => {
        summary.innerHTML = '';
        const typeId = vSel.selectedOptions[0]?.dataset.type;
        const opts = passTypes.filter((p) => String(p.vehicle_type_id) === String(typeId));
        if (!opts.length) {
          tSel.innerHTML = '<option value="">No products for this vehicle type</option>';
          tSel.disabled = true; return;
        }
        tSel.innerHTML = '<option value="">Choose a product…</option>' + opts.map((p) =>
          `<option value="${p.pass_type_id}" data-days="${p.duration_days}" data-price="${p.price}">${
            esc(p.name)} — ${money(p.price)}</option>`).join('');
        tSel.disabled = false;
      });

      const refreshSummary = () => {
        const o = tSel.selectedOptions[0];
        if (!o?.value) { summary.innerHTML = ''; return; }
        const from = new Date(scrim.querySelector('#p-from').value);
        const to = new Date(from.getTime() + Number(o.dataset.days) * 86400000);
        summary.innerHTML = `<div class="card" style="background:var(--surface-2)">
          <dl class="dl">
            <dt>Runs for</dt><dd class="mono">${o.dataset.days} days</dd>
            <dt>Expires</dt><dd class="mono">${esc(dateOnly(to.toISOString()))}</dd>
            <dt style="font-weight:600;color:var(--ink)">Price</dt>
            <dd class="money" style="font-weight:600">${esc(money(o.dataset.price))}</dd>
          </dl></div>`;
      };
      tSel.addEventListener('change', refreshSummary);
      scrim.querySelector('#p-from').addEventListener('change', refreshSummary);
    },
  });

  async function submit(close, scrim) {
    const form = scrim.querySelector('#pass-form');
    clearErrors(form);
    const c = scrim.querySelector('#p-customer'), v = scrim.querySelector('#p-vehicle');
    const t = scrim.querySelector('#p-type'), f = scrim.querySelector('#p-facility');
    const d = scrim.querySelector('#p-from');

    let bad = false;
    if (!c.value) { fieldError(c, 'Choose a customer.'); bad = true; }
    if (!v.value) { fieldError(v, 'Choose a vehicle.'); bad = true; }
    if (!t.value) { fieldError(t, 'Choose a pass product.'); bad = true; }
    if (!d.value) { fieldError(d, 'Set a start date.'); bad = true; }
    if (bad) { scrim.querySelector('[aria-invalid="true"]')?.focus(); return; }

    const btn = scrim.querySelector('[data-action="1"]');
    await submitting(btn, async () => {
      try {
        await api.buyPass({
          customer_id: Number(c.value), vehicle_id: Number(v.value),
          pass_type_id: Number(t.value), facility_id: Number(f.value),
          valid_from: new Date(d.value + 'T00:00:00').toISOString(),
        });
        toast('Pass sold', 'It covers every stay inside its window.', 'success');
        close(); onDone();
      } catch (err) { fieldError(t, err.message); }
    });
  }
}
