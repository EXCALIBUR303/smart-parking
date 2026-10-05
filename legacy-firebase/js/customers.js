import { db } from './firebase-config.js';
import { collection, getDocs } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";
import { initPage } from './utils.js';

async function initCustomers() {
    initPage('customers');
    loadCustomers();
}

async function loadCustomers() {
    const custSnap = await getDocs(collection(db, 'customers'));
    const grid = document.getElementById('customersGrid');
    grid.innerHTML = '';
    
    let count = 0;
    custSnap.forEach(doc => {
        count++;
        const data = doc.data();
        const initial = data.name ? data.name.charAt(0).toUpperCase() : 'U';
        
        grid.innerHTML += `
            <div class="card customer-card">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div class="avatar" style="background: #4F46E5; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold;">
                        ${initial}
                    </div>
                    <div>
                        <h3 style="margin: 0;">${data.name || 'Unknown'}</h3>
                        <p style="margin: 0; font-size: 0.9em; color: var(--text-secondary);">${data.phone || ''}</p>
                    </div>
                </div>
            </div>
        `;
    });
    document.getElementById('totalCust').textContent = count;
}

document.addEventListener('DOMContentLoaded', initCustomers);
