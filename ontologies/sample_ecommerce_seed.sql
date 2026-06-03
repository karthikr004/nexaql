-- =============================================================================
-- NexaQL Sample E-Commerce Dataset
-- Run against DuckDB to create tables + seed data for testing
-- =============================================================================

-- ── Employees (org hierarchy for access control) ───────────────────────────

CREATE TABLE IF NOT EXISTS employees (
    user_id     VARCHAR PRIMARY KEY,        -- matches created_by in other tables
    name        VARCHAR NOT NULL,
    email       VARCHAR NOT NULL,
    manager_id  VARCHAR,                    -- FK to self (NULL for top-level)
    region      VARCHAR NOT NULL,
    department  VARCHAR NOT NULL,
    team_id     VARCHAR NOT NULL,
    level       VARCHAR NOT NULL,
    job_role    VARCHAR NOT NULL
);

INSERT INTO employees VALUES
    ('alice',   'Alice Johnson',   'alice@company.com',   'mgr-east',  'US-EAST',  'Engineering',  'eng-platform',  'L6', 'Engineering Manager'),
    ('bob',     'Bob Smith',       'bob@company.com',     'mgr-east',  'US-EAST',  'Engineering',  'eng-platform',  'L4', 'Software Engineer'),
    ('carol',   'Carol Williams',  'carol@company.com',   'mgr-west',  'US-WEST',  'Sales',        'sales-west',    'L6', 'Sales Manager'),
    ('david',   'David Brown',     'david@company.com',   'mgr-west',  'US-WEST',  'Sales',        'sales-west',    'L4', 'Account Executive'),
    ('emma',    'Emma Davis',      'emma@company.com',    'mgr-eu',    'EU',        'Operations',   'ops-eu',        'L6', 'Operations Manager'),
    ('mgr-east','East Director',   'director-east@company.com', NULL,  'US-EAST',  'Engineering',  'eng-platform',  'L8', 'VP Engineering'),
    ('mgr-west','West Director',   'director-west@company.com', NULL,  'US-WEST',  'Sales',        'sales-west',    'L8', 'VP Sales'),
    ('mgr-eu',  'EU Director',     'director-eu@company.com',   NULL,  'EU',        'Operations',   'ops-eu',        'L8', 'VP Operations');

-- ── Categories ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR NOT NULL,
    slug        VARCHAR NOT NULL,
    description VARCHAR,
    created_by  VARCHAR NOT NULL DEFAULT 'alice'
);

INSERT INTO categories VALUES
    (1, 'Electronics',     'electronics',     'Phones, laptops, tablets, and accessories',  'alice'),
    (2, 'Clothing',        'clothing',        'Apparel, shoes, and fashion accessories',    'bob'),
    (3, 'Home & Kitchen',  'home-kitchen',    'Furniture, appliances, and kitchenware',     'carol'),
    (4, 'Books',           'books',           'Physical and digital books',                 'david'),
    (5, 'Sports',          'sports',          'Equipment, apparel, and outdoor gear',       'emma');

-- ── Products ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR NOT NULL,
    sku         VARCHAR NOT NULL,
    price       DECIMAL(10,2) NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  DATE NOT NULL,
    created_by  VARCHAR NOT NULL DEFAULT 'alice'
);

