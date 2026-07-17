"""Tests for schema generation: type mapping, enum detection, edge discovery.

Uses DuckDB in-memory databases with known data to validate that the
ontology generator produces correct field types, enum classifications,
and FK-based edges.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from nexaql.ontology.generator import (
    OntologyGenerator,
    _is_likely_enum,
    _is_pii,
    _map_type,
    _table_to_node_name,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestMapType:

    def test_integer_types(self):
        for t in ("integer", "int", "int4", "int8", "bigint", "smallint", "serial"):
            assert _map_type(t) == "integer", f"Failed for {t}"

    def test_numeric_types(self):
        for t in ("numeric", "decimal", "real", "double precision", "float", "money"):
            assert _map_type(t) == "numeric", f"Failed for {t}"

    def test_string_types(self):
        for t in ("character varying", "varchar", "text", "char", "uuid"):
            assert _map_type(t) == "string", f"Failed for {t}"

    def test_boolean(self):
        assert _map_type("boolean") == "boolean"
        assert _map_type("bool") == "boolean"

    def test_date_types(self):
        for t in ("date", "timestamp", "timestamp without time zone", "timestamptz"):
            assert _map_type(t) == "date", f"Failed for {t}"

    def test_parameterized_types(self):
        assert _map_type("varchar(255)") == "string"
        assert _map_type("numeric(10,2)") == "numeric"
        assert _map_type("decimal(18,4)") == "numeric"

    def test_unknown_defaults_to_string(self):
        assert _map_type("unknown_type") == "string"
        assert _map_type("bytea") == "string"


class TestIsLikelyEnum:

    def test_known_enum_patterns(self):
        assert _is_likely_enum("status") is True
        assert _is_likely_enum("order_status") is True
        assert _is_likely_enum("region") is True
        assert _is_likely_enum("category") is True
        assert _is_likely_enum("priority") is True
        assert _is_likely_enum("account_type") is True

    def test_non_enum_columns(self):
        assert _is_likely_enum("name") is False
        assert _is_likely_enum("email") is False
        assert _is_likely_enum("phone") is False
        assert _is_likely_enum("address") is False
        assert _is_likely_enum("description") is False
        assert _is_likely_enum("amount") is False
        assert _is_likely_enum("id") is False


class TestIsPii:

    def test_pii_columns(self):
        assert _is_pii("email") is True
        assert _is_pii("phone") is True
        assert _is_pii("ssn") is True
        assert _is_pii("password") is True
        assert _is_pii("home_address") is True

    def test_non_pii_columns(self):
        assert _is_pii("status") is False
        assert _is_pii("amount") is False
        assert _is_pii("region") is False
        assert _is_pii("order_date") is False


class TestTableToNodeName:

    def test_strips_prefix(self):
        assert _table_to_node_name("tbl_customers") == "customers"
        assert _table_to_node_name("t_orders") == "orders"

    def test_lowercase(self):
        assert _table_to_node_name("Customers") == "customers"
        assert _table_to_node_name("ORDER_ITEMS") == "order_items"

    def test_no_prefix(self):
        assert _table_to_node_name("customers") == "customers"


# ---------------------------------------------------------------------------
# Enum detection with DuckDB
# ---------------------------------------------------------------------------

ENUM_TEST_SQL = """
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    phone VARCHAR,
    status VARCHAR NOT NULL,
    region VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    description TEXT,
    price DECIMAL(10,2)
);

-- Insert 20 rows: status has 3 values, region has 4 values, category has 5 values
-- name, email, phone are all unique (high cardinality)
INSERT INTO products VALUES
    (1, 'Product A1', 'a1@test.com', '555-0001', 'ACTIVE', 'US-EAST', 'ELECTRONICS', 'Desc 1', 100.00),
    (2, 'Product A2', 'a2@test.com', '555-0002', 'ACTIVE', 'US-WEST', 'CLOTHING', 'Desc 2', 200.00),
    (3, 'Product A3', 'a3@test.com', '555-0003', 'INACTIVE', 'EU', 'FOOD', 'Desc 3', 50.00),
    (4, 'Product A4', 'a4@test.com', '555-0004', 'ACTIVE', 'APAC', 'ELECTRONICS', 'Desc 4', 300.00),
    (5, 'Product A5', 'a5@test.com', '555-0005', 'DISCONTINUED', 'US-EAST', 'CLOTHING', 'Desc 5', 150.00),
    (6, 'Product B1', 'b1@test.com', '555-0006', 'ACTIVE', 'US-WEST', 'FOOD', 'Desc 6', 75.00),
    (7, 'Product B2', 'b2@test.com', '555-0007', 'INACTIVE', 'EU', 'HOME', 'Desc 7', 250.00),
    (8, 'Product B3', 'b3@test.com', '555-0008', 'ACTIVE', 'APAC', 'ELECTRONICS', 'Desc 8', 500.00),
    (9, 'Product B4', 'b4@test.com', '555-0009', 'ACTIVE', 'US-EAST', 'CLOTHING', 'Desc 9', 120.00),
    (10, 'Product B5', 'b5@test.com', '555-0010', 'DISCONTINUED', 'US-WEST', 'FOOD', 'Desc 10', 80.00),
    (11, 'Product C1', 'c1@test.com', '555-0011', 'ACTIVE', 'EU', 'HOME', 'Desc 11', 350.00),
    (12, 'Product C2', 'c2@test.com', '555-0012', 'INACTIVE', 'APAC', 'SPORTS', 'Desc 12', 90.00),
    (13, 'Product C3', 'c3@test.com', '555-0013', 'ACTIVE', 'US-EAST', 'ELECTRONICS', 'Desc 13', 450.00),
    (14, 'Product C4', 'c4@test.com', '555-0014', 'ACTIVE', 'US-WEST', 'CLOTHING', 'Desc 14', 175.00),
    (15, 'Product C5', 'c5@test.com', '555-0015', 'DISCONTINUED', 'EU', 'FOOD', 'Desc 15', 60.00),
    (16, 'Product D1', 'd1@test.com', '555-0016', 'ACTIVE', 'APAC', 'HOME', 'Desc 16', 280.00),
    (17, 'Product D2', 'd2@test.com', '555-0017', 'INACTIVE', 'US-EAST', 'SPORTS', 'Desc 17', 110.00),
    (18, 'Product D3', 'd3@test.com', '555-0018', 'ACTIVE', 'US-WEST', 'ELECTRONICS', 'Desc 18', 600.00),
    (19, 'Product D4', 'd4@test.com', '555-0019', 'ACTIVE', 'EU', 'CLOTHING', 'Desc 19', 130.00),
    (20, 'Product D5', 'd5@test.com', '555-0020', 'DISCONTINUED', 'APAC', 'FOOD', 'Desc 20', 45.00);

