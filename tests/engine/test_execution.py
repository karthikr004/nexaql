"""End-to-end query execution tests using DuckDB in-memory.

Tests the full pipeline: NexaQL string → parse → translate → execute.
Uses a seeded DuckDB with known data for deterministic assertions.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from nexaql.adapters.duckdb_adapter import DuckDBAdapter
from nexaql.engine.parser import parse
from nexaql.ontology.models import (
    FieldDef,
    JoinStep,
    Ontology,
    OntologyEdge,
    OntologyNode,
)


SEED_SQL = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR,
    phone VARCHAR,
    region VARCHAR NOT NULL,
    total_spend DECIMAL(10,2) NOT NULL
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR NOT NULL,
    order_date DATE NOT NULL
);

CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_name VARCHAR NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL
);

CREATE TABLE support_tickets (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    category VARCHAR NOT NULL,
    priority VARCHAR NOT NULL,
    created_date DATE NOT NULL
);

-- 6 customers across 4 regions
INSERT INTO customers VALUES
    (1, 'Alice', 'alice@example.com', '555-0001', 'US-EAST', 5000.00),
    (2, 'Bob', 'bob@example.com', '555-0002', 'US-WEST', 3000.00),
    (3, 'Charlie', 'charlie@example.com', '555-0003', 'EU', 7000.00),
    (4, 'Diana', 'diana@example.com', '555-0004', 'APAC', 2000.00),
    (5, 'Eve', 'eve@example.com', '555-0005', 'US-EAST', 4000.00),
    (6, 'Frank', 'frank@example.com', '555-0006', 'EU', 6000.00);

-- 8 orders
INSERT INTO orders VALUES
    (1, 1, 1500.00, 'DELIVERED', '2024-01-15'),
    (2, 1, 2500.00, 'SHIPPED', '2024-02-20'),
    (3, 2, 1000.00, 'DELIVERED', '2024-01-10'),
    (4, 3, 3000.00, 'PENDING', '2024-03-01'),
    (5, 3, 2000.00, 'DELIVERED', '2024-02-15'),
    (6, 4, 800.00, 'CANCELLED', '2024-01-05'),
    (7, 5, 1500.00, 'SHIPPED', '2024-03-10'),
    (8, 6, 3500.00, 'DELIVERED', '2024-02-28');

-- 12 order items
INSERT INTO order_items VALUES
    (1, 1, 'Laptop', 1, 1200.00),
    (2, 1, 'Mouse', 2, 150.00),
    (3, 2, 'Monitor', 1, 2500.00),
    (4, 3, 'Keyboard', 3, 100.00),
    (5, 3, 'Mouse', 1, 150.00),
    (6, 4, 'Server', 1, 3000.00),
    (7, 5, 'Laptop', 1, 1500.00),
    (8, 5, 'Headphones', 2, 250.00),
    (9, 6, 'Tablet', 1, 800.00),
    (10, 7, 'Monitor', 1, 1500.00),
    (11, 8, 'Server', 1, 2500.00),
    (12, 8, 'UPS', 2, 500.00);

-- 10 support tickets
INSERT INTO support_tickets VALUES
    (1, 1, 'BILLING', 'HIGH', '2024-02-01'),
    (2, 1, 'PRODUCT_DEFECT', 'MEDIUM', '2024-02-15'),
    (3, 2, 'REFUND', 'LOW', '2024-01-20'),
    (4, 3, 'BILLING', 'HIGH', '2024-03-05'),
    (5, 3, 'GENERAL', 'LOW', '2024-03-10'),
    (6, 4, 'PRODUCT_DEFECT', 'CRITICAL', '2024-01-15'),
    (7, 5, 'BILLING', 'MEDIUM', '2024-03-15'),
    (8, 5, 'REFUND', 'HIGH', '2024-03-20'),
    (9, 6, 'GENERAL', 'LOW', '2024-02-25'),
    (10, 6, 'BILLING', 'MEDIUM', '2024-03-01');
"""


