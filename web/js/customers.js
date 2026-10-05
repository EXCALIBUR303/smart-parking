/* customers.js — customer and vehicle CRUD. */
import { api, auth } from './api.js';
import {
  mountShell, icon, esc, dateOnly, emptyRow, errorState, modal, toast,
  fieldError, clearErrors, submitting, confirmDialog,
} from './ui.js';
import { enter, revealList, bindInteractive } from './motion.js';

const ctx = mountShell('customers.html', {
  title: 'Customers',
  subtitle: 'People and the vehicles they park',
});
if (ctx) init(ctx);

async function init({ content }) {
  content.innerHTML = `
    <div class="toolbar">
      <div class="search">
        ${icon('search')}
        <label class="sr-only" for="q">Search customers</label>
        <input class="input" id="q" placeholder="Search by name or phone" autocomplete="off">
      </div>
      <div class="spacer"></div>
      ${auth.isStaff ? `<button class="btn btn-primary" id="new-customer" data-interactive>
        ${icon('plus')} Add customer</button>` : ''}
    </div>
    <section class="card">
      <div class="table-wrap">
        <table><caption class="sr-only">Customers</caption>
          <thead><tr>
            <th scope="col">Name</th><th scope="col">Phone</th><th scope="col">Email</th>
            <th scope="col" class="num">Vehicles</th><th scope="col">Since</th>
            <th scope="col"></th>
          </tr></thead><tbody id="rows"></tbody></table>
      </div>
    </section>`;

  const q = content.querySelector('#q');
  let t; q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(load, 250); });
  content.querySelector('#new-customer')?.addEventListener('click', () => newCustomer(load));
  enter(content.querySelector('.card'));
  load();

  async function load() {
    const tbody = content.querySelector('#rows');
    tbody.innerHTML = `<tr><td colspan="6" style="padding:var(--s4);border:0">
      <div class="skeleton skeleton-row"></div><div class="skeleton skeleton-row"></div></td></tr>`;
    let rows;
    try { rows = await api.customers(q.value.trim()); }
    catch (err) {
      tbody.innerHTML = '<tr><td colspan="6" style="padding:0;border:0"></td></tr>';
      errorState(tbody.querySelector('td'), err, load); return;
    }
    if (!rows.length) {
      emptyRow(tbody, 6,
        q.value.trim() ? `Nobody matches “${q.value.trim()}”` : 'No customers on file',
        q.value.trim() ? 'Try part of a name or phone number.'
                       : 'Add the first customer to start recording vehicles.');
      return;
    }
    tbody.innerHTML = rows.map((c) => `<tr>
      <td>${esc(c.full_name)}</td>
      <td class="mono">${esc(c.phone)}</td>
      <td>${esc(c.email || '—')}</td>
      <td class="num mono">${c.vehicle_count}</td>
      <td class="mono">${esc(dateOnly(c.created_at))}</td>
      <td style="text-align:right;white-space:nowrap">
        <button class="btn btn-sm" data-vehicles="${c.customer_id}"
          data-name="${esc(c.full_name)}" data-interactive>Vehicles</button>
      </td></tr>`).join('');
    revealList(tbody.querySelectorAll('tr'), { step: 0.015 });
    bindInteractive(tbody);
    tbody.querySelectorAll('[data-vehicles]').forEach((b) => b.addEventListener('click',
      () => showVehicles(Number(b.dataset.vehicles), b.dataset.name, load)));
  }
}

function newCustomer(onDone) {
  modal({
    title: 'Add a customer',
    body: `
      <form id="cust-form" novalidate>
        <div class="field">
          <label for="c-name">Full name</label>
          <input class="input" id="c-name" required autocomplete="name">
          <div class="field-error"></div>
        </div>
        <div class="form-row">
          <div class="field">
            <label for="c-phone">Phone</label>
            <input class="input mono" id="c-phone" required inputmode="numeric"
                   maxlength="10" placeholder="9876543210" autocomplete="tel">
            <div class="help">Ten digits, no spaces or country code.</div>
            <div class="field-error"></div>
          </div>
          <div class="field">
            <label for="c-email">Email <span style="color:var(--ink-2);
              font-weight:400">(optional)</span></label>
            <input class="input" type="email" id="c-email" autocomplete="email">
            <div class="field-error"></div>
          </div>
        </div>
      </form>`,
    actions: [
      { label: 'Cancel', onClick: (c) => c() },
      { label: 'Add customer', variant: 'primary', onClick: submit },
    ],
    onMount(scrim) {
      const phone = scrim.querySelector('#c-phone');
      phone.addEventListener('input', () => {
        phone.value = phone.value.replace(/\D/g, '').slice(0, 10);
      });
    },
  });

  async function submit(close, scrim) {
    const form = scrim.querySelector('#cust-form');
    clearErrors(form);
    const name = scrim.querySelector('#c-name'), phone = scrim.querySelector('#c-phone');
    const email = scrim.querySelector('#c-email');
    let bad = false;
    if (!name.value.trim()) { fieldError(name, 'Enter the customer’s name.'); bad = true; }
    if (!/^[0-9]{10}$/.test(phone.value)) {
      fieldError(phone, 'Enter exactly ten digits.'); bad = true;
    }
    if (email.value.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.value.trim())) {
      fieldError(email, 'That does not look like an email address.'); bad = true;
    }
    if (bad) { scrim.querySelector('[aria-invalid="true"]')?.focus(); return; }

    const btn = scrim.querySelector('[data-action="1"]');
    await submitting(btn, async () => {
      try {
        await api.createCustomer({
          full_name: name.value.trim(), phone: phone.value,
          email: email.value.trim() || null,
        });
        toast('Customer added', 'You can now register their vehicles.', 'success');
        close(); onDone();
      } catch (err) { fieldError(phone, err.message); }
    });
  }
}

