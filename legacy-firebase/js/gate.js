import { db } from './firebase-config.js';
import { collection, addDoc, getDocs, doc, updateDoc, query, where, orderBy, limit, serverTimestamp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";
import { initPage } from './utils.js';

async function initGatePage() {
  initPage('gate');
  setupEntryLogic();
  setupExitLogic();
  loadRecentActivity();
}

function setupEntryLogic() {
  const vInput = document.getElementById('entryVehicleNo');
  vInput.addEventListener('input', (e) => {
    e.target.value = e.target.value.toUpperCase();
  });

  const typeRadios = document.getElementsByName('entryType');
  typeRadios.forEach(radio => {
    radio.addEventListener('change', autoAssignSlot);
  });

  document.getElementById('btnCheckPass').addEventListener('click', async () => {
    const vNo = vInput.value.trim();
    if(!vNo) return alert('Enter vehicle number first');
    
    const passStatus = document.getElementById('passStatus');
    passStatus.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';
    
    // Mock pass check for now
    setTimeout(() => {
      passStatus.innerHTML = '<span style="color:#10B981;"><i class="fas fa-check-circle"></i> Valid Pass Found</span>';
    }, 1000);
  });

  document.getElementById('btnRecordEntry').addEventListener('click', async () => {
    const vNo = vInput.value.trim();
    if(!vNo) return alert('Enter vehicle number');
    
    const vType = document.querySelector('input[name="entryType"]:checked').value;
    const slotCode = document.getElementById('assignedSlot').innerText;
    
    if(slotCode === '--' || slotCode === 'No slots available') {
      return alert('No available slots for this vehicle type');
    }

    try {
      // Find the specific slot document
      const slotsQ = query(collection(db, 'slots'), where('status', '==', 'free'), where('vehicleType', '==', vType), limit(1));
      const slotSnap = await getDocs(slotsQ);
      
      if(slotSnap.empty) return alert('Slot grabbed by someone else. Try again.');
      
      const slotDoc = slotSnap.docs[0];
      const ticketNo = 'TK-' + Math.floor(Math.random() * 100000);
      
      // Create session
      await addDoc(collection(db, 'parkingSessions'), {
        vehicleId: vNo,
        slotId: slotDoc.data().code,
        entryTime: serverTimestamp(),
        ticketNumber: ticketNo,
        status: 'active'
      });
      
      // Update slot
      await updateDoc(doc(db, 'slots', slotDoc.id), {
        status: 'occupied',
        currentVehicle: vNo
      });
      
      showEntryTicket(ticketNo, vNo, slotDoc.data().code);
      vInput.value = '';
      autoAssignSlot(); // prep next
      loadRecentActivity(); // refresh table
      
    } catch(err) {
      console.error(err);
      alert('Error recording entry');
    }
  });

  autoAssignSlot();
}

async function autoAssignSlot() {
  const vType = document.querySelector('input[name="entryType"]:checked').value;
  const slotDisplay = document.getElementById('assignedSlot');
  slotDisplay.innerText = 'Searching...';
  
  try {
    const slotsQ = query(collection(db, 'slots'), where('status', '==', 'free'), where('vehicleType', '==', vType), limit(1));
    const snap = await getDocs(slotsQ);
    
    if(!snap.empty) {
      slotDisplay.innerText = snap.docs[0].data().code;
      slotDisplay.dataset.id = snap.docs[0].id;
    } else {
      slotDisplay.innerText = 'No slots available';
      slotDisplay.dataset.id = '';
    }
  } catch (err) {
    console.error(err);
    slotDisplay.innerText = '--';
  }
}

function showEntryTicket(ticketNo, vehicle, slot) {
  document.getElementById('ticketNo').innerText = ticketNo;
  document.getElementById('ticketVehicle').innerText = vehicle;
  document.getElementById('ticketSlot').innerText = slot;
  document.getElementById('ticketTime').innerText = new Date().toLocaleString();
  
  const overlay = document.getElementById('ticketOverlay');
  overlay.style.display = 'block';
  
  setTimeout(() => {
    overlay.style.display = 'none';
  }, 5000);
}

// Exit Logic
let currentExitSession = null;
let durationInterval = null;

function setupExitLogic() {
  document.getElementById('btnLookUp').addEventListener('click', async () => {
    const searchVal = document.getElementById('exitSearchInput').value.trim();
    if(!searchVal) return;
    
    try {
      // search by ticket or vehicle
      let q = query(collection(db, 'parkingSessions'), where('ticketNumber', '==', searchVal), where('status', '==', 'active'));
      let snap = await getDocs(q);
      
      if(snap.empty) {
        q = query(collection(db, 'parkingSessions'), where('vehicleId', '==', searchVal.toUpperCase()), where('status', '==', 'active'));
        snap = await getDocs(q);
      }
      
      if(snap.empty) {
        alert('No active session found.');
        return;
      }
      
      currentExitSession = { id: snap.docs[0].id, ...snap.docs[0].data() };
      displayExitDetails();
      
    } catch(err) {
      console.error(err);
    }
  });

  document.getElementById('btnProcessExit').addEventListener('click', async () => {
    if(!currentExitSession) return;
    
    try {
      // Mock payment and bill creation
      const payMethod = document.getElementById('paymentMethod').value;
      const amount = parseFloat(document.getElementById('exitTotal').innerText.replace('₹', ''));
      
      await addDoc(collection(db, 'payments'), {
        sessionId: currentExitSession.id,
        amount: amount,
        method: payMethod,
        timestamp: serverTimestamp()
      });
      
      // Update Session
      await updateDoc(doc(db, 'parkingSessions', currentExitSession.id), {
        status: 'completed',
        exitTime: serverTimestamp()
      });
      
      // Free up slot
      const slotsQ = query(collection(db, 'slots'), where('code', '==', currentExitSession.slotId));
      const slotSnap = await getDocs(slotsQ);
      if(!slotSnap.empty) {
        await updateDoc(doc(db, 'slots', slotSnap.docs[0].id), {
          status: 'free',
          currentVehicle: null
        });
      }
      
      alert('Exit processed successfully!');
      
      document.getElementById('exitEmptyState').style.display = 'block';
      document.getElementById('exitSessionDetails').style.display = 'none';
      document.getElementById('exitSearchInput').value = '';
      clearInterval(durationInterval);
      currentExitSession = null;
      loadRecentActivity();
      
    } catch(err) {
      console.error(err);
      alert('Error processing exit');
    }
  });
}

function displayExitDetails() {
  document.getElementById('exitEmptyState').style.display = 'none';
  document.getElementById('exitSessionDetails').style.display = 'block';
  
  document.getElementById('exitVehicle').innerText = currentExitSession.vehicleId;
  document.getElementById('exitSlot').innerText = currentExitSession.slotId;
  
  const entryDate = currentExitSession.entryTime ? currentExitSession.entryTime.toDate() : new Date();
  document.getElementById('exitEntryTime').innerText = entryDate.toLocaleString();
  
  if(durationInterval) clearInterval(durationInterval);
  
  durationInterval = setInterval(() => {
    const now = new Date();
    const diffMs = now - entryDate;
    const hrs = Math.floor(diffMs / 3600000);
    const mins = Math.floor((diffMs % 3600000) / 60000);
    const secs = Math.floor((diffMs % 60000) / 1000);
    
    document.getElementById('exitDuration').innerText = 
      `${hrs.toString().padStart(2,'0')}:${mins.toString().padStart(2,'0')}:${secs.toString().padStart(2,'0')}`;
      
    // Simple calculation: ₹50/hr base
    const billHrs = Math.max(1, Math.ceil(diffMs / 3600000));
    const rate = 50;
    const base = billHrs * rate;
    const tax = base * 0.18;
    const total = base + tax;
    
    document.getElementById('exitRate').innerText = `₹${rate}`;
    document.getElementById('exitBase').innerText = `₹${base.toFixed(2)}`;
    document.getElementById('exitTax').innerText = `₹${tax.toFixed(2)}`;
    document.getElementById('exitTotal').innerText = `₹${total.toFixed(2)}`;
  }, 1000);
}

async function loadRecentActivity() {
  const tbody = document.getElementById('recentActivityTable');
  try {
    const q = query(collection(db, 'parkingSessions'), orderBy('entryTime', 'desc'), limit(10));
    const snap = await getDocs(q);
    
    tbody.innerHTML = '';
    if(snap.empty) {
      tbody.innerHTML = '<tr><td colspan="5" style="padding:20px; text-align:center;">No recent activity</td></tr>';
      return;
    }
    
    snap.forEach(doc => {
      const data = doc.data();
      const tr = document.createElement('tr');
      tr.style.borderBottom = '1px solid rgba(148,163,184,0.1)';
      
      const timeStr = data.entryTime ? data.entryTime.toDate().toLocaleTimeString() : '-';
      const actionBadge = data.status === 'active' 
        ? `<span style="padding:4px 8px; border-radius:4px; background:rgba(16,185,129,0.1); color:#10B981; font-size:12px;">ENTRY</span>`
        : `<span style="padding:4px 8px; border-radius:4px; background:rgba(244,63,94,0.1); color:#F43F5E; font-size:12px;">EXIT</span>`;
        
      tr.innerHTML = `
        <td style="padding:12px; color:#F1F5F9;">${timeStr}</td>
        <td style="padding:12px; font-weight:bold; color:#F1F5F9;">${data.vehicleId}</td>
        <td style="padding:12px; color:#94A3B8;">${data.slotId || '-'}</td>
        <td style="padding:12px;">${actionBadge}</td>
        <td style="padding:12px; color:#F1F5F9;">${data.status === 'completed' ? 'Paid' : '-'}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch(err) {
    console.error(err);
  }
}

document.addEventListener('DOMContentLoaded', initGatePage);
