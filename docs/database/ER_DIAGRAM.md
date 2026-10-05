# Entity–Relationship Diagram

Smart Parking Lot Allocation & Billing System — DBMS PBL Project 20.

This diagram is drawn from the live schema in `db/migrations/`, not from an
earlier sketch. Every relationship shown below corresponds to a real foreign
key you can list with `\d+ <table>` in `psql`.

---

## 1. Full model

```mermaid
erDiagram
    FACILITY ||--o{ FLOOR            : "is divided into"
    FACILITY ||--o{ TARIFF           : "prices"
    FACILITY ||--o{ PARKING_PASS     : "honours"
    FACILITY ||--o{ APP_USER         : "posts operators to"
    FLOOR    ||--o{ ZONE             : "contains"
    ZONE     ||--o{ SLOT             : "contains"

    VEHICLE_TYPE ||--o{ SLOT          : "slot is built for"
    VEHICLE_TYPE ||--o{ VEHICLE       : "classifies"
    VEHICLE_TYPE ||--o{ TARIFF        : "is priced by"
    VEHICLE_TYPE ||--o{ PASS_TYPE     : "is sold for"

    APP_USER ||--o| CUSTOMER          : "may log in as"
    CUSTOMER ||--o{ VEHICLE           : "owns"
    CUSTOMER ||--o{ RESERVATION       : "books"
    CUSTOMER ||--o{ PARKING_PASS      : "buys"

    VEHICLE  ||--o{ RESERVATION       : "is booked for"
    VEHICLE  ||--o{ PARKING_SESSION   : "parks in"
    VEHICLE  ||--o{ PARKING_PASS      : "is covered by"
    VEHICLE  ||--o{ VIOLATION         : "commits"

    SLOT ||--o{ RESERVATION           : "is held by"
    SLOT ||--o{ PARKING_SESSION       : "hosts"
    SLOT ||--o{ VIOLATION             : "is site of"

    RESERVATION ||--o| PARKING_SESSION : "is fulfilled by"
    PARKING_PASS ||--o{ PARKING_SESSION : "covers"
    PASS_TYPE   ||--o{ PARKING_PASS    : "is instantiated as"

    PARKING_SESSION ||--o| BILL        : "produces"
    PARKING_SESSION ||--o{ VIOLATION   : "may incur"
    TARIFF   ||--o{ BILL               : "priced by"
    BILL     ||--o{ PAYMENT            : "is settled by"
    APP_USER ||--o{ PAYMENT            : "receives"
    APP_USER ||--o{ PARKING_SESSION    : "operates gate for"

    FACILITY {
        bigint  facility_id  PK
        text    name         UK
        text    address_line
        text    city
        time    opens_at
        time    closes_at
        numeric tax_rate_pct
        boolean is_active
    }
    FLOOR {
        bigint  floor_id     PK
        bigint  facility_id  FK
        int     level_number "UK with facility_id"
        text    name
    }
    ZONE {
        bigint  zone_id   PK
        bigint  floor_id  FK
        text    code      "UK with floor_id"
        text    name
    }
    SLOT {
        bigint  slot_id         PK
        bigint  zone_id         FK
        text    code            "UK with zone_id"
        bigint  vehicle_type_id FK "UK with slot_id - see rule 2"
        boolean is_active
        smallint grid_row
        smallint grid_col
    }
    VEHICLE_TYPE {
        bigint   vehicle_type_id PK
        text     code            UK
        text     name
        smallint footprint_units
    }
    APP_USER {
        bigint    user_id      PK
        citext    email        UK
        text      password_hash
        text      full_name
        user_role role
        bigint    facility_id  FK "required iff role = operator"
        boolean   is_active
    }
    CUSTOMER {
        bigint  customer_id PK
        bigint  user_id     FK "UK, nullable for walk-ins"
        text    full_name
        text    phone       UK
        citext  email       UK
    }
    VEHICLE {
        bigint  vehicle_id      PK
        bigint  customer_id     FK
        text    plate_number    UK
        bigint  vehicle_type_id FK "UK with vehicle_id - see rule 2"
        text    make
        text    model
        text    colour
    }
    TARIFF {
        bigint      tariff_id            PK
        bigint      facility_id          FK
        bigint      vehicle_type_id      FK
        text        name
        int         free_minutes
        numeric     first_hour_rate
        numeric     subsequent_hour_rate
        numeric     daily_cap
        timestamptz effective_from
        timestamptz effective_to         "NULL = in force"
    }
    RESERVATION {
        bigint             reservation_id PK
        bigint             customer_id    FK
        bigint             vehicle_id     FK
        bigint             slot_id        FK
        timestamptz        reserved_from
        timestamptz        reserved_until
        reservation_status status
    }
    PARKING_SESSION {
        bigint      session_id       PK
        text        ticket_no        UK
        bigint      slot_id          FK
        bigint      vehicle_id       FK
        bigint      vehicle_type_id  FK "composite FK to both - see rule 2"
        timestamptz entry_time
        timestamptz exit_time        "NULL = still parked"
        bigint      reservation_id   FK
        bigint      pass_id          FK
        bigint      entry_operator_id FK
        bigint      exit_operator_id  FK
    }
    PASS_TYPE {
        bigint  pass_type_id    PK
        text    code            UK
        text    name
        int     duration_days
        numeric price
        bigint  vehicle_type_id FK
    }
    PARKING_PASS {
        bigint      pass_id      PK
        bigint      customer_id  FK
        bigint      vehicle_id   FK
        bigint      pass_type_id FK
        bigint      facility_id  FK
        timestamptz valid_from
        timestamptz valid_to
        numeric     price_paid
        timestamptz cancelled_at
    }
    BILL {
        bigint      bill_id          PK
        bigint      session_id       FK "UK - one bill per session"
        bigint      tariff_id        FK
        int         billable_minutes
        numeric     base_amount      "written by trigger from fn_calculate_charge"
        numeric     tax_amount
        numeric     total_amount     "GENERATED base + tax"
        bill_status status
        timestamptz generated_at
    }
    PAYMENT {
        bigint         payment_id   PK
        bigint         bill_id      FK
        numeric        amount
        payment_method method
        text           reference_no
        timestamptz    paid_at
        bigint         received_by  FK
    }
    VIOLATION {
        bigint         violation_id   PK
        violation_type kind
        bigint         session_id     FK
        bigint         vehicle_id     FK
        bigint         slot_id        FK
        timestamptz    detected_at
        numeric        penalty_amount
        timestamptz    resolved_at
    }
```

