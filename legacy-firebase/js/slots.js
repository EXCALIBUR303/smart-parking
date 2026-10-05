import { db } from './firebase-config.js';
import { collection, addDoc, getDocs, doc, updateDoc, query, where, onSnapshot } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";
import { initPage } from './utils.js';

let currentFacility = null;
let currentFloor = null;
let activeFilters = { type: 'all', status: 'all' };
let slotsUnsubscribe = null;

async function initSlotsPage() {
  initPage('slots');
  setupEventListeners();
  await loadFacilities();
}

function setupEventListeners() {
  document.getElementById('addFacilityBtn').addEventListener('click', () => {
    document.getElementById('addFacilityModal').style.display = 'block';
  });
  
  document.getElementById('closeFacilityModal').addEventListener('click', () => {
    document.getElementById('addFacilityModal').style.display = 'none';
  });

  document.getElementById('addFacilityForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('facName').value;
    const address = document.getElementById('facAddress').value;
    const floors = parseInt(document.getElementById('facFloors').value);
    
    try {
      const facRef = await addDoc(collection(db, 'facilities'), { name, address, floors });
      alert('Facility added successfully!');
      document.getElementById('addFacilityModal').style.display = 'none';
      await loadFacilities();
    } catch (err) {
      console.error(err);
      alert('Error adding facility');
    }
  });

  document.getElementById('facilitySelect').addEventListener('change', (e) => {
    currentFacility = e.target.value;
    loadFloors();
  });

  document.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      e.target.closest('.filter-chip').classList.add('active');
      activeFilters.type = e.target.closest('.filter-chip').dataset.type;
      renderSlots();
    });
  });

  document.getElementById('statusSelect').addEventListener('change', (e) => {
    activeFilters.status = e.target.value;
    renderSlots();
  });

  document.getElementById('fabAddSlot').addEventListener('click', () => {
    document.getElementById('addSlotModal').style.display = 'block';
    populateZonesDropdown();
  });

  document.getElementById('closeSlotModal').addEventListener('click', () => {
    document.getElementById('addSlotModal').style.display = 'none';
  });

  document.getElementById('addSlotForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const zoneId = document.getElementById('slotZone').value;
    const type = document.getElementById('slotType').value;
    const slotCode = `S-${Math.floor(Math.random()*10000)}`;
    
    try {
      await addDoc(collection(db, 'slots'), {
        code: slotCode,
        zoneId: zoneId,
        facilityId: currentFacility,
        floorId: currentFloor,
        vehicleType: type,
        status: 'free'
      });
      document.getElementById('addSlotModal').style.display = 'none';
      alert('Slot added');
    } catch(err) {
      console.error(err);
    }
  });
  
  document.getElementById('closeDetailModal').addEventListener('click', () => {
    document.getElementById('slotDetailModal').style.display = 'none';
  });
}

async function loadFacilities() {
  const select = document.getElementById('facilitySelect');
  select.innerHTML = '<option value="">Select Facility</option>';
  
  const snap = await getDocs(collection(db, 'facilities'));
  if (snap.empty) {
    select.innerHTML = '<option value="">No facilities found. Add one!</option>';
    return;
  }
  
  snap.forEach(doc => {
    const opt = document.createElement('option');
    opt.value = doc.id;
    opt.textContent = doc.data().name;
    select.appendChild(opt);
  });
  
  if (!currentFacility && snap.docs.length > 0) {
    currentFacility = snap.docs[0].id;
    select.value = currentFacility;
    loadFloors();
  }
}

async function loadFloors() {
  if (!currentFacility) return;
  const tabsContainer = document.getElementById('floorTabs');
  tabsContainer.innerHTML = '';
  
  // Mocking floors based on facility doc for simplicity, or just fetching zones
  const snap = await getDocs(query(collection(db, 'zones'), where('facilityId', '==', currentFacility)));
  let zones = [];
  snap.forEach(d => {
    zones.push({id: d.id, ...d.data()});
  });
  
  if(zones.length === 0) {
    // create a default zone
    const zRef = await addDoc(collection(db, 'zones'), { facilityId: currentFacility, name: 'Main Zone' });
    zones.push({id: zRef.id, name: 'Main Zone'});
  }
  
  currentFloor = 'floor-1'; // Mock floor selection
  
  tabsContainer.innerHTML = `<button class="btn btn-primary" style="background:#4F46E5; color:white; border:none; padding:8px 16px; border-radius:8px;">Ground Floor</button>`;
  
  loadSlots(zones);
}

let allSlots = [];

function loadSlots(zones) {
  if (slotsUnsubscribe) slotsUnsubscribe();
  
  const q = query(collection(db, 'slots'), where('facilityId', '==', currentFacility));
  slotsUnsubscribe = onSnapshot(q, (snapshot) => {
    allSlots = [];
    snapshot.forEach(doc => allSlots.push({id: doc.id, ...doc.data()}));
    
    // Map slots to zones
    const zonesContainer = document.getElementById('zonesContainer');
    zonesContainer.innerHTML = '';
    
    zones.forEach(zone => {
      const zDiv = document.createElement('div');
      zDiv.style.marginBottom = '30px';
      zDiv.innerHTML = `<h3 style="margin-bottom:15px; color:#94A3B8;">${zone.name}</h3>`;
      
      const grid = document.createElement('div');
      grid.className = 'slot-grid';
      grid.style.display = 'grid';
      grid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(100px, 1fr))';
      grid.style.gap = '15px';
      grid.id = `grid-${zone.id}`;
      
      zDiv.appendChild(grid);
      zonesContainer.appendChild(zDiv);
    });
    
    renderSlots();
  });
}

