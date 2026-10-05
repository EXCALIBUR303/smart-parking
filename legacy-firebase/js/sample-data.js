import { writeBatch, collection, doc } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";

export async function seedSampleData(db) {
    const batch = writeBatch(db);

    // 1. Create Facility
    const facRef = doc(collection(db, 'facilities'));
    batch.set(facRef, {
        name: 'SmartPark Central',
        address: '123 Main Street',
        operatingHours: '24/7'
    });

    // 2. Create Types
    const types = ['Car', 'Bike', 'Truck', 'EV', 'SUV'];
    types.forEach(t => {
        const tRef = doc(collection(db, 'vehicleTypes'));
        batch.set(tRef, { name: t });
    });

    // 3. Create Tariffs
    const tariffs = [
        { type: 'Car', perHour: 40, perDay: 300 },
        { type: 'Bike', perHour: 20, perDay: 150 },
        { type: 'Truck', perHour: 60, perDay: 500 },
        { type: 'EV', perHour: 50, perDay: 400 },
        { type: 'SUV', perHour: 50, perDay: 400 }
    ];
    tariffs.forEach(t => {
        const ref = doc(collection(db, 'tariffs'));
        batch.set(ref, t);
    });

    // 4. Create Slots (60 slots)
    const floors = ['Ground', 'First', 'Second'];
    const zones = ['Zone A', 'Zone B'];
    
    let slotId = 1;
    for(const floor of floors) {
        for(const zone of zones) {
            for(let i=1; i<=10; i++) {
                const sRef = doc(collection(db, 'slots'));
                let vType = 'Car';
                if(i <= 6) vType = 'Car';
                else if(i <= 8) vType = 'Bike';
                else if(i == 9) vType = 'Truck';
                else vType = 'EV';
                
                batch.set(sRef, {
                    code: `${floor.charAt(0)}${zone.charAt(zone.length-1)}-${i}`,
                    floor,
                    zone,
                    vehicleType: vType,
                    status: 'free' // setting a few as occupied later would happen here in full version
                });
                slotId++;
            }
        }
    }

    // 5. Create Customers
    const cRef = doc(collection(db, 'customers'));
    batch.set(cRef, {
        name: 'Rahul Sharma',
        phone: '+91 9876543210'
    });

    await batch.commit();
    return true;
}