INSERT INTO products VALUES
    (1,  'iPhone 15 Pro',           'ELEC-001', 999.99,  1, TRUE,  '2023-09-22', 'alice'),
    (2,  'MacBook Air M3',          'ELEC-002', 1299.00, 1, TRUE,  '2024-03-08', 'alice'),
    (3,  'AirPods Pro',             'ELEC-003', 249.99,  1, TRUE,  '2023-09-12', 'alice'),
    (4,  'Samsung Galaxy S24',      'ELEC-004', 849.99,  1, TRUE,  '2024-01-17', 'alice'),
    (5,  'iPad Air',                'ELEC-005', 599.00,  1, TRUE,  '2024-05-07', 'alice'),
    (6,  'Running Shoes Nike Air',  'CLTH-001', 129.99,  2, TRUE,  '2024-01-10', 'bob'),
    (7,  'Levi 501 Jeans',          'CLTH-002', 69.99,   2, TRUE,  '2023-06-15', 'bob'),
    (8,  'North Face Jacket',       'CLTH-003', 199.99,  2, TRUE,  '2023-10-01', 'bob'),
    (9,  'Cotton T-Shirt Pack',     'CLTH-004', 34.99,   2, TRUE,  '2024-02-20', 'bob'),
    (10, 'Adidas Ultraboost',       'CLTH-005', 179.99,  2, TRUE,  '2024-04-12', 'bob'),
    (11, 'Instant Pot Duo',         'HOME-001', 89.99,   3, TRUE,  '2023-03-15', 'carol'),
    (12, 'Dyson V15 Vacuum',        'HOME-002', 749.99,  3, TRUE,  '2023-07-20', 'carol'),
    (13, 'KitchenAid Mixer',        'HOME-003', 379.99,  3, TRUE,  '2023-11-25', 'carol'),
    (14, 'Nespresso Machine',       'HOME-004', 199.99,  3, TRUE,  '2024-01-05', 'carol'),
    (15, 'Cast Iron Skillet',       'HOME-005', 44.99,   3, TRUE,  '2023-08-10', 'carol'),
    (16, 'Atomic Habits',           'BOOK-001', 16.99,   4, TRUE,  '2023-01-10', 'david'),
    (17, 'The Pragmatic Programmer','BOOK-002', 49.99,   4, TRUE,  '2023-02-14', 'david'),
    (18, 'Designing Data Apps',     'BOOK-003', 59.99,   4, TRUE,  '2023-05-20', 'david'),
    (19, 'Clean Code',              'BOOK-004', 39.99,   4, TRUE,  '2023-04-01', 'david'),
    (20, 'System Design Interview', 'BOOK-005', 35.99,   4, FALSE, '2023-06-30', 'david'),
    (21, 'Yoga Mat Premium',        'SPRT-001', 49.99,   5, TRUE,  '2024-01-15', 'emma'),
    (22, 'Resistance Bands Set',    'SPRT-002', 29.99,   5, TRUE,  '2024-02-01', 'emma'),
    (23, 'Camping Tent 4-Person',   'SPRT-003', 249.99,  5, TRUE,  '2024-03-10', 'emma'),
    (24, 'Hiking Backpack 40L',     'SPRT-004', 89.99,   5, TRUE,  '2024-04-05', 'emma'),
    (25, 'Dumbbell Set 50lb',       'SPRT-005', 149.99,  5, TRUE,  '2024-05-01', 'emma');

-- ── Customers ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS customers (
    id              INTEGER PRIMARY KEY,
    name            VARCHAR NOT NULL,
    email           VARCHAR NOT NULL UNIQUE,
    phone           VARCHAR,
    region          VARCHAR NOT NULL DEFAULT 'US-EAST',
    status          VARCHAR NOT NULL DEFAULT 'ACTIVE',
    created_at      DATE NOT NULL,
    lifetime_value  DECIMAL(10,2) DEFAULT 0,
    created_by      VARCHAR NOT NULL DEFAULT 'alice'
);

INSERT INTO customers VALUES
    (1,  'Alice Johnson',    'alice@example.com',    '+1-555-0101', 'US-EAST',  'ACTIVE',    '2023-01-15', 4250.95,  'alice'),
    (2,  'Bob Smith',        'bob@example.com',      '+1-555-0102', 'US-EAST',  'ACTIVE',    '2023-02-20', 2180.47,  'bob'),
    (3,  'Carol Williams',   'carol@example.com',    '+1-555-0103', 'US-WEST',  'ACTIVE',    '2023-03-10', 6890.22,  'carol'),
    (4,  'David Brown',      'david@example.com',    '+1-555-0104', 'US-WEST',  'ACTIVE',    '2023-04-05', 1520.00,  'david'),
    (5,  'Emma Davis',       'emma@example.com',     '+44-20-7946',  'EU',       'ACTIVE',    '2023-05-18', 3340.75,  'emma'),
    (6,  'Frank Miller',     'frank@example.com',    '+44-20-7947',  'EU',       'INACTIVE',  '2023-06-22', 890.50,   'emma'),
    (7,  'Grace Wilson',     'grace@example.com',    '+81-3-1234',   'APAC',     'ACTIVE',    '2023-07-14', 5120.33,  'carol'),
    (8,  'Henry Taylor',     'henry@example.com',    '+81-3-5678',   'APAC',     'ACTIVE',    '2023-08-30', 2780.00,  'carol'),
    (9,  'Ivy Anderson',     'ivy@example.com',      '+1-555-0109', 'US-EAST',  'SUSPENDED', '2023-09-12', 450.99,   'alice'),
    (10, 'Jack Thomas',      'jack@example.com',     '+1-555-0110', 'US-EAST',  'ACTIVE',    '2023-10-25', 7650.10,  'alice'),
    (11, 'Karen Martinez',   'karen@example.com',    '+1-555-0111', 'US-WEST',  'ACTIVE',    '2024-01-03', 1890.45,  'david'),
    (12, 'Leo Robinson',     'leo@example.com',      '+44-20-7948',  'EU',       'ACTIVE',    '2024-02-14', 3210.80,  'emma'),
    (13, 'Mia Clark',        'mia@example.com',      '+81-3-9012',   'APAC',     'ACTIVE',    '2024-03-08', 960.25,   'bob'),
    (14, 'Noah Lewis',       'noah@example.com',     '+1-555-0114', 'US-EAST',  'ACTIVE',    '2024-04-19', 4580.00,  'alice'),
    (15, 'Olivia Walker',    'olivia@example.com',   '+44-20-7949',  'EU',       'ACTIVE',    '2024-05-01', 2100.60,  'emma');

