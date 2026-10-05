import { db } from './firebase-config.js';
import { collection, addDoc, doc, updateDoc, query, onSnapshot, serverTimestamp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";
import { initPage, showToast, animateCounter, checkAuth } from './utils.js';

document.addEventListener('DOMContentLoaded', async () => {
  initPage('passes');
  if(!await checkAuth()) return;

  const passesList = document.getElementById('passesList');
  const emptyState = document.getElementById('emptyState');
  
  let allPasses = [];

  const prices = {
    'Daily': 100,
    'Weekly': 500,
    'Monthly': 1500,
    'Annual': 12000
  };

  const gradients = {
    'Daily': 'linear-gradient(to right, var(--secondary-start), var(--secondary-end))',
    'Weekly': 'linear-gradient(to right, #10B981, #059669)',
    'Monthly': 'linear-gradient(to right, var(--primary-start), var(--primary-end))',
    'Annual': 'linear-gradient(to right, #F59E0B, #D97706)'
  };

  const passRef = collection(db, 'passes');
  onSnapshot(passRef, (snapshot) => {
    allPasses = [];
    let stats = { active: 0, expiring: 0, expired: 0, revenue: 0 };
    const now = new Date();
    const sevenDaysFromNow = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);

    snapshot.forEach(docSnap => {
      const data = docSnap.data();
      const id = docSnap.id;
      const validUntil = data.validUntil.toDate();
      const validFrom = data.validFrom.toDate();
      
      let status = data.status;
      if (status === 'Active' && now > validUntil) {
        status = 'Expired';
        updateDoc(doc(db, 'passes', id), { status: 'Expired' });
      }

      allPasses.push({ id, ...data, validFrom, validUntil, status });

      if (status === 'Active') {
        stats.active++;
        if (validUntil <= sevenDaysFromNow) {
          stats.expiring++;
        }
      } else if (status === 'Expired') {
        stats.expired++;
      }
      if(data.price) stats.revenue += data.price;
    });

    animateCounter('statActivePasses', stats.active);
    animateCounter('statExpiringPasses', stats.expiring);
    animateCounter('statExpiredPasses', stats.expired);
    document.getElementById('statPassRevenue').innerText = `₹${stats.revenue.toLocaleString()}`;

    renderPasses();
  });

  function renderPasses() {
    const typeFilter = document.getElementById('passTypeFilter').value;
    const statusFilter = document.getElementById('passStatusFilter').value;

    let filtered = allPasses;
    
    if(typeFilter !== 'all') {
      filtered = filtered.filter(p => p.passType === typeFilter);
    }
    
    if(statusFilter !== 'all') {
      filtered = filtered.filter(p => p.status === statusFilter);
    }

    passesList.innerHTML = '';
    if (filtered.length === 0) {
      emptyState.style.display = 'flex';
    } else {
      emptyState.style.display = 'none';
      filtered.forEach(pass => {
        const daysRem = Math.max(0, Math.ceil((pass.validUntil - new Date()) / (1000 * 60 * 60 * 24)));
        const card = document.createElement('div');
        card.className = 'card pass-card';
        card.style.overflow = 'hidden';
        
        card.innerHTML = `
          <div style="background: ${gradients[pass.passType]}; padding: 15px; color: white; display: flex; justify-content: space-between; align-items: center;">
            <h3 style="margin:0">${pass.passType} Pass</h3>
            <span style="background: rgba(255,255,255,0.2); padding: 4px 8px; border-radius: 4px; font-size: 0.8rem;">${pass.status}</span>
          </div>
          <div class="card-body">
            <p><strong>Customer:</strong> ${pass.customerName}</p>
            <p><strong>Plate:</strong> ${pass.vehiclePlate}</p>
            <p><strong>Valid:</strong> ${pass.validFrom.toLocaleDateString()} to ${pass.validUntil.toLocaleDateString()}</p>
            <p style="color: ${daysRem <= 7 && daysRem > 0 ? 'var(--warning)' : 'inherit'}"><strong>Days Remaining:</strong> ${daysRem}</p>
            
            <div class="mt-3 flex-row gap-2">
              <button class="btn btn-sm btn-primary">Renew</button>
              ${pass.status === 'Active' ? `<button class="btn btn-sm btn-outline btn-cancel" data-id="${pass.id}">Cancel</button>` : ''}
            </div>
          </div>
        `;
        passesList.appendChild(card);
      });
    }

    document.querySelectorAll('.btn-cancel').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const id = e.target.getAttribute('data-id');
        if(confirm('Cancel this pass?')) {
          await updateDoc(doc(db, 'passes', id), { status: 'Cancelled' });
          showToast('Pass cancelled', 'success');
        }
      });
    });
  }

  document.getElementById('passTypeFilter').addEventListener('change', renderPasses);
  document.getElementById('passStatusFilter').addEventListener('change', renderPasses);

  // New Pass Modal
  const modal = document.getElementById('newPassModal');
  document.getElementById('btnNewPass').addEventListener('click', () => modal.style.display = 'flex');
  document.querySelectorAll('.close-modal, #btnCancelPass').forEach(btn => {
    btn.addEventListener('click', () => modal.style.display = 'none');
  });

  const typeRadios = document.querySelectorAll('input[name="passType"]');
  const validFrom = document.getElementById('passValidFrom');
  const validUntil = document.getElementById('passValidUntil');
  const priceDisplay = document.getElementById('passPriceDisplay');
  
  // Initialize dates
  validFrom.valueAsDate = new Date();
  
  function updatePassDatesAndPrice() {
    let type = 'Daily';
    typeRadios.forEach(r => { if(r.checked) type = r.value; });
    
    let end = new Date(validFrom.value);
    if(type === 'Daily') end.setDate(end.getDate()); // End of day technically, keep same date
    if(type === 'Weekly') end.setDate(end.getDate() + 7);
    if(type === 'Monthly') end.setMonth(end.getMonth() + 1);
    if(type === 'Annual') end.setFullYear(end.getFullYear() + 1);
    
    validUntil.valueAsDate = end;
    priceDisplay.innerText = `₹${prices[type]}`;
  }

  typeRadios.forEach(r => r.addEventListener('change', updatePassDatesAndPrice));
  validFrom.addEventListener('change', updatePassDatesAndPrice);
  updatePassDatesAndPrice(); // Init

  document.getElementById('passForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const cust = document.getElementById('passCustomerSearch').value;
    const plate = document.getElementById('passVehiclePlate').value;
    let type = 'Daily';
    typeRadios.forEach(r => { if(r.checked) type = r.value; });
    const fromDate = new Date(validFrom.value);
    const untilDate = new Date(validUntil.value);

    try {
      await addDoc(collection(db, 'passes'), {
        customerName: cust,
        vehiclePlate: plate,
        passType: type,
        validFrom: fromDate,
        validUntil: untilDate,
        price: prices[type],
        status: 'Active',
        createdAt: serverTimestamp()
      });
      
      showToast('Pass issued successfully', 'success');
      modal.style.display = 'none';
      e.target.reset();
      updatePassDatesAndPrice();
    } catch(err) {
      console.error(err);
      showToast('Error issuing pass', 'error');
    }
  });

});
