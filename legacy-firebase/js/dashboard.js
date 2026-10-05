import { db } from './firebase-config.js';
import { collection, query, orderBy, limit, onSnapshot, getDocs } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";
import { initPage, animateCounter } from './utils.js';

let occupancyChart, revenueChart;

async function initDashboard() {
  initPage('dashboard');
  
  // Real-time listener for recent activity
  const sessionsRef = collection(db, 'parkingSessions');
  const q = query(sessionsRef, orderBy('entryTime', 'desc'), limit(10));
  
  onSnapshot(q, (snapshot) => {
    const feed = document.getElementById('activityFeed');
    feed.innerHTML = '';
    
    if (snapshot.empty) {
      feed.innerHTML = '<p style="color: #94A3B8; padding: 20px; text-align: center;">No recent activity</p>';
      return;
    }
    
    snapshot.forEach((doc) => {
      const data = doc.data();
      const statusColor = data.status === 'active' ? '#10B981' : '#94A3B8';
      const timeStr = data.entryTime ? data.entryTime.toDate().toLocaleString() : 'Just now';
      
      const item = document.createElement('div');
      item.style.padding = '12px';
      item.style.borderBottom = '1px solid rgba(148,163,184,0.1)';
      item.style.display = 'flex';
      item.style.justifyContent = 'space-between';
      item.style.alignItems = 'center';
      
      item.innerHTML = `
        <div>
          <strong style="color: #F1F5F9;">${data.vehicleId || 'Unknown'}</strong>
          <span style="color: #94A3B8; font-size: 14px; margin-left: 10px;">Slot: ${data.slotId || '-'}</span>
          <div style="font-size: 12px; color: #64748B; margin-top: 4px;">${timeStr}</div>
        </div>
        <span style="padding: 4px 8px; border-radius: 4px; font-size: 12px; background: rgba(16,185,129,0.1); color: ${statusColor};">
          ${data.status.toUpperCase()}
        </span>
      `;
      feed.appendChild(item);
    });
  });

  // Load static stats (Mocked logic for now, should aggregate from Firestore)
  try {
    const slotsSnapshot = await getDocs(collection(db, 'slots'));
    let total = 0, occupied = 0, free = 0, reserved = 0, maintenance = 0;
    
    slotsSnapshot.forEach(doc => {
      total++;
      const s = doc.data().status;
      if (s === 'occupied') occupied++;
      else if (s === 'free') free++;
      else if (s === 'reserved') reserved++;
      else if (s === 'maintenance') maintenance++;
    });

    if(total === 0) {
      total = 100; free = 80; occupied = 15; reserved = 3; maintenance = 2; // fallback mock
    }

    animateCounter('statTotalSlots', total);
    animateCounter('statOccupied', occupied);
    animateCounter('statAvailable', free);
    animateCounter('statRevenue', 12450); // Mock revenue

    initCharts(occupied, free, reserved, maintenance);
  } catch (error) {
    console.error("Error loading stats:", error);
  }
}

function initCharts(occ, free, resv, maint) {
  Chart.defaults.color = '#94A3B8';
  Chart.defaults.font.family = 'Inter';

  const ctxOcc = document.getElementById('occupancyChart').getContext('2d');
  occupancyChart = new Chart(ctxOcc, {
    type: 'doughnut',
    data: {
      labels: ['Occupied', 'Available', 'Reserved', 'Maintenance'],
      datasets: [{
        data: [occ, free, resv, maint],
        backgroundColor: ['#F43F5E', '#10B981', '#F59E0B', '#64748B'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      cutout: '70%',
      plugins: { legend: { position: 'bottom' } }
    }
  });

  const ctxRev = document.getElementById('revenueChart').getContext('2d');
  revenueChart = new Chart(ctxRev, {
    type: 'line',
    data: {
      labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      datasets: [{
        label: 'Revenue (₹)',
        data: [12000, 19000, 15000, 22000, 18000, 25000, 21000], // Mock trend
        borderColor: '#0D9488',
        backgroundColor: 'rgba(13, 148, 136, 0.1)',
        tension: 0.4,
        fill: true
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        y: { grid: { color: 'rgba(148,163,184,0.1)' } },
        x: { grid: { display: false } }
      }
    }
  });
}

document.addEventListener('DOMContentLoaded', initDashboard);

// Quick Search Modal logic
const searchBtn = document.getElementById('quickSearchBtn');
const searchModal = document.getElementById('searchModal');
const closeSearch = document.getElementById('closeSearchModal');

if(searchBtn) searchBtn.addEventListener('click', () => { searchModal.style.display = 'block'; });
if(closeSearch) closeSearch.addEventListener('click', () => { searchModal.style.display = 'none'; });