-- ── Orders ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    status       VARCHAR NOT NULL,
    ordered_at   DATE NOT NULL,
    shipped_at   DATE,
    total_amount DECIMAL(10,2) NOT NULL,
    created_by   VARCHAR NOT NULL DEFAULT 'alice'
);

INSERT INTO orders VALUES
    (1,  1,  'DELIVERED',  '2024-01-05', '2024-01-07', 1249.98, 'alice'),
    (2,  1,  'DELIVERED',  '2024-02-14', '2024-02-16', 299.98,  'alice'),
    (3,  2,  'DELIVERED',  '2024-01-20', '2024-01-23', 849.99,  'bob'),
    (4,  3,  'DELIVERED',  '2024-01-08', '2024-01-10', 1548.98, 'carol'),
    (5,  3,  'DELIVERED',  '2024-03-15', '2024-03-17', 379.99,  'carol'),
    (6,  3,  'SHIPPED',    '2024-05-20', '2024-05-22', 1299.00, 'carol'),
    (7,  4,  'DELIVERED',  '2024-02-28', '2024-03-02', 219.98,  'david'),
    (8,  5,  'DELIVERED',  '2024-03-10', '2024-03-12', 1049.98, 'emma'),
    (9,  5,  'CANCELLED',  '2024-04-01', NULL,         599.00,  'emma'),
    (10, 7,  'DELIVERED',  '2024-01-18', '2024-01-20', 2049.98, 'carol'),
    (11, 7,  'DELIVERED',  '2024-04-05', '2024-04-07', 449.98,  'carol'),
    (12, 8,  'DELIVERED',  '2024-02-10', '2024-02-12', 129.99,  'carol'),
    (13, 8,  'SHIPPED',    '2024-05-25', '2024-05-27', 799.98,  'carol'),
    (14, 10, 'DELIVERED',  '2024-01-30', '2024-02-01', 1599.98, 'alice'),
    (15, 10, 'DELIVERED',  '2024-03-22', '2024-03-24', 2048.97, 'alice'),
    (16, 10, 'PENDING',    '2024-05-28', NULL,         249.99,  'alice'),
    (17, 11, 'DELIVERED',  '2024-02-05', '2024-02-07', 339.98,  'david'),
    (18, 12, 'DELIVERED',  '2024-03-01', '2024-03-03', 1379.98, 'emma'),
    (19, 12, 'SHIPPED',    '2024-05-15', '2024-05-17', 89.99,   'emma'),
    (20, 13, 'DELIVERED',  '2024-04-10', '2024-04-12', 164.98,  'bob'),
    (21, 14, 'DELIVERED',  '2024-04-25', '2024-04-27', 1949.98, 'alice'),
    (22, 14, 'PENDING',    '2024-05-30', NULL,         449.98,  'alice'),
    (23, 15, 'DELIVERED',  '2024-05-01', '2024-05-03', 279.98,  'emma'),
    (24, 1,  'DELIVERED',  '2024-04-20', '2024-04-22', 599.00,  'alice'),
    (25, 2,  'SHIPPED',    '2024-05-18', '2024-05-20', 329.98,  'bob'),
    (26, 4,  'DELIVERED',  '2024-05-10', '2024-05-12', 1299.00, 'david'),
    (27, 5,  'PENDING',    '2024-05-29', NULL,         179.99,  'emma'),
    (28, 6,  'DELIVERED',  '2024-03-05', '2024-03-07', 890.50,  'emma'),
    (29, 9,  'DELIVERED',  '2024-02-22', '2024-02-24', 450.99,  'alice'),
    (30, 11, 'DELIVERED',  '2024-05-05', '2024-05-07', 1549.97, 'david');