function renderSlots() {
  // Clear grids
  document.querySelectorAll('.slot-grid').forEach(g => g.innerHTML = '');
  
  let stats = { total: 0, free: 0, occupied: 0, reserved: 0 };
  
  allSlots.forEach(slot => {
    if (activeFilters.type !== 'all' && slot.vehicleType !== activeFilters.type) return;
    if (activeFilters.status !== 'all' && slot.status !== activeFilters.status) return;
    
    stats.total++;
    stats[slot.status] = (stats[slot.status] || 0) + 1;
    
    const grid = document.getElementById(`grid-${slot.zoneId}`);
    if(!grid) return; // zone grid not found (maybe single zone fallback)
    
    const div = document.createElement('div');
    let color = '#94A3B8', bg = 'rgba(148,163,184,0.1)';
    if (slot.status === 'free') { color = '#10B981'; bg = 'rgba(16,185,129,0.1)'; }
    if (slot.status === 'occupied') { color = '#F43F5E'; bg = 'rgba(244,63,94,0.1)'; }
    if (slot.status === 'reserved') { color = '#F59E0B'; bg = 'rgba(245,158,11,0.1)'; }
    
    div.style.background = bg;
    div.style.border = `1px solid ${color}`;
    div.style.borderRadius = '8px';
    div.style.padding = '15px 10px';
    div.style.textAlign = 'center';
    div.style.cursor = 'pointer';
    div.style.position = 'relative';
    div.style.transition = 'all 0.3s ease';
    
    let icon = 'fa-car';
    if(slot.vehicleType === 'bike') icon = 'fa-motorcycle';
    if(slot.vehicleType === 'truck') icon = 'fa-truck';
    if(slot.vehicleType === 'ev') icon = 'fa-charging-station';
    
    div.innerHTML = `
      <i class="fas ${icon}" style="font-size:24px; color:${color}; margin-bottom:10px; display:block;"></i>
      <div style="font-weight:bold; color:#F1F5F9; font-size:14px;">${slot.code}</div>
      ${slot.status === 'occupied' && slot.currentVehicle ? `<div style="font-size:10px; color:${color}; margin-top:5px;">${slot.currentVehicle}</div>` : ''}
    `;
    
    div.addEventListener('click', () => showSlotDetails(slot));
    grid.appendChild(div);
  });
  
  // Also append to main fallback grid if specific zone missing
  if(document.querySelectorAll('.slot-grid').length === 0) {
    const defaultGrid = document.createElement('div');
    defaultGrid.className = 'slot-grid';
    defaultGrid.style.display = 'grid';
    defaultGrid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(100px, 1fr))';
    defaultGrid.style.gap = '15px';
    document.getElementById('zonesContainer').appendChild(defaultGrid);
    // run render again for default grid
  }
  
  document.getElementById('statTotal').innerText = stats.total;
  document.getElementById('statFree').innerText = stats.free || 0;
  document.getElementById('statOccup').innerText = stats.occupied || 0;
  document.getElementById('statResv').innerText = stats.reserved || 0;
}

function showSlotDetails(slot) {
  document.getElementById('detailSlotCode').innerText = `Slot ${slot.code}`;
  const body = document.getElementById('slotDetailBody');
  body.innerHTML = `
    <p><strong>Status:</strong> ${slot.status.toUpperCase()}</p>
    <p><strong>Type:</strong> ${slot.vehicleType.toUpperCase()}</p>
    ${slot.status === 'occupied' ? `<p><strong>Vehicle:</strong> ${slot.currentVehicle || 'N/A'}</p>` : ''}
  `;
  
  const modal = document.getElementById('slotDetailModal');
  modal.style.display = 'block';
  
  // Attach current slot ID to buttons for actions
  document.getElementById('btnToggleMaint').onclick = async () => {
    const newStatus = slot.status === 'maintenance' ? 'free' : 'maintenance';
    await updateDoc(doc(db, 'slots', slot.id), { status: newStatus });
    modal.style.display = 'none';
  };
  
  document.getElementById('btnFreeSlot').onclick = async () => {
    await updateDoc(doc(db, 'slots', slot.id), { status: 'free', currentVehicle: null });
    modal.style.display = 'none';
  };
}

async function populateZonesDropdown() {
  const sel = document.getElementById('slotZone');
  sel.innerHTML = '';
  const snap = await getDocs(query(collection(db, 'zones'), where('facilityId', '==', currentFacility)));
  snap.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d.id;
    opt.textContent = d.data().name;
    sel.appendChild(opt);
  });
}

document.addEventListener('DOMContentLoaded', initSlotsPage);