-- Small table (< 10 rows) — should skip enum detection
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    label VARCHAR NOT NULL
);
INSERT INTO tags VALUES (1, 'sale'), (2, 'new'), (3, 'featured'), (4, 'sale'), (5, 'new');
"""


class TestEnumDetection:

    @pytest_asyncio.fixture(scope="class")
    async def db_path(self, tmp_path_factory):
        import duckdb
        path = str(tmp_path_factory.mktemp("enum_test") / "test.db")
        conn = duckdb.connect(path)
        conn.execute(ENUM_TEST_SQL)
        conn.close()
        return path

    @pytest_asyncio.fixture(scope="class")
    async def generator(self, db_path):
        gen = OntologyGenerator.__new__(OntologyGenerator)
        gen._db_type = "duckdb"
        gen._url = db_path
        return gen

    @pytest_asyncio.fixture(scope="class")
    async def tables(self, db_path):
        from nexaql.ontology.generator import ColumnInfo, TableInfo
        import duckdb
        conn = duckdb.connect(db_path)

        result = []
        for table_name in ("products", "tags"):
            cols_raw = conn.execute(
                f"SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE table_name = '{table_name}' ORDER BY ordinal_position"
            ).fetchall()
            columns = []
            for col_name, col_type in cols_raw:
                columns.append(ColumnInfo(
                    name=col_name,
                    data_type=col_type,
                    is_nullable=True,
                    ordinal_position=len(columns) + 1,
                ))
            result.append(TableInfo(
                name=table_name,
                schema_name="main",
                columns=columns,
            ))
        conn.close()
        return result

    @pytest.mark.asyncio
    async def test_status_detected_as_enum(self, generator, tables):
        products_table = [t for t in tables if t.name == "products"]
        enums = await generator._detect_enums(products_table)
        assert "products" in enums
        assert "status" in enums["products"]
        assert set(enums["products"]["status"]) == {"ACTIVE", "DISCONTINUED", "INACTIVE"}

    @pytest.mark.asyncio
    async def test_region_detected_as_enum(self, generator, tables):
        products_table = [t for t in tables if t.name == "products"]
        enums = await generator._detect_enums(products_table)
        assert "region" in enums["products"]
        assert set(enums["products"]["region"]) == {"APAC", "EU", "US-EAST", "US-WEST"}

    @pytest.mark.asyncio
    async def test_category_detected_as_enum(self, generator, tables):
        products_table = [t for t in tables if t.name == "products"]
        enums = await generator._detect_enums(products_table)
        assert "category" in enums["products"]

    @pytest.mark.asyncio
    async def test_name_not_detected_as_enum(self, generator, tables):
        products_table = [t for t in tables if t.name == "products"]
        enums = await generator._detect_enums(products_table)
        assert "name" not in enums.get("products", {})

    @pytest.mark.asyncio
    async def test_email_not_detected_as_enum(self, generator, tables):
        products_table = [t for t in tables if t.name == "products"]
        enums = await generator._detect_enums(products_table)
        assert "email" not in enums.get("products", {})

    @pytest.mark.asyncio
    async def test_phone_not_detected_as_enum(self, generator, tables):
        products_table = [t for t in tables if t.name == "products"]
        enums = await generator._detect_enums(products_table)
        assert "phone" not in enums.get("products", {})

    @pytest.mark.asyncio
    async def test_description_not_detected_as_enum(self, generator, tables):
        products_table = [t for t in tables if t.name == "products"]
        enums = await generator._detect_enums(products_table)
        assert "description" not in enums.get("products", {})

    @pytest.mark.asyncio
    async def test_small_table_skipped(self, generator, tables):
        tags_table = [t for t in tables if t.name == "tags"]
        enums = await generator._detect_enums(tags_table)
        assert "tags" not in enums
