-- =============================================================================
-- NexaQL Sample Customer Support Dataset
-- Run against PostgreSQL to create tables + seed data for testing
-- cross-datasource federation with the ecommerce DuckDB dataset.
--
-- References:
--   customer_id  -> ecommerce.customers.id   (1-15)
--   order_id     -> ecommerce.orders.id      (1-30)
--   order_item_id -> ecommerce.order_items.id (1-58)
-- =============================================================================

CREATE TABLE IF NOT EXISTS support_tickets (
    id              SERIAL PRIMARY KEY,
    ticket_number   VARCHAR(20) UNIQUE NOT NULL,
    customer_id     INTEGER NOT NULL,
    order_id        INTEGER,
    order_item_id   INTEGER,
    subject         VARCHAR(255) NOT NULL,
    description     TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    priority        VARCHAR(10) NOT NULL DEFAULT 'MEDIUM',
    category        VARCHAR(50) NOT NULL,
    channel         VARCHAR(20) NOT NULL DEFAULT 'EMAIL',
    assigned_to     VARCHAR(100),
    satisfaction    INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TIMESTAMP
);

INSERT INTO support_tickets (ticket_number, customer_id, order_id, order_item_id, subject, description, status, priority, category, channel, assigned_to, satisfaction, created_at, updated_at, resolved_at)
VALUES
    ('TKT-2024-0001', 1, 1, 1, 'iPhone 15 Pro screen issue', 'Screen has a dead pixel in the top right corner after 2 weeks of use', 'RESOLVED', 'HIGH', 'PRODUCT_DEFECT', 'PHONE', 'support-alice', 4, '2024-01-20 10:30:00', '2024-01-25 14:00:00', '2024-01-25 14:00:00'),
    ('TKT-2024-0002', 1, 2, 3, 'Wrong shoe size received', 'Ordered size 10 but received size 8 running shoes', 'RESOLVED', 'MEDIUM', 'WRONG_ITEM', 'EMAIL', 'support-bob', 5, '2024-02-18 09:15:00', '2024-02-22 11:30:00', '2024-02-22 11:30:00'),
    ('TKT-2024-0003', 2, 3, 6, 'Samsung Galaxy S24 battery drain', 'Battery drains within 4 hours of normal use', 'RESOLVED', 'HIGH', 'PRODUCT_DEFECT', 'CHAT', 'support-carol', 3, '2024-02-01 14:45:00', '2024-02-10 16:00:00', '2024-02-10 16:00:00'),
    ('TKT-2024-0004', 3, 4, 7, 'MacBook Air delivery delayed', 'Order shows shipped but no tracking update for 5 days', 'RESOLVED', 'MEDIUM', 'SHIPPING', 'EMAIL', 'support-alice', 4, '2024-01-15 08:00:00', '2024-01-18 10:00:00', '2024-01-18 10:00:00'),
    ('TKT-2024-0005', 3, 5, 9, 'KitchenAid Mixer missing attachment', 'The dough hook attachment was not included in the box', 'RESOLVED', 'LOW', 'MISSING_PARTS', 'EMAIL', 'support-bob', 5, '2024-03-20 11:30:00', '2024-03-25 09:00:00', '2024-03-25 09:00:00'),
    ('TKT-2024-0006', 4, 7, 11, 'North Face Jacket zipper broken', 'Main zipper broke on first use', 'RESOLVED', 'HIGH', 'PRODUCT_DEFECT', 'PHONE', 'support-carol', 2, '2024-03-05 15:20:00', '2024-03-15 17:00:00', '2024-03-15 17:00:00'),
    ('TKT-2024-0007', 5, 8, 13, 'Request for invoice copy', 'Need a copy of the invoice for expense reporting', 'RESOLVED', 'LOW', 'BILLING', 'EMAIL', 'support-alice', 5, '2024-03-12 10:00:00', '2024-03-12 14:00:00', '2024-03-12 14:00:00'),
    ('TKT-2024-0008', 5, 9, 15, 'Cancellation refund not received', 'Order was cancelled on Apr 1 but refund not reflected', 'RESOLVED', 'HIGH', 'REFUND', 'CHAT', 'support-bob', 3, '2024-04-08 09:30:00', '2024-04-15 11:00:00', '2024-04-15 11:00:00'),
    ('TKT-2024-0009', 7, 10, 16, 'MacBook Air keyboard issue', 'Several keys are unresponsive intermittently', 'OPEN', 'HIGH', 'PRODUCT_DEFECT', 'PHONE', 'support-carol', NULL, '2024-05-15 13:00:00', '2024-05-20 10:00:00', NULL),
    ('TKT-2024-0010', 7, 11, 18, 'Wrong color Ultraboost received', 'Ordered black but received white', 'IN_PROGRESS', 'MEDIUM', 'WRONG_ITEM', 'EMAIL', 'support-alice', NULL, '2024-04-10 16:45:00', '2024-04-12 09:00:00', NULL),
    ('TKT-2024-0011', 8, 12, 21, 'Running shoes sole peeling', 'Sole started peeling after 3 weeks of use', 'RESOLVED', 'MEDIUM', 'PRODUCT_DEFECT', 'CHAT', 'support-bob', 4, '2024-02-25 11:15:00', '2024-03-02 14:30:00', '2024-03-02 14:30:00'),
    ('TKT-2024-0012', 10, 14, 24, 'iPhone 15 Pro overheating', 'Phone gets very hot during video calls', 'RESOLVED', 'HIGH', 'PRODUCT_DEFECT', 'PHONE', 'support-carol', 3, '2024-02-05 10:30:00', '2024-02-12 16:00:00', '2024-02-12 16:00:00'),
    ('TKT-2024-0013', 10, 15, 26, 'MacBook Air charger not working', 'MagSafe charger stopped working after 1 month', 'RESOLVED', 'MEDIUM', 'PRODUCT_DEFECT', 'EMAIL', 'support-alice', 4, '2024-04-01 08:45:00', '2024-04-05 11:00:00', '2024-04-05 11:00:00'),
    ('TKT-2024-0014', 10, 16, 29, 'Order status stuck on pending', 'Order placed on May 28 still shows pending', 'OPEN', 'MEDIUM', 'SHIPPING', 'CHAT', 'support-bob', NULL, '2024-06-01 14:00:00', '2024-06-02 09:00:00', NULL),
    ('TKT-2024-0015', 11, 17, 30, 'Instant Pot lid not sealing', 'Pressure cooker lid does not seal properly', 'RESOLVED', 'HIGH', 'PRODUCT_DEFECT', 'PHONE', 'support-carol', 4, '2024-02-10 09:30:00', '2024-02-15 13:00:00', '2024-02-15 13:00:00'),
    ('TKT-2024-0016', 12, 18, 32, 'MacBook Air trackpad click issue', 'Trackpad requires excessive force to click', 'IN_PROGRESS', 'MEDIUM', 'PRODUCT_DEFECT', 'EMAIL', 'support-alice', NULL, '2024-05-01 11:00:00', '2024-05-05 10:00:00', NULL),
    ('TKT-2024-0017', 13, 20, 35, 'Duplicate charge on order', 'Charged twice for Atomic Habits books', 'RESOLVED', 'HIGH', 'BILLING', 'CHAT', 'support-bob', 5, '2024-04-15 10:20:00', '2024-04-18 15:00:00', '2024-04-18 15:00:00'),
    ('TKT-2024-0018', 14, 21, 37, 'MacBook Air arrived damaged', 'Box was crushed and laptop has a dent on the corner', 'OPEN', 'CRITICAL', 'SHIPPING', 'PHONE', 'support-carol', NULL, '2024-04-28 08:15:00', '2024-04-29 09:00:00', NULL),
    ('TKT-2024-0019', 14, 22, 40, 'Want to exchange Ultraboost size', 'Need to exchange from size 9 to size 10', 'IN_PROGRESS', 'LOW', 'EXCHANGE', 'EMAIL', 'support-alice', NULL, '2024-06-02 13:30:00', '2024-06-03 10:00:00', NULL),
    ('TKT-2024-0020', 15, 23, 43, 'Cotton T-Shirt color fading', 'Colors faded significantly after first wash', 'RESOLVED', 'LOW', 'PRODUCT_DEFECT', 'EMAIL', 'support-bob', 3, '2024-05-10 15:00:00', '2024-05-15 11:00:00', '2024-05-15 11:00:00'),
    ('TKT-2024-0021', 1, 24, 46, 'iPad Air screen protector bubbles', 'Pre-applied screen protector has air bubbles', 'RESOLVED', 'LOW', 'PRODUCT_DEFECT', 'CHAT', 'support-carol', 4, '2024-04-25 09:00:00', '2024-04-28 14:00:00', '2024-04-28 14:00:00'),
    ('TKT-2024-0022', 2, 25, 47, 'North Face Jacket stitching loose', 'Stitching on the left sleeve is coming undone', 'OPEN', 'MEDIUM', 'PRODUCT_DEFECT', 'EMAIL', 'support-alice', NULL, '2024-05-22 10:30:00', '2024-05-23 08:00:00', NULL),
    ('TKT-2024-0023', 4, 26, 49, 'MacBook Air wifi connectivity issue', 'Wifi keeps dropping every 30 minutes', 'IN_PROGRESS', 'HIGH', 'PRODUCT_DEFECT', 'PHONE', 'support-bob', NULL, '2024-05-15 14:00:00', '2024-05-18 11:00:00', NULL),
    ('TKT-2024-0024', 6, 28, 51, 'Dyson vacuum suction weak', 'Suction power dropped significantly after 2 months', 'RESOLVED', 'MEDIUM', 'PRODUCT_DEFECT', 'CHAT', 'support-carol', 4, '2024-03-15 08:30:00', '2024-03-22 16:00:00', '2024-03-22 16:00:00'),
    ('TKT-2024-0025', 9, 29, 54, 'Want full refund instead of store credit', 'Received store credit but want refund to original payment', 'RESOLVED', 'MEDIUM', 'REFUND', 'EMAIL', 'support-alice', 2, '2024-03-01 11:00:00', '2024-03-08 14:00:00', '2024-03-08 14:00:00');
