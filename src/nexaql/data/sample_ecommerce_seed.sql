-- =============================================================================
-- NexaQL Sample E-Commerce Dataset
-- Run against DuckDB to create tables + seed data for testing
-- =============================================================================

-- ── Categories ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR NOT NULL,
    slug        VARCHAR NOT NULL,
    description VARCHAR
);

INSERT INTO categories VALUES
    (1, 'Electronics',     'electronics',     'Phones, laptops, tablets, and accessories'),
    (2, 'Clothing',        'clothing',        'Apparel, shoes, and fashion accessories'),
    (3, 'Home & Kitchen',  'home-kitchen',    'Furniture, appliances, and kitchenware'),
    (4, 'Books',           'books',           'Physical and digital books'),
    (5, 'Sports',          'sports',          'Equipment, apparel, and outdoor gear');

-- ── Products ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR NOT NULL,
    sku         VARCHAR NOT NULL,
    price       DECIMAL(10,2) NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  DATE NOT NULL
);

INSERT INTO products VALUES
    (1,  'iPhone 15 Pro',           'ELEC-001', 999.99,  1, TRUE,  '2023-09-22'),
    (2,  'MacBook Air M3',          'ELEC-002', 1299.00, 1, TRUE,  '2024-03-08'),
    (3,  'AirPods Pro',             'ELEC-003', 249.99,  1, TRUE,  '2023-09-12'),
    (4,  'Samsung Galaxy S24',      'ELEC-004', 849.99,  1, TRUE,  '2024-01-17'),
    (5,  'iPad Air',                'ELEC-005', 599.00,  1, TRUE,  '2024-05-07'),
    (6,  'Running Shoes Nike Air',  'CLTH-001', 129.99,  2, TRUE,  '2024-01-10'),
    (7,  'Levi 501 Jeans',          'CLTH-002', 69.99,   2, TRUE,  '2023-06-15'),
    (8,  'North Face Jacket',       'CLTH-003', 199.99,  2, TRUE,  '2023-10-01'),
    (9,  'Cotton T-Shirt Pack',     'CLTH-004', 34.99,   2, TRUE,  '2024-02-20'),
    (10, 'Adidas Ultraboost',       'CLTH-005', 179.99,  2, TRUE,  '2024-04-12'),
    (11, 'Instant Pot Duo',         'HOME-001', 89.99,   3, TRUE,  '2023-03-15'),
    (12, 'Dyson V15 Vacuum',        'HOME-002', 749.99,  3, TRUE,  '2023-07-20'),
    (13, 'KitchenAid Mixer',        'HOME-003', 379.99,  3, TRUE,  '2023-11-25'),
    (14, 'Nespresso Machine',       'HOME-004', 199.99,  3, TRUE,  '2024-01-05'),
    (15, 'Cast Iron Skillet',       'HOME-005', 44.99,   3, TRUE,  '2023-08-10'),
    (16, 'Atomic Habits',           'BOOK-001', 16.99,   4, TRUE,  '2023-01-10'),
    (17, 'The Pragmatic Programmer','BOOK-002', 49.99,   4, TRUE,  '2023-02-14'),
    (18, 'Designing Data Apps',     'BOOK-003', 59.99,   4, TRUE,  '2023-05-20'),
    (19, 'Clean Code',              'BOOK-004', 39.99,   4, TRUE,  '2023-04-01'),
    (20, 'System Design Interview', 'BOOK-005', 35.99,   4, FALSE, '2023-06-30'),
    (21, 'Yoga Mat Premium',        'SPRT-001', 49.99,   5, TRUE,  '2024-01-15'),
    (22, 'Resistance Bands Set',    'SPRT-002', 29.99,   5, TRUE,  '2024-02-01'),
    (23, 'Camping Tent 4-Person',   'SPRT-003', 249.99,  5, TRUE,  '2024-03-10'),
    (24, 'Hiking Backpack 40L',     'SPRT-004', 89.99,   5, TRUE,  '2024-04-05'),
    (25, 'Dumbbell Set 50lb',       'SPRT-005', 149.99,  5, TRUE,  '2024-05-01');

-- ── Customers ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS customers (
    id              INTEGER PRIMARY KEY,
    name            VARCHAR NOT NULL,
    email           VARCHAR NOT NULL UNIQUE,
    phone           VARCHAR,
    region          VARCHAR NOT NULL DEFAULT 'US-EAST',
    status          VARCHAR NOT NULL DEFAULT 'ACTIVE',
    created_at      DATE NOT NULL,
    lifetime_value  DECIMAL(10,2) DEFAULT 0
);