def _build_ontology() -> Ontology:
    customers = OntologyNode(
        table="customers",
        description="Customer records",
        primary_key="id",
        fields={
            "id": FieldDef(type="integer", description="ID"),
            "name": FieldDef(type="string", description="Name", filterable=True),
            "email": FieldDef(type="string", description="Email"),
            "phone": FieldDef(type="string", description="Phone"),
            "region": FieldDef(
                type="enum", description="Region", filterable=True,
                values=["APAC", "EU", "US-EAST", "US-WEST"],
            ),
            "total_spend": FieldDef(type="numeric", description="Total spend", filterable=True),
        },
        edges={
            "orders": OntologyEdge(
                node="orders",
                description="Customer orders",
                join_steps=[
                    JoinStep(table="orders", alias_key="orders",
                             condition="{customers}.id = {orders}.customer_id"),
                ],
            ),
            "support_tickets": OntologyEdge(
                node="support_tickets",
                description="Support tickets",
                join_steps=[
                    JoinStep(table="support_tickets", alias_key="support_tickets",
                             condition="{customers}.id = {support_tickets}.customer_id"),
                ],
            ),
        },
    )

    orders = OntologyNode(
        table="orders",
        description="Order records",
        primary_key="id",
        fields={
            "id": FieldDef(type="integer", description="ID"),
            "customer_id": FieldDef(type="integer", description="Customer ID"),
            "amount": FieldDef(type="numeric", description="Amount", filterable=True),
            "status": FieldDef(
                type="enum", description="Status", filterable=True,
                values=["PENDING", "SHIPPED", "DELIVERED", "CANCELLED"],
            ),
            "order_date": FieldDef(type="date", description="Order date", filterable=True),
        },
        edges={
            "items": OntologyEdge(
                node="order_items",
                description="Line items",
                join_steps=[
                    JoinStep(table="order_items", alias_key="order_items",
                             condition="{orders}.id = {order_items}.order_id"),
                ],
            ),
        },
    )

    order_items = OntologyNode(
        table="order_items",
        description="Order line items",
        primary_key="id",
        fields={
            "id": FieldDef(type="integer", description="ID"),
            "order_id": FieldDef(type="integer", description="Order ID"),
            "product_name": FieldDef(type="string", description="Product name", filterable=True),
            "quantity": FieldDef(type="integer", description="Quantity"),
            "unit_price": FieldDef(type="numeric", description="Unit price"),
        },
    )

    support_tickets = OntologyNode(
        table="support_tickets",
        description="Support tickets",
        primary_key="id",
        fields={
            "id": FieldDef(type="integer", description="ID"),
            "customer_id": FieldDef(type="integer", description="Customer ID"),
            "category": FieldDef(
                type="enum", description="Category", filterable=True,
                values=["BILLING", "PRODUCT_DEFECT", "REFUND", "GENERAL"],
            ),
            "priority": FieldDef(
                type="enum", description="Priority", filterable=True,
                values=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
            ),
            "created_date": FieldDef(type="date", description="Created date", filterable=True),
        },
    )

    return Ontology(
        version="1.0",
        domain="test",
        description="Test ontology for e2e tests",
        nodes={
            "customers": customers,
            "orders": orders,
            "order_items": order_items,
            "support_tickets": support_tickets,
        },
    )


@pytest.fixture(scope="module")
def ontology() -> Ontology:
    return _build_ontology()


@pytest.fixture(scope="module")
def adapter() -> DuckDBAdapter:
    a = DuckDBAdapter(":memory:")
    conn = a._get_conn()
    conn.execute(SEED_SQL)
    return a


# ---------------------------------------------------------------------------
# Simple selects
# ---------------------------------------------------------------------------

