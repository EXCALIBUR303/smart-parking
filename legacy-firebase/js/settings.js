import { db } from './firebase-config.js';
import { initPage } from './utils.js';
import { seedSampleData } from './sample-data.js';

async function initSettings() {
    initPage('settings');

    document.getElementById('seedDataBtn').addEventListener('click', async () => {
        if(confirm('This will seed the database with sample data. Continue?')) {
            try {
                await seedSampleData(db);
                alert('Sample data seeded successfully!');
            } catch(e) {
                console.error(e);
                alert('Error seeding data: ' + e.message);
            }
        }
    });

    document.getElementById('clearDataBtn').addEventListener('click', async () => {
        if(confirm('Are you sure you want to clear all data? This cannot be undone.')) {
            // Placeholder for clear data
            alert('Data cleared (simulated).');
        }
    });
}

document.addEventListener('DOMContentLoaded', initSettings);