async function showVehicles(customerId, customerName, onDone) {
  let vehicles = [], types = [];
  try { [vehicles, types] = await Promise.all([
    api.vehicles({ customer_id: customerId }), api.vehicleTypes()]); }
  catch (err) { toast('Could not load vehicles', err.message, 'error'); return; }

  const list = (vs) => vs.length ? `
    <div class="table-wrap"><table>
      <thead><tr><th scope="col">Registration</th><th scope="col">Type</th>
        <th scope="col">Vehicle</th><th scope="col">State</th><th scope="col"></th></tr></thead>
      <tbody>${vs.map((v) => `<tr>
        <td class="plate">${esc(v.plate_number)}</td>
        <td>${esc(v.vehicle_type_name)}</td>
        <td>${esc([v.make, v.model, v.colour].filter(Boolean).join(' ') || '—')}</td>
        <td>${v.is_parked ? '<span class="badge badge-occupied">In lot</span>'
                          : '<span class="badge badge-neutral">Away</span>'}</td>
        <td style="text-align:right">${v.is_parked ? '' :
          `<button class="btn btn-sm btn-danger" data-del="${v.vehicle_id}"
             data-plate="${esc(v.plate_number)}">Remove</button>`}</td>
      </tr>`).join('')}</tbody></table></div>` : `
    <div class="empty" style="border:0;background:transparent">
      ${icon('car')}<div class="empty-title">No vehicles yet</div>
      <p>Add one below so this customer can park.</p></div>`;

  const m = modal({
    title: `Vehicles — ${customerName}`,
    width: '660px',
    body: `<div id="veh-list">${list(vehicles)}</div>
      ${auth.isStaff || true ? `
      <hr style="border:0;border-top:1px solid var(--rule);margin:var(--s5) 0">
      <h3 style="font-size:var(--t-md);margin-bottom:var(--s3)">Register a vehicle</h3>
      <form id="veh-form" novalidate>
        <div class="form-row">
          <div class="field">
            <label for="v-plate">Registration number</label>
            <input class="input plate" id="v-plate" required placeholder="TS09AB1234"
                   spellcheck="false" autocomplete="off">
            <div class="field-error"></div>
          </div>
          <div class="field">
            <label for="v-type">Vehicle type</label>
            <select class="select" id="v-type" required>
              ${types.map((t) => `<option value="${t.vehicle_type_id}">${
                esc(t.name)}</option>`).join('')}
            </select><div class="field-error"></div>
          </div>
        </div>
        <div class="form-row">
          <div class="field"><label for="v-make">Make</label>
            <input class="input" id="v-make" placeholder="Maruti"></div>
          <div class="field"><label for="v-model">Model</label>
            <input class="input" id="v-model" placeholder="Swift"></div>
          <div class="field"><label for="v-colour">Colour</label>
            <input class="input" id="v-colour" placeholder="White"></div>
        </div>
        <button class="btn btn-primary" type="submit" id="v-submit" data-interactive>
          ${icon('plus')} Register vehicle</button>
      </form>` : ''}`,
    actions: [{ label: 'Done', onClick: (c) => { c(); onDone(); } }],
    onMount(scrim) {
      const plate = scrim.querySelector('#v-plate');
      plate?.addEventListener('input', () => {
        plate.value = plate.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
      });
      wireDeletes(scrim);
      scrim.querySelector('#veh-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const form = e.currentTarget;
        clearErrors(form);
        const v = plate.value.trim();
        if (!/^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$/.test(v)) {
          fieldError(plate, 'Use the Indian format, for example TS09AB1234.');
          plate.focus(); return;
        }
        await submitting(scrim.querySelector('#v-submit'), async () => {
          try {
            await api.createVehicle({
              customer_id: customerId, plate_number: v,
              vehicle_type_id: Number(scrim.querySelector('#v-type').value),
              make: scrim.querySelector('#v-make').value.trim() || null,
              model: scrim.querySelector('#v-model').value.trim() || null,
              colour: scrim.querySelector('#v-colour').value.trim() || null,
            });
            toast('Vehicle registered', `${v} is on file.`, 'success');
            form.reset();
            await refresh(scrim);
          } catch (err) { fieldError(plate, err.message); }
        });
      });
    },
  });

  async function refresh(scrim) {
    const vs = await api.vehicles({ customer_id: customerId });
    scrim.querySelector('#veh-list').innerHTML = list(vs);
    wireDeletes(scrim);
  }

  function wireDeletes(scrim) {
    scrim.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', async () => {
      if (!await confirmDialog('Remove this vehicle?',
        `${b.dataset.plate} will be removed from this customer. A vehicle with parking history cannot be removed.`,
        'Remove vehicle')) return;
      try {
        await api.deleteVehicle(b.dataset.del);
        toast('Vehicle removed', '', 'success');
        await refresh(scrim);
      } catch (err) {
        // ON DELETE RESTRICT on parking_session protects vehicles with history.
        toast('Could not remove that vehicle', err.message, 'error');
      }
    }));
  }
}