class TestSimpleExecution:

    @pytest.mark.asyncio
    async def test_select_all_customers(self, adapter, ontology):
        ast = parse("query { customers { id name region } }")
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 6
        assert all("customers__id" in r and "customers__name" in r for r in result.rows)

    @pytest.mark.asyncio
    async def test_select_with_limit(self, adapter, ontology):
        ast = parse("query { customers @limit(3) { id name } }")
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 3

    @pytest.mark.asyncio
    async def test_select_with_orderby(self, adapter, ontology):
        ast = parse("query { customers @orderby(total_spend, DESC) @limit(3) { name total_spend } }")
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 3
        spends = [r["customers__total_spend"] for r in result.rows]
        assert spends == sorted(spends, reverse=True)

    @pytest.mark.asyncio
    async def test_select_distinct(self, adapter, ontology):
        ast = parse("query { customers @distinct { region } }")
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 4


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

class TestFilterExecution:

    @pytest.mark.asyncio
    async def test_eq_filter(self, adapter, ontology):
        ast = parse('query { customers(region: "US-EAST") { id name } }')
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 2

    @pytest.mark.asyncio
    async def test_gt_filter(self, adapter, ontology):
        ast = parse("query { customers(total_spend_gt: 5000) { id name total_spend } }")
        result = await adapter.execute(ast, ontology)
        for row in result.rows:
            assert row["customers__total_spend"] > 5000

    @pytest.mark.asyncio
    async def test_lte_filter(self, adapter, ontology):
        ast = parse("query { customers(total_spend_lte: 3000) { id name total_spend } }")
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 2
        for row in result.rows:
            assert row["customers__total_spend"] <= 3000

    @pytest.mark.asyncio
    async def test_in_filter(self, adapter, ontology):
        ast = parse('query { customers(region_in: ["US-EAST", "US-WEST"]) { id name region } }')
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 3
        for row in result.rows:
            assert row["customers__region"] in ("US-EAST", "US-WEST")

    @pytest.mark.asyncio
    async def test_like_filter(self, adapter, ontology):
        ast = parse('query { customers(name_like: "A%") { id name } }')
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 1
        assert result.rows[0]["customers__name"] == "Alice"


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------

class TestAggregationExecution:

    @pytest.mark.asyncio
    async def test_count_all(self, adapter, ontology):
        ast = parse("query { customers { total: count() } }")
        result = await adapter.execute(ast, ontology)
        assert result.rows[0]["total"] == 6

    @pytest.mark.asyncio
    async def test_sum(self, adapter, ontology):
        ast = parse("query { customers { total: sum(total_spend) } }")
        result = await adapter.execute(ast, ontology)
        assert result.rows[0]["total"] == 27000.0

    @pytest.mark.asyncio
    async def test_avg(self, adapter, ontology):
        ast = parse("query { customers { avg_spend: avg(total_spend) } }")
        result = await adapter.execute(ast, ontology)
        assert result.rows[0]["avg_spend"] == 4500.0

    @pytest.mark.asyncio
    async def test_group_by_region(self, adapter, ontology):
        ast = parse("query { customers { region cnt: count() } }")
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 4
        region_counts = {r["customers__region"]: r["cnt"] for r in result.rows}
        assert region_counts["US-EAST"] == 2
        assert region_counts["EU"] == 2
        assert region_counts["US-WEST"] == 1
        assert region_counts["APAC"] == 1

    @pytest.mark.asyncio
    async def test_group_by_with_sum(self, adapter, ontology):
        ast = parse("query { customers { region total: sum(total_spend) } }")
        result = await adapter.execute(ast, ontology)
        region_totals = {r["customers__region"]: r["total"] for r in result.rows}
        assert region_totals["US-EAST"] == 9000.0
        assert region_totals["EU"] == 13000.0


# ---------------------------------------------------------------------------
# Edge aggregation GROUP BY (regression for #11)
# ---------------------------------------------------------------------------