---

## 2. The structural spine

The physical hierarchy is a strict containment chain. Every slot resolves to
exactly one facility by walking it, which is why `tariff` is keyed on
`facility_id` rather than duplicated onto each bay.

```mermaid
flowchart LR
    F[FACILITY] --> FL[FLOOR] --> Z[ZONE] --> S[SLOT]
    VT[VEHICLE_TYPE] --> S
    F --> T[TARIFF]
    VT --> T
    S --> PS[PARKING_SESSION]
    T -.->|"fn_calculate_charge<br/>picks the tariff in force<br/>at entry_time"| B[BILL]
    PS --> B --> P[PAYMENT]
```

---

## 3. How the slot / vehicle-type match is enforced

This is the part worth explaining in a viva. Business rule 2 is not a trigger
and not application code — it is three constraints that make the invalid state
unrepresentable.

```mermaid
flowchart TD
    subgraph slot["SLOT"]
        SU["UNIQUE (slot_id, vehicle_type_id)"]
    end
    subgraph veh["VEHICLE"]
        VU["UNIQUE (vehicle_id, vehicle_type_id)"]
    end
    subgraph sess["PARKING_SESSION"]
        SC["carries vehicle_type_id"]
    end
    SC -->|"FK (slot_id, vehicle_type_id)"| SU
    SC -->|"FK (vehicle_id, vehicle_type_id)"| VU
    note["To insert a session the database must find BOTH<br/>referenced rows. A car in a bike bay means one of<br/>them does not exist, so the INSERT fails.<br/>There is no code path that can skip this."]
    sess -.- note
```

Because `parking_session.vehicle_type_id` is pinned simultaneously to the
slot's type and the vehicle's type, the two are forced equal. Lying about the
type in either direction fails — proven in `docs/TESTING.md`, tests 3 and 3b.

---

## 4. Cardinality summary

| Relationship | Cardinality | Enforced by |
|---|---|---|
| facility → floor | 1 : N | `fk_floor_facility`, ON DELETE CASCADE |
| floor → zone | 1 : N | `fk_zone_floor`, ON DELETE CASCADE |
| zone → slot | 1 : N | `fk_slot_zone`, ON DELETE CASCADE |
| customer → vehicle | 1 : N | `fk_vehicle_customer`, ON DELETE RESTRICT |
| vehicle → parking_session | 1 : N over time, **1 : 1 at any instant** | `uq_active_session_vehicle` (partial unique) |
| slot → parking_session | 1 : N over time, **1 : 1 at any instant** | `uq_active_session_slot` (partial unique) |
| slot → reservation | 1 : N, **non-overlapping while live** | `ex_reservation_no_overlap` (GiST exclusion) |
| parking_session → bill | 1 : 0..1 | `bill.session_id` UNIQUE |
| bill → payment | 1 : N | `fk_payment_bill`, ON DELETE CASCADE |
| reservation → parking_session | 1 : 0..1 | `parking_session.reservation_id` UNIQUE |
| app_user → customer | 1 : 0..1 | `customer.user_id` UNIQUE, nullable |
| facility + vehicle_type → tariff | 1 : N, **one in force at a time** | `ex_tariff_no_overlap` (GiST exclusion) |

---

## 5. Deliberate absences

Three attributes a first draft would include are **not** in this model, and
their absence is the design:

| Not stored | Why | Derived instead by |
|---|---|---|
| `slot.status` (free/occupied) | Two places to update on every gate event, with nothing forcing them to agree | `v_current_occupancy` |
| `parking_session.status` (active/completed) | Derivable from `exit_time IS NULL`; storing it permits a row that claims 'active' while carrying an exit time | the `exit_time` predicate |
| `parking_pass.status` (active/expired) | Derivable from the date window; storing it needs a nightly job to stay honest | `v_pass_usage` |

Full reasoning in [NORMALIZATION.md](NORMALIZATION.md) §4.
