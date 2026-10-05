# Smart Parking Lot Allocation & Billing System

A modern web application for managing parking lot operations, customers, billing, and reporting.

## Features
* **Dashboard:** Real-time overview of occupancy, revenue, and active sessions.
* **Parking Slots:** Visual map of slots by floor and zone.
* **Gate Entry/Exit:** Quick entry and exit management with automatic billing.
* **Reservations:** Manage future bookings.
* **Passes:** Support for daily, weekly, and monthly passes.
* **Billing:** Track payments, unpaid bills, and generate invoices.
* **Reports:** Detailed analytics on occupancy, revenue, usage, and violations.
* **Customers:** Manage users and their vehicles.
* **Settings:** Configure facility layout, vehicle types, and tariffs.

## Tech Stack
* HTML5 / CSS3 / JavaScript (ES Modules)
* Firebase (Firestore for Database, Authentication)
* Chart.js for visualizations

## Firebase Setup Instructions
1. Go to https://console.firebase.google.com/
2. Click 'Add Project', name it (e.g., 'smart-parking')
3. Disable Google Analytics (optional, simplifies setup)
4. Once created, click the web icon '</>' to add a web app
5. Register app name, copy the firebaseConfig object
6. Open `js/firebase-config.js` and replace placeholder values with your config
7. In Firebase Console, go to 'Build' → 'Authentication' → 'Sign-in method'
8. Enable 'Email/Password' provider
9. Go to 'Build' → 'Firestore Database' → 'Create Database'
10. Start in test mode (or production mode with the provided rules)
11. Select a region close to you

## Local Development
- Just open `index.html` in a browser (or use Live Server extension in VS Code)
- Register a new account on the login page
- Go to Settings → 'Seed Sample Data' to populate demo data

## Firebase Hosting Deployment
1. Install Firebase CLI: `npm install -g firebase-tools`
2. Login: `firebase login`
3. In project directory: `firebase init` (select Hosting and Firestore)
4. Deploy: `firebase deploy`

## Project Structure
```
smart-parking/
├── css/
│   ├── components.css
│   ├── pages.css
│   └── styles.css
├── js/
│   ├── customers.js
│   ├── firebase-config.js
│   ├── reports.js
│   ├── sample-data.js
│   ├── settings.js
│   └── utils.js
├── customers.html
├── reports.html
├── settings.html
├── firebase.json
├── firestore.rules
└── README.md
```

## Database Schema
* **facilities**: Info about the parking facilities.
* **vehicleTypes**: Allowed vehicle categories (Car, Bike, etc.).
* **slots**: Individual parking spaces with status and assigned type.
* **customers**: Registered users.
* **vehicles**: Vehicles linked to customers.
* **tariffs**: Pricing configuration per vehicle type.
* **parkingSessions**: Active and historical parking records.
* **passes**: Issued passes for customers.
* **bills**: Billing records for sessions and passes.
* **payments**: Transaction records.

## Screenshots
*(Add screenshots here)*
