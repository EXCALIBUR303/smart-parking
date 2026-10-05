/* billing.js — bills and recorded payments.
   Payments are RECORDED, not processed. No gateway, and no field anywhere in
   this file collects a card number, CVV or UPI credential. */
import { api, auth } from './api.js';
import {
  mountShell, icon, esc, money, moneyShort, duration, dateTime, titleCase,
  emptyRow, errorState, modal, toast, fieldError, clearErrors, submitting,
} from './ui.js';
import { enter, revealList, countTo, bindInteractive } from './motion.js';

const ctx = mountShell('billing.html', {
  title: 'Billing',
  subtitle: 'Bills raised and money collected',
});
if (ctx) init(ctx);

async function init({ content }) {
  content.innerHTML = `
    <div class="toolbar">
      <label class="sr-only" for="status">Bill status</label>
      <select class="select" id="status" style="max-width:200px">
        <option value="all">All bills</option>
        <option value="unpaid">Unpaid</option>
        <option value="partly_paid">Partly paid</option>
        <option value="paid">Paid</option>
        <option value="waived">Waived</option>
      </select>
      <div class="search">
        ${icon('search')}
        <label class="sr-only" for="q">Search by registration</label>
        <input class="input plate" id="q" placeholder="Filter by registration" autocomplete="off">
      </div>
    </div>
    <div id="stats" class="stat-row"></div>
    <p class="section-note">
      Every amount below was computed by the database from the tariff in force
      when the vehicle arrived. Payments are recorded against a bill; the bill's
      status is derived from the payments, never set by hand.
    </p>
    <section class="card">
      <div class="table-wrap">
        <table><caption class="sr-only">Bills</caption>
          <thead><tr>
            <th scope="col">Bill</th><th scope="col">Vehicle</th><th scope="col">Bay</th>
            <th scope="col">Raised</th><th scope="col">Duration</th>
            <th scope="col" class="num">Total</th><th scope="col" class="num">Due</th>
            <th scope="col">Status</th><th scope="col"></th>
          </tr></thead><tbody id="rows"></tbody></table>
      </div>
    </section>`;

  const sel = content.querySelector('#status');
  const q = content.querySelector('#q');
  let data = { bills: [], summary: {} };

  sel.addEventListener('change', load);
  let t; q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(render, 200); });
  enter(content.querySelector('.card'));
  load();

  // Deep link from the gate: billing.html?bill=123 opens that bill directly.
  const wanted = new URLSearchParams(location.search).get('bill');

  async function load() {
    const tbody = content.querySelector('#rows');
    tbody.innerHTML = `<tr><td colspan="9" style="padding:var(--s4);border:0">
      <div class="skeleton skeleton-row"></div><div class="skeleton skeleton-row"></div>
      <div class="skeleton skeleton-row"></div></td></tr>`;
    try { data = await api.bills(sel.value); }
    catch (err) {
      tbody.innerHTML = '<tr><td colspan="9" style="padding:0;border:0"></td></tr>';
      errorState(tbody.querySelector('td'), err, load); return;
    }
    renderStats(); render();
    if (wanted) { openBill(Number(wanted)); history.replaceState({}, '', 'billing.html'); }
  }

  function renderStats() {
    const s = data.summary || {};
    const amt = (k) => Number(s[k]?.amount || 0);
    const cnt = (k) => Number(s[k]?.count || 0);
    const outstanding = amt('unpaid') + amt('partly_paid');
    const host = content.querySelector('#stats');
    host.innerHTML = `
      <div class="stat stat-accent"><div class="stat-label">${icon('check')} Settled</div>
        <div class="stat-value" data-count="${amt('paid')}" data-money="1">₹0</div>
        <div class="stat-foot">${cnt('paid')} bills paid in full</div></div>
      <div class="stat"><div class="stat-label">${icon('alert')} Outstanding</div>
        <div class="stat-value" data-count="${outstanding}" data-money="1">₹0</div>
        <div class="stat-foot">${cnt('unpaid')} unpaid · ${cnt('partly_paid')} part-paid</div></div>
      <div class="stat"><div class="stat-label">${icon('receipt')} Bills raised</div>
        <div class="stat-value" data-count="${cnt('paid') + cnt('unpaid') + cnt('partly_paid') + cnt('waived')}">0</div>
        <div class="stat-foot">all time</div></div>`;
    revealList(host.querySelectorAll('.stat'));
    host.querySelectorAll('[data-count]').forEach((el) => countTo(el, Number(el.dataset.count),
      { format: el.dataset.money ? moneyShort : (v) => Math.round(v).toLocaleString('en-IN') }));
  }

  function render() {
    const tbody = content.querySelector('#rows');
    const term = q.value.trim().toUpperCase();
    const rows = term
      ? data.bills.filter((b) => (b.plate_number || '').includes(term))
      : data.bills;

    if (!rows.length) {
      emptyRow(tbody, 9,
        term ? `No bills for “${term}”`
             : sel.value === 'all' ? 'No bills yet' : `No ${titleCase(sel.value).toLowerCase()} bills`,
        term ? 'Check the registration, or clear the filter.'
             : 'A bill is raised automatically when a vehicle exits the gate.');
      return;
    }
    tbody.innerHTML = rows.map((b) => `<tr>
      <td class="mono">#${b.bill_id}</td>
      <td class="plate">${esc(b.plate_number)}<div style="color:var(--ink-2);
        font-size:var(--t-xs)">${esc(b.customer_name)}</div></td>
      <td class="mono">${esc(b.slot_code)}</td>
      <td class="mono" style="white-space:nowrap">${esc(dateTime(b.generated_at))}</td>
      <td class="mono">${esc(duration(b.billable_minutes))}</td>
      <td class="num money">${esc(money(b.total_amount))}</td>
      <td class="num money" style="${Number(b.amount_due) > 0 ? 'color:var(--alert-ink)' : ''}">${
        esc(money(b.amount_due))}</td>
      <td><span class="badge badge-${esc(b.status)}">${esc(titleCase(b.status))}</span></td>
      <td style="text-align:right;white-space:nowrap">
        <button class="btn btn-sm" data-view="${b.bill_id}" data-interactive>Invoice</button>
        ${Number(b.amount_due) > 0 && auth.isStaff
          ? `<button class="btn btn-sm btn-primary" data-pay="${b.bill_id}"
               data-due="${b.amount_due}" data-interactive>Record payment</button>` : ''}
      </td></tr>`).join('');
    revealList(tbody.querySelectorAll('tr'), { step: 0.015 });
    bindInteractive(tbody);
    tbody.querySelectorAll('[data-view]').forEach((b) =>
      b.addEventListener('click', () => openBill(Number(b.dataset.view))));
    tbody.querySelectorAll('[data-pay]').forEach((b) =>
      b.addEventListener('click', () => recordPayment(Number(b.dataset.pay),
                                                      Number(b.dataset.due), load)));
  }

  async function openBill(id) {
    let b;
    try { b = await api.bill(id); }
    catch (err) { toast('Could not open that bill', err.message, 'error'); return; }

    const paid = (b.payments || []).reduce((a, p) => a + Number(p.amount), 0);
    const due = Number(b.total_amount) - paid;

    modal({
      title: `Invoice #${b.bill_id}`,
      width: '600px',
      body: `
        <div style="border:1px solid var(--rule);border-radius:var(--r);
                    padding:var(--s5);background:var(--surface)">
          <div style="display:flex;justify-content:space-between;gap:var(--s4);
                      align-items:flex-start;margin-bottom:var(--s5)">
            <div>
              <div style="font-family:var(--font-display);font-size:var(--t-md);
                          font-weight:600">${esc(b.facility_name)}</div>
              <div style="color:var(--ink-2);font-size:var(--t-xs)">${
                esc(b.address_line)}, ${esc(b.city)}</div>
            </div>
            <span class="badge badge-${esc(b.status)}">${esc(titleCase(b.status))}</span>
          </div>
          <dl class="dl">
            <dt>Customer</dt><dd>${esc(b.customer_name)}</dd>
            <dt>Vehicle</dt><dd class="plate">${esc(b.plate_number)} · ${esc(b.vehicle_type_name)}</dd>
            <dt>Ticket</dt><dd class="mono">${esc(b.ticket_no)}</dd>
            <dt>Bay</dt><dd class="mono">${esc(b.slot_code)}</dd>
            <dt>Entered</dt><dd class="mono">${esc(dateTime(b.entry_time))}</dd>
            <dt>Exited</dt><dd class="mono">${esc(dateTime(b.exit_time))}</dd>
            <dt>Duration</dt><dd class="mono">${esc(duration(b.billable_minutes))}</dd>
          </dl>
          <hr style="border:0;border-top:1px solid var(--rule);margin:var(--s4) 0">
          <div style="font-size:var(--t-xs);color:var(--ink-2);
                      margin-bottom:var(--s3)">
            Tariff: ${esc(b.tariff_name)} — ${money(b.first_hour_rate)} first hour,
            ${money(b.subsequent_hour_rate)} thereafter, capped at ${money(b.daily_cap)} a day,
            first ${b.free_minutes} minutes free.
          </div>
          <dl class="dl">
            <dt>Parking charge</dt><dd class="money">${esc(money(b.base_amount))}</dd>
            <dt>Tax at ${esc(b.tax_rate_pct)}%</dt><dd class="money">${esc(money(b.tax_amount))}</dd>
            <dt style="font-weight:600;color:var(--ink)">Total</dt>
            <dd class="money" style="font-weight:600;font-size:var(--t-md)">${
              esc(money(b.total_amount))}</dd>
          </dl>
          ${(b.payments || []).length ? `
            <hr style="border:0;border-top:1px solid var(--rule);margin:var(--s4) 0">
            <div style="font-size:var(--t-sm);font-weight:500;margin-bottom:var(--s2)">
              Payments recorded</div>
            <dl class="dl">${b.payments.map((p) => `
              <dt>${esc(dateTime(p.paid_at))} · ${esc(titleCase(p.method))}${
                p.reference_no ? ` · <span class="mono">${esc(p.reference_no)}</span>` : ''}</dt>
              <dd class="money">${esc(money(p.amount))}</dd>`).join('')}
              ${due > 0.005 ? `<dt style="font-weight:600;color:var(--alert-ink)">Still due</dt>
                <dd class="money" style="font-weight:600;color:var(--alert-ink)">${
                  esc(money(due))}</dd>` : ''}
            </dl>` : `
            <p style="font-size:var(--t-sm);color:var(--ink-2);margin-top:var(--s4)">
              No payment recorded against this bill yet.</p>`}
        </div>`,
      actions: [
        { label: 'Close', onClick: (c) => c() },
        { label: 'Print', onClick: () => window.print() },
      ],
    });
  }
}

