/* reservations.js — bookings, with the expiry sweep run server-side on read. */
import { api } from './api.js';
import {
  mountShell, icon, esc, dateTime, titleCase, skeleton, emptyRow, errorState,
  facility, modal, toast, fieldError, clearErrors, submitting, confirmDialog,
} from './ui.js';
import { enter, revealList, bindInteractive } from './motion.js';

const ctx = mountShell('reservations.html', {
  title: 'Reservations',
  subtitle: 'Slot holds and their status',
});
if (ctx) init(ctx);

async function init({ content, user }) {
  content.innerHTML = `
    <div class="toolbar">
      <label class="sr-only" for="status">Status</label>
      <select class="select" id="status" style="max-width:200px">
        <option value="all">All statuses</option>
        <option value="held">Held</option>
        <option value="confirmed">Confirmed</option>
        <option value="fulfilled">Fulfilled</option>
        <option value="expired">Expired</option>
        <option value="cancelled">Cancelled</option>
      </select>
      <div class="spacer"></div>
      <button class="btn btn-primary" id="new" data-interactive>${icon('plus')} New reservation</button>
    </div>
    <p class="section-note">
      A hold blocks its bay for the whole booked window. Two live holds cannot
      overlap on one bay — the database refuses the second, so a double booking
      is impossible rather than merely unlikely. Lapsed holds are expired
      automatically whenever this page loads.
    </p>
    <section class="card">
      <div class="table-wrap">
        <table><caption class="sr-only">Reservations</caption>
          <thead><tr>
            <th scope="col">Customer</th><th scope="col">Vehicle</th><th scope="col">Bay</th>
            <th scope="col">From</th><th scope="col">Until</th>
            <th scope="col">Status</th><th scope="col"></th>
          </tr></thead><tbody id="rows"></tbody></table>
      </div>
    </section>`;

  const sel = content.querySelector('#status');
  sel.addEventListener('change', load);
  content.querySelector('#new').addEventListener('click', () => newReservation(load));
  enter(content.querySelector('.card'));
  load();

  async function load() {
    const tbody = content.querySelector('#rows');
    tbody.innerHTML = `<tr><td colspan="7" style="padding:var(--s4);border:0">
      <div class="skeleton skeleton-row"></div><div class="skeleton skeleton-row"></div>
      <div class="skeleton skeleton-row"></div></td></tr>`;
    let rows;
    try { rows = await api.reservations(sel.value); }
    catch (err) {
      tbody.innerHTML = '<tr><td colspan="7" style="padding:0;border:0"></td></tr>';
      errorState(tbody.querySelector('td'), err, load); return;
    }
    if (!rows.length) {
      emptyRow(tbody, 7,
        sel.value === 'all' ? 'No reservations yet' : `No ${sel.value} reservations`,
        sel.value === 'all'
          ? 'Create one with New reservation to hold a bay for an arrival.'
          : 'Try a different status filter.');
      return;
    }
    tbody.innerHTML = rows.map((r) => {
      const live = r.status === 'held' || r.status === 'confirmed';
      return `<tr>
        <td>${esc(r.customer_name)}<div style="color:var(--ink-2);font-size:var(--t-xs)"
              class="mono">${esc(r.phone)}</div></td>
        <td class="plate">${esc(r.plate_number)}</td>
        <td class="mono">${esc(r.slot_code)}<div style="color:var(--ink-2);
              font-size:var(--t-xs)">${esc(r.floor_name)}</div></td>
        <td class="mono">${esc(dateTime(r.reserved_from))}</td>
        <td class="mono">${esc(dateTime(r.reserved_until))}</td>
        <td><span class="badge badge-${esc(r.status)}">${esc(titleCase(r.status))}</span></td>
        <td style="text-align:right;white-space:nowrap">
          ${r.status === 'held' ? `<button class="btn btn-sm" data-confirm="${r.reservation_id}"
              data-interactive>Confirm</button>` : ''}
          ${live ? `<button class="btn btn-sm btn-danger" data-cancel="${r.reservation_id}"
              data-interactive>Cancel</button>` : ''}
        </td></tr>`;
    }).join('');
    revealList(tbody.querySelectorAll('tr'), { step: 0.018 });
    bindInteractive(tbody);

    tbody.querySelectorAll('[data-confirm]').forEach((b) => b.addEventListener('click', async () => {
      await submitting(b, async () => {
        try {
          await api.setReservation(b.dataset.confirm, 'confirmed');
          toast('Reservation confirmed', 'The bay stays held for this booking.', 'success');
          load();
        } catch (err) { toast('Could not confirm', err.message, 'error'); }
      });
    }));
    tbody.querySelectorAll('[data-cancel]').forEach((b) => b.addEventListener('click', async () => {
      if (!await confirmDialog('Cancel this reservation?',
        'The bay is released immediately and becomes available to other drivers.',
        'Cancel reservation')) return;
      try {
        await api.setReservation(b.dataset.cancel, 'cancelled');
        toast('Reservation cancelled', 'The bay is free again.', 'success');
        load();
      } catch (err) { toast('Could not cancel', err.message, 'error'); }
    }));
  }
}

