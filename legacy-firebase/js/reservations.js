import { db } from './firebase-config.js';
import { collection, addDoc, getDocs, doc, updateDoc, query, where, orderBy, onSnapshot, serverTimestamp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";
import { initPage, showToast, animateCounter, checkAuth } from './utils.js';

document.addEventListener('DOMContentLoaded', async () => {
  initPage('reservations');
  if(!await checkAuth()) return;

  const reservationsList = document.getElementById('reservationsList');
  const emptyState = document.getElementById('emptyState');
  
  // Status Colors
  const statusColors = {
    'pending': 'var(--info)', // blue
    'confirmed': 'var(--success)', // emerald
    'checkedin': 'var(--warning)', // amber
    'completed': 'var(--text-secondary)', // gray
    'expired': 'var(--danger)', // rose
    'cancelled': 'var(--border)' // slate
  };

  let allReservations = [];

  // Fetch and setup listener
  const resRef = collection(db, 'reservations');
  const q = query(resRef, orderBy('startTime', 'desc'));
  
  onSnapshot(q, (snapshot) => {
    allReservations = [];
    let stats = { total: 0, active: 0, upcoming: 0, expired: 0, cancelled: 0 };
    const now = new Date();

    snapshot.forEach(docSnap => {
      const data = docSnap.data();
      const id = docSnap.id;
      const startTime = data.startTime.toDate();
      const endTime = data.endTime.toDate();
      
      // Auto-expire check
      let currentStatus = data.status;
      if ((currentStatus === 'confirmed' || currentStatus === 'pending') && now > endTime) {
        currentStatus = 'expired';
        updateDoc(doc(db, 'reservations', id), { status: 'expired' });
      }

      allReservations.push({ id, ...data, startTime, endTime, status: currentStatus });

      stats.total++;
      if(currentStatus === 'checkedin') stats.active++;
      else if(currentStatus === 'confirmed' || currentStatus === 'pending') stats.upcoming++;
      else if(currentStatus === 'expired') stats.expired++;
      else if(currentStatus === 'cancelled') stats.cancelled++;
    });

    animateCounter('statTotal', stats.total);
    animateCounter('statActive', stats.active);
    animateCounter('statUpcoming', stats.upcoming);
    animateCounter('statExpired', stats.expired);
    animateCounter('statCancelled', stats.cancelled);

    renderReservations();
  });

  function renderReservations() {
    const statusFilter = document.getElementById('statusFilter').value;
    const dateFilter = document.getElementById('dateFilter').value;

    let filtered = allReservations;
    
    if(statusFilter !== 'all') {
      filtered = filtered.filter(r => r.status.toLowerCase() === statusFilter);
    }
    
    if(dateFilter) {
      filtered = filtered.filter(r => {
        const rDate = r.startTime.toISOString().split('T')[0];
        return rDate === dateFilter;
      });
    }

    reservationsList.innerHTML = '';
    if (filtered.length === 0) {
      emptyState.style.display = 'flex';
    } else {
      emptyState.style.display = 'none';
      filtered.forEach(res => {
        const card = document.createElement('div');
        card.className = 'card reservation-card';
        card.style.borderLeft = `4px solid ${statusColors[res.status.toLowerCase()] || '#ccc'}`;
        
        card.innerHTML = `
          <div class="card-body">
            <div class="flex-between mb-2">
              <h3 style="margin:0">${res.customerName || 'Walk-in'}</h3>
              <span class="badge" style="background-color: ${statusColors[res.status.toLowerCase()]}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem;">${res.status.toUpperCase()}</span>
            </div>
            <p><strong>Plate:</strong> ${res.vehiclePlate}</p>
            <p><strong>Slot:</strong> ${res.slotCode || 'N/A'}</p>
            <p><strong>Start:</strong> ${res.startTime.toLocaleString()}</p>
            <p><strong>End:</strong> ${res.endTime.toLocaleString()}</p>
            <div class="mt-3 flex-row gap-2">
              ${(res.status === 'confirmed') ? `<button class="btn btn-sm btn-primary btn-checkin" data-id="${res.id}">Check-in</button>` : ''}
              ${(res.status === 'confirmed' || res.status === 'pending') ? `<button class="btn btn-sm btn-outline btn-cancel" data-id="${res.id}">Cancel</button>` : ''}
              <button class="btn btn-sm btn-outline btn-details" data-id="${res.id}">Details</button>
            </div>
          </div>
        `;
        reservationsList.appendChild(card);
      });
    }

    // Attach event listeners for buttons
    document.querySelectorAll('.btn-checkin').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const id = e.target.getAttribute('data-id');
        await handleCheckin(id);
      });
    });

    document.querySelectorAll('.btn-cancel').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const id = e.target.getAttribute('data-id');
        await handleCancel(id);
      });
    });
  }

  document.getElementById('statusFilter').addEventListener('change', renderReservations);
  document.getElementById('dateFilter').addEventListener('change', renderReservations);

  async function handleCheckin(id) {
    try {
      const res = allReservations.find(r => r.id === id);
      if(!res) return;
      
      // Update res
      await updateDoc(doc(db, 'reservations', id), { status: 'checkedin' });
      
      // Update slot
      if(res.slotId) {
        await updateDoc(doc(db, 'slots', res.slotId), { status: 'occupied', vehiclePlate: res.vehiclePlate });
      }

      // Create session
      await addDoc(collection(db, 'parkingSessions'), {
        reservationId: id,
        vehiclePlate: res.vehiclePlate,
        entryTime: serverTimestamp(),
        status: 'active',
        slotId: res.slotId
      });

      showToast('Checked in successfully', 'success');
    } catch(err) {
      console.error(err);
      showToast('Error checking in', 'error');
    }
  }

  async function handleCancel(id) {
    if(!confirm('Are you sure you want to cancel this reservation?')) return;
    try {
      const res = allReservations.find(r => r.id === id);
      await updateDoc(doc(db, 'reservations', id), { status: 'cancelled' });
      if(res.slotId) {
         // check if start time is near, maybe free slot
         await updateDoc(doc(db, 'slots', res.slotId), { status: 'available' });
      }
      showToast('Reservation cancelled', 'success');
    } catch(err) {
      console.error(err);
      showToast('Error cancelling', 'error');
    }
  }

  // Modal logic
  const modal = document.getElementById('newReservationModal');
  const btnNew = document.getElementById('btnNewReservation');
  const closeModals = document.querySelectorAll('.close-modal');
  
  btnNew.addEventListener('click', () => {
    modal.style.display = 'flex';
  });

  closeModals.forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('.modal').style.display = 'none';
    });
  });

  document.getElementById('btnCancelRes').addEventListener('click', () => {
    modal.style.display = 'none';
  });

  // Mock slot loading for demo (should query based on time/type)
  document.getElementById('resVehicleType').addEventListener('change', loadAvailableSlots);
  document.getElementById('resStartTime').addEventListener('change', loadAvailableSlots);
  document.getElementById('resEndTime').addEventListener('change', loadAvailableSlots);

  async function loadAvailableSlots() {
    const slotSelect = document.getElementById('resSlot');
    slotSelect.innerHTML = '<option value="">Select a slot...</option>';
    slotSelect.disabled = false;
    
    const q = query(collection(db, 'slots'), where('status', 'in', ['available', 'reserved'])); // simplified for now
    const snap = await getDocs(q);
    snap.forEach(doc => {
      const d = doc.data();
      const opt = document.createElement('option');
      opt.value = doc.id;
      opt.textContent = `${d.code} (${d.zoneId})`;
      opt.dataset.code = d.code;
      slotSelect.appendChild(opt);
    });
  }

  document.getElementById('reservationForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const customerSearch = document.getElementById('resCustomerSearch').value;
    const plate = document.getElementById('resVehiclePlate').value;
    const vType = document.getElementById('resVehicleType').value;
    const st = new Date(document.getElementById('resStartTime').value);
    const et = new Date(document.getElementById('resEndTime').value);
    const slotId = document.getElementById('resSlot').value;
    const slotSelect = document.getElementById('resSlot');
    const slotCode = slotSelect.options[slotSelect.selectedIndex].dataset.code;

    try {
      await addDoc(collection(db, 'reservations'), {
        customerName: customerSearch,
        vehiclePlate: plate,
        vehicleType: vType,
        startTime: st,
        endTime: et,
        slotId: slotId,
        slotCode: slotCode,
        status: 'confirmed',
        createdAt: serverTimestamp()
      });

      // Update slot to reserved
      if(slotId) {
         await updateDoc(doc(db, 'slots', slotId), { status: 'reserved' });
      }

      showToast('Reservation created!', 'success');
      modal.style.display = 'none';
      e.target.reset();
    } catch(err) {
      console.error(err);
      showToast('Error creating reservation', 'error');
    }
  });

});