function recordPayment(billId, due, onDone) {
  modal({
    title: `Record payment for bill #${billId}`,
    body: `
      <p style="color:var(--ink-2);font-size:var(--t-sm);margin-bottom:var(--s4)">
        This records a receipt that has already been taken. No card, CVV or UPI
        credential is collected or stored anywhere in this system.
      </p>
      <form id="pay-form" novalidate>
        <div class="form-row">
          <div class="field">
            <label for="pay-amount">Amount received</label>
            <input class="input mono" type="number" id="pay-amount" step="0.01" min="0.01"
                   max="${due}" value="${Number(due).toFixed(2)}" required>
            <div class="help">Outstanding on this bill: ${money(due)}</div>
            <div class="field-error"></div>
          </div>
          <div class="field">
            <label for="pay-method">Method</label>
            <select class="select" id="pay-method" required>
              <option value="cash">Cash</option><option value="card">Card</option>
              <option value="upi">UPI</option><option value="netbanking">Net banking</option>
              <option value="wallet">Wallet</option>
            </select><div class="field-error"></div>
          </div>
        </div>
        <div class="field">
          <label for="pay-ref">Receipt or transaction reference <span
            style="color:var(--ink-2);font-weight:400">(optional)</span></label>
          <input class="input mono" id="pay-ref" autocomplete="off"
                 placeholder="e.g. the reference printed on the terminal slip">
          <div class="field-error"></div>
        </div>
      </form>`,
    actions: [
      { label: 'Cancel', onClick: (c) => c() },
      { label: 'Record payment', variant: 'primary', onClick: submit },
    ],
  });

  async function submit(close, scrim) {
    const form = scrim.querySelector('#pay-form');
    clearErrors(form);
    const amt = scrim.querySelector('#pay-amount');
    const val = Number(amt.value);
    if (!amt.value || Number.isNaN(val) || val <= 0) {
      fieldError(amt, 'Enter an amount greater than zero.'); amt.focus(); return;
    }
    if (val > due + 0.005) {
      fieldError(amt, `That is more than the ${money(due)} outstanding.`); amt.focus(); return;
    }
    const btn = scrim.querySelector('[data-action="1"]');
    await submitting(btn, async () => {
      try {
        const r = await api.pay({
          bill_id: billId, amount: val,
          method: scrim.querySelector('#pay-method').value,
          reference_no: scrim.querySelector('#pay-ref').value.trim() || null,
        });
        toast('Payment recorded',
              `Bill #${billId} is now ${titleCase(r.status).toLowerCase()}.`, 'success');
        close(); onDone();
      } catch (err) { fieldError(amt, err.message); }
    });
  }
}