class TestEdgeAggregationExecution:

    @pytest.mark.asyncio
    async def test_root_field_with_edge_count(self, adapter, ontology):
        """Root scalar fields must appear in GROUP BY when edge has aggregation."""
        ast = parse("""query {
            customers {
                region
                support_tickets {
                    case_count: count()
                }
            }
        }""")
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 4
        assert result.row_count > 0

    @pytest.mark.asyncio
    async def test_edge_count_with_edge_field(self, adapter, ontology):
        """Both root and edge scalar fields grouped correctly."""
        ast = parse("""query {
            customers {
                region
                support_tickets {
                    category
                    case_count: count()
                }
            }
        }""")
        result = await adapter.execute(ast, ontology)
        assert result.row_count > 0
        assert result.row_count > 0

    @pytest.mark.asyncio
    async def test_edge_count_with_filter(self, adapter, ontology):
        ast = parse("""query {
            customers {
                region
                support_tickets(category_in: ["BILLING", "REFUND"]) {
                    case_count: count()
                }
            }
        }""")
        result = await adapter.execute(ast, ontology)
        assert result.row_count > 0
        for row in result.rows:
            assert row["case_count"] >= 0


# ---------------------------------------------------------------------------
# Edge joins
# ---------------------------------------------------------------------------

class TestEdgeJoinExecution:

    @pytest.mark.asyncio
    async def test_single_edge(self, adapter, ontology):
        ast = parse("query { customers { name orders { amount status } } }")
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 8
        assert all("customers__name" in r for r in result.rows)

    @pytest.mark.asyncio
    async def test_nested_edge(self, adapter, ontology):
        ast = parse("""query {
            customers {
                name
                orders {
                    amount
                    items { product_name quantity }
                }
            }
        }""")
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 12
        assert all("product_name" in k for k in result.rows[0] if "product" in k)

    @pytest.mark.asyncio
    async def test_edge_with_filter(self, adapter, ontology):
        ast = parse('query { customers { name orders(status: "DELIVERED") { amount } } }')
        result = await adapter.execute(ast, ontology)
        assert result.row_count == 4

    @pytest.mark.asyncio
    async def test_edge_with_aggregation(self, adapter, ontology):
        ast = parse("""query {
            customers {
                name
                orders {
                    total_orders: count()
                    total_amount: sum(amount)
                }
            }
        }""")
        result = await adapter.execute(ast, ontology)
        alice = [r for r in result.rows if r["customers__name"] == "Alice"]
        assert len(alice) == 1
        assert alice[0]["total_orders"] == 2
        assert alice[0]["total_amount"] == 4000.0


# ---------------------------------------------------------------------------
# Type preservation
# ---------------------------------------------------------------------------

class TestTypePreservation:

    @pytest.mark.asyncio
    async def test_decimal_type(self, adapter, ontology):
        ast = parse("query { customers { total_spend } }")
        result = await adapter.execute(ast, ontology)
        spend_col = [c for c in result.columns if "total_spend" in c.name]
        assert len(spend_col) == 1
        assert spend_col[0].type == "numeric"

    @pytest.mark.asyncio
    async def test_integer_type(self, adapter, ontology):
        ast = parse("query { customers { id } }")
        result = await adapter.execute(ast, ontology)
        id_col = [c for c in result.columns if "id" in c.name]
        assert len(id_col) == 1
        assert id_col[0].type == "integer"

    @pytest.mark.asyncio
    async def test_string_type(self, adapter, ontology):
        ast = parse("query { customers { name } }")
        result = await adapter.execute(ast, ontology)
        name_col = [c for c in result.columns if "name" in c.name]
        assert len(name_col) == 1
        assert name_col[0].type == "string"

    @pytest.mark.asyncio
    async def test_date_type(self, adapter, ontology):
        ast = parse("query { orders { order_date } }")
        result = await adapter.execute(ast, ontology)
        date_col = [c for c in result.columns if "order_date" in c.name]
        assert len(date_col) == 1
        assert date_col[0].type == "date"