INSERT INTO customers VALUES
    (1,  'Alice Johnson',    'alice@example.com',    '+1-555-0101', 'US-EAST',  'ACTIVE',    '2023-01-15', 4250.95),
    (2,  'Bob Smith',        'bob@example.com',      '+1-555-0102', 'US-EAST',  'ACTIVE',    '2023-02-20', 2180.47),
    (3,  'Carol Williams',   'carol@example.com',    '+1-555-0103', 'US-WEST',  'ACTIVE',    '2023-03-10', 6890.22),
    (4,  'David Brown',      'david@example.com',    '+1-555-0104', 'US-WEST',  'ACTIVE',    '2023-04-05', 1520.00),
    (5,  'Emma Davis',       'emma@example.com',     '+44-20-7946',  'EU',       'ACTIVE',    '2023-05-18', 3340.75),
    (6,  'Frank Miller',     'frank@example.com',    '+44-20-7947',  'EU',       'INACTIVE',  '2023-06-22', 890.50),
    (7,  'Grace Wilson',     'grace@example.com',    '+81-3-1234',   'APAC',     'ACTIVE',    '2023-07-14', 5120.33),
    (8,  'Henry Taylor',     'henry@example.com',    '+81-3-5678',   'APAC',     'ACTIVE',    '2023-08-30', 2780.00),
    (9,  'Ivy Anderson',     'ivy@example.com',      '+1-555-0109', 'US-EAST',  'SUSPENDED', '2023-09-12', 450.99),
    (10, 'Jack Thomas',      'jack@example.com',     '+1-555-0110', 'US-EAST',  'ACTIVE',    '2023-10-25', 7650.10),
    (11, 'Karen Martinez',   'karen@example.com',    '+1-555-0111', 'US-WEST',  'ACTIVE',    '2024-01-03', 1890.45),
    (12, 'Leo Robinson',     'leo@example.com',      '+44-20-7948',  'EU',       'ACTIVE',    '2024-02-14', 3210.80),
    (13, 'Mia Clark',        'mia@example.com',      '+81-3-9012',   'APAC',     'ACTIVE',    '2024-03-08', 960.25),
    (14, 'Noah Lewis',       'noah@example.com',     '+1-555-0114', 'US-EAST',  'ACTIVE',    '2024-04-19', 4580.00),
    (15, 'Olivia Walker',    'olivia@example.com',   '+44-20-7949',  'EU',       'ACTIVE',    '2024-05-01', 2100.60);

-- ── Orders ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    status       VARCHAR NOT NULL,
    ordered_at   DATE NOT NULL,
    shipped_at   DATE,
    total_amount DECIMAL(10,2) NOT NULL
);

INSERT INTO orders VALUES
    (1,  1,  'DELIVERED',  '2024-01-05', '2024-01-07', 1249.98),
    (2,  1,  'DELIVERED',  '2024-02-14', '2024-02-16', 299.98),
    (3,  2,  'DELIVERED',  '2024-01-20', '2024-01-23', 849.99),
    (4,  3,  'DELIVERED',  '2024-01-08', '2024-01-10', 1548.98),
    (5,  3,  'DELIVERED',  '2024-03-15', '2024-03-17', 379.99),
    (6,  3,  'SHIPPED',    '2024-05-20', '2024-05-22', 1299.00),
    (7,  4,  'DELIVERED',  '2024-02-28', '2024-03-02', 219.98),
    (8,  5,  'DELIVERED',  '2024-03-10', '2024-03-12', 1049.98),
    (9,  5,  'CANCELLED',  '2024-04-01', NULL,         599.00),
    (10, 7,  'DELIVERED',  '2024-01-18', '2024-01-20', 2049.98),
    (11, 7,  'DELIVERED',  '2024-04-05', '2024-04-07', 449.98),
    (12, 8,  'DELIVERED',  '2024-02-10', '2024-02-12', 129.99),
    (13, 8,  'SHIPPED',    '2024-05-25', '2024-05-27', 799.98),
    (14, 10, 'DELIVERED',  '2024-01-30', '2024-02-01', 1599.98),
    (15, 10, 'DELIVERED',  '2024-03-22', '2024-03-24', 2048.97),
    (16, 10, 'PENDING',    '2024-05-28', NULL,         249.99),
    (17, 11, 'DELIVERED',  '2024-02-05', '2024-02-07', 339.98),
    (18, 12, 'DELIVERED',  '2024-03-01', '2024-03-03', 1379.98),
    (19, 12, 'SHIPPED',    '2024-05-15', '2024-05-17', 89.99),
    (20, 13, 'DELIVERED',  '2024-04-10', '2024-04-12', 164.98),
    (21, 14, 'DELIVERED',  '2024-04-25', '2024-04-27', 1949.98),
    (22, 14, 'PENDING',    '2024-05-30', NULL,         449.98),
    (23, 15, 'DELIVERED',  '2024-05-01', '2024-05-03', 279.98),
    (24, 1,  'DELIVERED',  '2024-04-20', '2024-04-22', 599.00),
    (25, 2,  'SHIPPED',    '2024-05-18', '2024-05-20', 329.98),
    (26, 4,  'DELIVERED',  '2024-05-10', '2024-05-12', 1299.00),
    (27, 5,  'PENDING',    '2024-05-29', NULL,         179.99),
    (28, 6,  'DELIVERED',  '2024-03-05', '2024-03-07', 890.50),
    (29, 9,  'DELIVERED',  '2024-02-22', '2024-02-24', 450.99),
    (30, 11, 'DELIVERED',  '2024-05-05', '2024-05-07', 1549.97);