-- ── Order Items ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    line_total DECIMAL(10,2) NOT NULL,
    created_by VARCHAR NOT NULL DEFAULT 'alice'
);

INSERT INTO order_items VALUES
    (1,  1,  1,  1, 999.99,  999.99,  'alice'),
    (2,  1,  3,  1, 249.99,  249.99,  'alice'),
    (3,  2,  6,  1, 129.99,  129.99,  'alice'),
    (4,  2,  9,  2, 34.99,   69.98,   'alice'),
    (5,  2,  16, 1, 16.99,   16.99,   'alice'),
    (6,  3,  4,  1, 849.99,  849.99,  'bob'),
    (7,  4,  2,  1, 1299.00, 1299.00, 'carol'),
    (8,  4,  3,  1, 249.99,  249.99,  'carol'),
    (9,  5,  13, 1, 379.99,  379.99,  'carol'),
    (10, 6,  2,  1, 1299.00, 1299.00, 'carol'),
    (11, 7,  8,  1, 199.99,  199.99,  'david'),
    (12, 7,  22, 1, 29.99,   29.99,   'david'),
    (13, 8,  1,  1, 999.99,  999.99,  'emma'),
    (14, 8,  21, 1, 49.99,   49.99,   'emma'),
    (15, 9,  5,  1, 599.00,  599.00,  'emma'),
    (16, 10, 2,  1, 1299.00, 1299.00, 'carol'),
    (17, 10, 12, 1, 749.99,  749.99,  'carol'),
    (18, 11, 10, 1, 179.99,  179.99,  'carol'),
    (19, 11, 7,  2, 69.99,   139.98,  'carol'),
    (20, 11, 15, 1, 44.99,   44.99,   'carol'),
    (21, 12, 6,  1, 129.99,  129.99,  'carol'),
    (22, 13, 5,  1, 599.00,  599.00,  'carol'),
    (23, 13, 14, 1, 199.99,  199.99,  'carol'),
    (24, 14, 1,  1, 999.99,  999.99,  'alice'),
    (25, 14, 5,  1, 599.00,  599.00,  'alice'),
    (26, 15, 2,  1, 1299.00, 1299.00, 'alice'),
    (27, 15, 3,  1, 249.99,  249.99,  'alice'),
    (28, 15, 12, 1, 749.99,  749.99,  'alice'),
    (29, 16, 3,  1, 249.99,  249.99,  'alice'),
    (30, 17, 11, 1, 89.99,   89.99,   'david'),
    (31, 17, 23, 1, 249.99,  249.99,  'david'),
    (32, 18, 2,  1, 1299.00, 1299.00, 'emma'),
    (33, 18, 24, 1, 89.99,   89.99,   'emma'),
    (34, 19, 11, 1, 89.99,   89.99,   'emma'),
    (35, 20, 16, 2, 16.99,   33.98,   'bob'),
    (36, 20, 6,  1, 129.99,  129.99,  'bob'),
    (37, 21, 2,  1, 1299.00, 1299.00, 'alice'),
    (38, 21, 1,  1, 999.99,  999.99,  'alice'),
    (39, 21, 25, 1, 149.99,  149.99,  'alice'),
    (40, 22, 10, 1, 179.99,  179.99,  'alice'),
    (41, 22, 7,  2, 69.99,   139.98,  'alice'),
    (42, 22, 15, 1, 44.99,   44.99,   'alice'),
    (43, 23, 9,  3, 34.99,   104.97,  'emma'),
    (44, 23, 21, 1, 49.99,   49.99,   'emma'),
    (45, 23, 22, 1, 29.99,   29.99,   'emma'),
    (46, 24, 5,  1, 599.00,  599.00,  'alice'),
    (47, 25, 8,  1, 199.99,  199.99,  'bob'),
    (48, 25, 6,  1, 129.99,  129.99,  'bob'),
    (49, 26, 2,  1, 1299.00, 1299.00, 'david'),
    (50, 27, 10, 1, 179.99,  179.99,  'emma'),
    (51, 28, 12, 1, 749.99,  749.99,  'emma'),
    (52, 28, 15, 1, 44.99,   44.99,   'emma'),
    (53, 28, 17, 1, 49.99,   49.99,   'emma'),
    (54, 29, 19, 2, 39.99,   79.98,   'alice'),
    (55, 29, 18, 1, 59.99,   59.99,   'alice'),
    (56, 29, 17, 1, 49.99,   49.99,   'alice'),
    (57, 30, 2,  1, 1299.00, 1299.00, 'david'),
    (58, 30, 3,  1, 249.99,  249.99,  'david');
