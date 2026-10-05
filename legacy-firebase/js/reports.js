import { db } from './firebase-config.js';
import { collection, getDocs, query, where, orderBy } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";
import { initPage } from './utils.js';

let charts = {};

async function initReports() {
    initPage('reports');
    
    // Tab switching
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(btn.dataset.target).classList.add('active');
            loadTabData(btn.dataset.target);
        });
    });

    document.getElementById('applyFiltersBtn').addEventListener('click', () => {
        const activeTab = document.querySelector('.tab-btn.active').dataset.target;
        loadTabData(activeTab);
    });

    // Load initial data
    loadTabData('occupancyTab');
}

async function loadTabData(tabId) {
    if(tabId === 'occupancyTab') await loadOccupancyData();
    if(tabId === 'revenueTab') await loadRevenueData();
    if(tabId === 'usageTab') await loadUsageData();
    if(tabId === 'violationsTab') await loadViolationsData();
    if(tabId === 'freeSlotsTab') await loadFreeSlotsData();
}

// Chart.js dark theme defaults
Chart.defaults.color = '#94A3B8';
Chart.defaults.borderColor = 'rgba(148, 163, 184, 0.1)';

function destroyChart(id) {
    if(charts[id]) {
        charts[id].destroy();
    }
}

async function loadOccupancyData() {
    const slotsSnapshot = await getDocs(collection(db, 'slots'));
    let total = 0, occupied = 0;
    let floorData = {};
    
    slotsSnapshot.forEach(doc => {
        const slot = doc.data();
        total++;
        if(slot.status === 'occupied') occupied++;
        
        if(!floorData[slot.floor]) {
            floorData[slot.floor] = { total: 0, occupied: 0, free: 0 };
        }
        floorData[slot.floor].total++;
        if(slot.status === 'occupied') floorData[slot.floor].occupied++;
        else floorData[slot.floor].free++;
    });

    const pct = total === 0 ? 0 : Math.round((occupied/total)*100);
    document.getElementById('occupancyProgressBar').style.width = pct + '%';
    document.getElementById('occupancyPercentText').textContent = pct + '%';

    // Table
    let tableHtml = '';
    for(const [floor, data] of Object.entries(floorData)) {
        const fpct = data.total === 0 ? 0 : Math.round((data.occupied/data.total)*100);
        tableHtml += `<tr><td>${floor}</td><td>All Zones</td><td>${data.total}</td><td>${data.occupied}</td><td>${data.free}</td><td>${fpct}%</td></tr>`;
    }
    document.getElementById('snapshotTableBody').innerHTML = tableHtml;

    // Chart
    destroyChart('occupancyFloorChart');
    const ctx = document.getElementById('occupancyFloorChart').getContext('2d');
    charts['occupancyFloorChart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: Object.keys(floorData),
            datasets: [{
                label: 'Occupied',
                data: Object.values(floorData).map(d => d.occupied),
                backgroundColor: '#4F46E5'
            }, {
                label: 'Free',
                data: Object.values(floorData).map(d => d.free),
                backgroundColor: '#10B981'
            }]
        },
        options: { responsive: true }
    });
}

async function loadRevenueData() {
    // Basic mock implementation for structure
    document.getElementById('totalRevenueStat').textContent = '₹0';
}

async function loadUsageData() {
    // Basic mock
}

async function loadViolationsData() {
    // Basic mock
}

async function loadFreeSlotsData() {
    // Basic mock
}

document.addEventListener('DOMContentLoaded', initReports);