-- ── Order Items ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    line_total DECIMAL(10,2) NOT NULL
);

INSERT INTO order_items VALUES
    (1,  1,  1,  1, 999.99,  999.99),
    (2,  1,  3,  1, 249.99,  249.99),
    (3,  2,  6,  1, 129.99,  129.99),
    (4,  2,  9,  2, 34.99,   69.98),
    (5,  2,  16, 1, 16.99,   16.99),
    (6,  3,  4,  1, 849.99,  849.99),
    (7,  4,  2,  1, 1299.00, 1299.00),
    (8,  4,  3,  1, 249.99,  249.99),
    (9,  5,  13, 1, 379.99,  379.99),
    (10, 6,  2,  1, 1299.00, 1299.00),
    (11, 7,  8,  1, 199.99,  199.99),
    (12, 7,  22, 1, 29.99,   29.99),
    (13, 8,  1,  1, 999.99,  999.99),
    (14, 8,  21, 1, 49.99,   49.99),
    (15, 9,  5,  1, 599.00,  599.00),
    (16, 10, 2,  1, 1299.00, 1299.00),
    (17, 10, 12, 1, 749.99,  749.99),
    (18, 11, 10, 1, 179.99,  179.99),
    (19, 11, 7,  2, 69.99,   139.98),
    (20, 11, 15, 1, 44.99,   44.99),
    (21, 12, 6,  1, 129.99,  129.99),
    (22, 13, 5,  1, 599.00,  599.00),
    (23, 13, 14, 1, 199.99,  199.99),
    (24, 14, 1,  1, 999.99,  999.99),
    (25, 14, 5,  1, 599.00,  599.00),
    (26, 15, 2,  1, 1299.00, 1299.00),
    (27, 15, 3,  1, 249.99,  249.99),
    (28, 15, 12, 1, 749.99,  749.99),
    (29, 16, 3,  1, 249.99,  249.99),
    (30, 17, 11, 1, 89.99,   89.99),
    (31, 17, 23, 1, 249.99,  249.99),
    (32, 18, 2,  1, 1299.00, 1299.00),
    (33, 18, 24, 1, 89.99,   89.99),
    (34, 19, 11, 1, 89.99,   89.99),
    (35, 20, 16, 2, 16.99,   33.98),
    (36, 20, 6,  1, 129.99,  129.99),
    (37, 21, 2,  1, 1299.00, 1299.00),
    (38, 21, 1,  1, 999.99,  999.99),
    (39, 21, 25, 1, 149.99,  149.99),
    (40, 22, 10, 1, 179.99,  179.99),
    (41, 22, 7,  2, 69.99,   139.98),
    (42, 22, 15, 1, 44.99,   44.99),
    (43, 23, 9,  3, 34.99,   104.97),
    (44, 23, 21, 1, 49.99,   49.99),
    (45, 23, 22, 1, 29.99,   29.99),
    (46, 24, 5,  1, 599.00,  599.00),
    (47, 25, 8,  1, 199.99,  199.99),
    (48, 25, 6,  1, 129.99,  129.99),
    (49, 26, 2,  1, 1299.00, 1299.00),
    (50, 27, 10, 1, 179.99,  179.99),
    (51, 28, 12, 1, 749.99,  749.99),
    (52, 28, 15, 1, 44.99,   44.99),
    (53, 28, 17, 1, 49.99,   49.99),
    (54, 29, 19, 2, 39.99,   79.98),
    (55, 29, 18, 1, 59.99,   59.99),
    (56, 29, 17, 1, 49.99,   49.99),
    (57, 30, 2,  1, 1299.00, 1299.00),
    (58, 30, 3,  1, 249.99,  249.99);
