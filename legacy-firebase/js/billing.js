import { db } from './firebase-config.js';
import { collection, addDoc, getDocs, doc, updateDoc, query, onSnapshot, serverTimestamp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";
import { initPage, showToast, animateCounter, checkAuth } from './utils.js';

document.addEventListener('DOMContentLoaded', async () => {
  initPage('billing');
  if(!await checkAuth()) return;

  const billsTableBody = document.getElementById('billsTableBody');
  const tariffTableBody = document.getElementById('tariffTableBody');
  const tariffEditFields = document.getElementById('tariffEditFields');
  
  let allBills = [];
  let currentTariffs = {};

  // Load Tariffs
  const tariffRef = collection(db, 'tariffs');
  onSnapshot(tariffRef, (snap) => {
    tariffTableBody.innerHTML = '';
    tariffEditFields.innerHTML = '';
    
    snap.forEach(docSnap => {
      const data = docSnap.data();
      const type = docSnap.id;
      currentTariffs[type] = data;
      
      tariffTableBody.innerHTML += `
        <tr>
          <td>${type}</td>
          <td>₹${data.ratePerHour}</td>
          <td>₹${data.ratePerDay}</td>
          <td>₹${data.maxDaily}</td>
        </tr>
      `;

      tariffEditFields.innerHTML += `
        <div class="card mb-3 p-3">
          <h4>${type}</h4>
          <div class="form-row">
            <div class="form-group">
              <label>Rate / Hour</label>
              <input type="number" class="form-control t-hour" data-type="${type}" value="${data.ratePerHour}">
            </div>
            <div class="form-group">
              <label>Rate / Day</label>
              <input type="number" class="form-control t-day" data-type="${type}" value="${data.ratePerDay}">
            </div>
            <div class="form-group">
              <label>Max Daily Rate</label>
              <input type="number" class="form-control t-max" data-type="${type}" value="${data.maxDaily}">
            </div>
          </div>
        </div>
      `;
    });
  });

  // Tariff Modal
  const tariffModal = document.getElementById('tariffModal');
  document.getElementById('btnEditTariffs').addEventListener('click', () => tariffModal.style.display = 'flex');
  document.querySelectorAll('.close-modal, #btnCancelTariff').forEach(btn => {
    if(btn.id !== 'closeInvoiceModal') btn.addEventListener('click', () => tariffModal.style.display = 'none');
  });

  document.getElementById('tariffForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const types = Object.keys(currentTariffs);
      for(let type of types) {
        const hour = document.querySelector(`.t-hour[data-type="${type}"]`).value;
        const day = document.querySelector(`.t-day[data-type="${type}"]`).value;
        const max = document.querySelector(`.t-max[data-type="${type}"]`).value;
        
        await updateDoc(doc(db, 'tariffs', type), {
          ratePerHour: Number(hour),
          ratePerDay: Number(day),
          maxDaily: Number(max)
        });
      }
      showToast('Tariffs updated successfully', 'success');
      tariffModal.style.display = 'none';
    } catch(err) {
      showToast('Error updating tariffs', 'error');
    }
  });


  // Load Bills
  const billsRef = collection(db, 'bills');
  onSnapshot(billsRef, (snap) => {
    allBills = [];
    let stats = { today: 0, week: 0, month: 0, pending: 0 };
    const now = new Date();

    snap.forEach(docSnap => {
      const data = docSnap.data();
      const dateObj = data.date ? data.date.toDate() : new Date();
      allBills.push({ id: docSnap.id, ...data, dateObj });

      if (data.status === 'Pending') {
        stats.pending += data.total;
      } else if (data.status === 'Paid') {
        // Simple mock stats check
        stats.month += data.total;
        stats.week += data.total;
        stats.today += data.total;
      }
    });
    
    // Sort desc
    allBills.sort((a,b) => b.dateObj - a.dateObj);

    animateCounter('statRevToday', stats.today);
    animateCounter('statRevWeek', stats.week);
    animateCounter('statRevMonth', stats.month);
    animateCounter('statPendingAmt', stats.pending);

    renderBills();
  });

  function renderBills() {
    const statusFilter = document.getElementById('billStatusFilter').value;
    
    let filtered = allBills;
    if(statusFilter !== 'all') {
      filtered = filtered.filter(b => b.status === statusFilter);
    }

    billsTableBody.innerHTML = '';
    filtered.slice(0, 20).forEach(bill => { // mock pagination
      billsTableBody.innerHTML += `
        <tr>
          <td>${bill.id.substring(0,6)}</td>
          <td>${bill.dateObj.toLocaleDateString()}</td>
          <td>${bill.vehiclePlate}</td>
          <td>${bill.durationHours || 0}h</td>
          <td>₹${bill.baseAmount || 0}</td>
          <td>₹${bill.tax || 0}</td>
          <td><strong>₹${bill.total || 0}</strong></td>
          <td><span class="badge" style="background:${bill.status==='Paid'?'var(--success)':'var(--warning)'}">${bill.status}</span></td>
          <td>
            <button class="btn btn-sm btn-outline btn-invoice" data-id="${bill.id}">Invoice</button>
            ${bill.status === 'Pending' ? `<button class="btn btn-sm btn-primary btn-pay" data-id="${bill.id}">Pay</button>` : ''}
          </td>
        </tr>
      `;
    });

    document.querySelectorAll('.btn-pay').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const id = e.target.dataset.id;
        try {
          await updateDoc(doc(db, 'bills', id), { status: 'Paid', paidAt: serverTimestamp() });
          showToast('Payment recorded', 'success');
        } catch(err) {
          showToast('Payment failed', 'error');
        }
      });
    });

    document.querySelectorAll('.btn-invoice').forEach(btn => {
      btn.addEventListener('click', (e) => {
        showInvoice(e.target.dataset.id);
      });
    });
  }

  document.getElementById('billStatusFilter').addEventListener('change', renderBills);

  // Invoice Logic
  const invoiceModal = document.getElementById('invoiceModal');
  const invoiceContent = document.getElementById('invoiceContent');
  
  document.getElementById('closeInvoiceModal').addEventListener('click', () => invoiceModal.style.display = 'none');
  
  document.getElementById('btnPrintInvoice').addEventListener('click', () => {
    window.print();
  });

  function showInvoice(id) {
    const bill = allBills.find(b => b.id === id);
    if(!bill) return;

    invoiceContent.innerHTML = `
      <div style="text-align: center; margin-bottom: 2rem;">
        <h2>SmartPark</h2>
        <p>123 Parking Ave, Tech City</p>
      </div>
      <div class="flex-between mb-4">
        <div>
          <p><strong>Bill To:</strong> ${bill.customerName || 'Walk-in'}</p>
          <p><strong>Vehicle:</strong> ${bill.vehiclePlate}</p>
        </div>
        <div style="text-align: right;">
          <p><strong>Invoice #:</strong> ${bill.id}</p>
          <p><strong>Date:</strong> ${bill.dateObj.toLocaleString()}</p>
          <p><strong>Status:</strong> ${bill.status}</p>
        </div>
      </div>
      <table class="table" style="width:100%; border-collapse: collapse; margin-bottom: 2rem;">
        <tr style="border-bottom: 1px solid #ccc;">
          <th style="text-align: left; padding: 8px;">Description</th>
          <th style="text-align: right; padding: 8px;">Amount</th>
        </tr>
        <tr>
          <td style="padding: 8px;">Parking Fee (${bill.durationHours || 0} hours)</td>
          <td style="text-align: right; padding: 8px;">₹${bill.baseAmount || 0}</td>
        </tr>
        <tr>
          <td style="padding: 8px;">Tax (18%)</td>
          <td style="text-align: right; padding: 8px;">₹${bill.tax || 0}</td>
        </tr>
        <tr style="border-top: 2px solid #333;">
          <td style="padding: 8px;"><strong>Total</strong></td>
          <td style="text-align: right; padding: 8px;"><strong>₹${bill.total || 0}</strong></td>
        </tr>
      </table>
      <div style="text-align: center; color: #666;">
        <p>Thank you for parking with us!</p>
      </div>
    `;
    
    invoiceModal.style.display = 'flex';
  }

});