async function newReservation(onDone) {
  let customers = [], vtypes = [], facilities = [];
  try {
    [customers, vtypes, facilities] = await Promise.all([
      api.customers(), api.vehicleTypes(), api.facilities()]);
  } catch (err) { toast('Could not open the form', err.message, 'error'); return; }

  const start = new Date(Date.now() + 30 * 60000);
  const end   = new Date(Date.now() + 150 * 60000);
  const local = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000)
                        .toISOString().slice(0, 16);

  modal({
    title: 'New reservation',
    width: '620px',
    body: `
      <form id="res-form" novalidate>
        <div class="field">
          <label for="r-customer">Customer</label>
          <select class="select" id="r-customer" required>
            <option value="">Choose a customer…</option>
            ${customers.map((c) => `<option value="${c.customer_id}">${esc(c.full_name)} — ${
              esc(c.phone)}</option>`).join('')}
          </select>
          <div class="field-error"></div>
        </div>
        <div class="field">
          <label for="r-vehicle">Vehicle</label>
          <select class="select" id="r-vehicle" required disabled>
            <option value="">Choose a customer first</option></select>
          <div class="field-error"></div>
        </div>
        <div class="form-row">
          <div class="field">
            <label for="r-from">From</label>
            <input class="input" type="datetime-local" id="r-from" value="${local(start)}" required>
            <div class="field-error"></div>
          </div>
          <div class="field">
            <label for="r-until">Until</label>
            <input class="input" type="datetime-local" id="r-until" value="${local(end)}" required>
            <div class="field-error"></div>
          </div>
        </div>
        <div class="field">
          <label for="r-slot">Bay</label>
          <select class="select" id="r-slot" required disabled>
            <option value="">Choose a vehicle first</option></select>
          <div class="help">Only bays built for that vehicle type and free now are listed.</div>
          <div class="field-error"></div>
        </div>
      </form>`,
    actions: [
      { label: 'Cancel', onClick: (c) => c() },
      { label: 'Create reservation', variant: 'primary', onClick: submit },
    ],
    onMount(scrim) {
      const cSel = scrim.querySelector('#r-customer');
      const vSel = scrim.querySelector('#r-vehicle');
      const sSel = scrim.querySelector('#r-slot');

      cSel.addEventListener('change', async () => {
        vSel.disabled = true; vSel.innerHTML = '<option value="">Loading…</option>';
        sSel.disabled = true; sSel.innerHTML = '<option value="">Choose a vehicle first</option>';
        if (!cSel.value) { vSel.innerHTML = '<option value="">Choose a customer first</option>'; return; }
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
        } catch (err) {
          vSel.innerHTML = `<option value="">${esc(err.message)}</option>`;
        }
      });

      vSel.addEventListener('change', async () => {
        sSel.disabled = true; sSel.innerHTML = '<option value="">Loading bays…</option>';
        const typeId = vSel.selectedOptions[0]?.dataset.type;
        if (!typeId) return;
        try {
          const all = (await Promise.all(facilities.map((f) =>
            api.freeSlots(f.facility_id, { vehicle_type_id: typeId })))).flat();
          if (!all.length) {
            sSel.innerHTML = '<option value="">No free bays for this vehicle type</option>';
            return;
          }
          sSel.innerHTML = '<option value="">Choose a bay…</option>' + all.map((s) =>
            `<option value="${s.slot_id}">${esc(s.slot_code)} — ${esc(s.floor_name)}, Zone ${
              esc(s.zone_code)}</option>`).join('');
          sSel.disabled = false;
        } catch (err) {
          sSel.innerHTML = `<option value="">${esc(err.message)}</option>`;
        }
      });
    },
  });

  async function submit(close, scrim) {
    const form = scrim.querySelector('#res-form');
    clearErrors(form);
    const c = scrim.querySelector('#r-customer'), v = scrim.querySelector('#r-vehicle');
    const f = scrim.querySelector('#r-from'), u = scrim.querySelector('#r-until');
    const s = scrim.querySelector('#r-slot');

    let bad = false;
    if (!c.value) { fieldError(c, 'Choose a customer.'); bad = true; }
    if (!v.value) { fieldError(v, 'Choose a vehicle.'); bad = true; }
    if (!s.value) { fieldError(s, 'Choose a bay.'); bad = true; }
    if (!f.value) { fieldError(f, 'Set a start time.'); bad = true; }
    if (!u.value) { fieldError(u, 'Set an end time.'); bad = true; }
    if (f.value && u.value && new Date(u.value) <= new Date(f.value)) {
      fieldError(u, 'The end time must be after the start time.'); bad = true;
    }
    if (bad) { scrim.querySelector('[aria-invalid="true"]')?.focus(); return; }

    const btn = scrim.querySelector('[data-action="1"]');
    await submitting(btn, async () => {
      try {
        await api.createReservation({
          customer_id: Number(c.value), vehicle_id: Number(v.value),
          slot_id: Number(s.value),
          reserved_from: new Date(f.value).toISOString(),
          reserved_until: new Date(u.value).toISOString(),
        });
        toast('Reservation created', 'The bay is held for that window.', 'success');
        close(); onDone();
      } catch (err) {
        fieldError(s, err.message);
      }
    });
  }
}
