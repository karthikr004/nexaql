# NexaQL Grammar Reference

NexaQL is a structured query language designed for AI agents to deterministically query, join, and aggregate data across any database. It uses a familiar graph-traversal syntax that compiles to native SQL.

---

## Table of Contents

- [Query Structure](#query-structure)
- [Nodes](#nodes)
- [Fields](#fields)
- [Filters](#filters)
- [Edge Traversals](#edge-traversals)
- [Aggregations](#aggregations)
- [Computed Fields (calc)](#computed-fields-calc)
- [Directives](#directives)
- [Combining Features](#combining-features)
- [Formal Grammar (EBNF)](#formal-grammar-ebnf)

---

## Query Structure

Every NexaQL query has this shape:

```
query OptionalName {
  node(filters) @directives {
    field
    field
    edge { ... }
  }
}
```

The outer `query Name` wrapper is optional:

```graphql
# Named query
query RecentOrders {
  order @limit(10) { id ordered_at }
}

# Anonymous query (also valid)
{
  order @limit(10) { id ordered_at }
}
```

A query always starts with a **root node** — the primary table you're querying.

---

## Nodes

A node corresponds to a table or entity defined in the ontology. The root node determines the FROM clause in SQL.

```graphql
{
  customer {         # → FROM customers
    name
    email
  }
}
```

```graphql
{
  product {          # → FROM products
    name
    price
  }
}
```

Only nodes defined in the ontology can be queried. The engine validates the node name at parse time.

---

## Fields

Fields are the columns you want to SELECT. They must be defined in the ontology for the current node.

```graphql
{
  order {
    id               # scalar field
    status           # enum field
    ordered_at       # date field
    total_amount     # numeric field
  }
}
```

### Aliased Fields

Give a field a custom name in the output:

```graphql
{
  customer {
    customer_name: name        # output column will be "customer_name"
    signup_date: created_at
  }
}
```

---

## Filters

Filters restrict which rows are returned. They appear in parentheses after the node name.

### Equality

```graphql
{
  order(status: "DELIVERED") {
    id
    total_amount
  }
}
```

```sql
-- Compiles to:
SELECT ... FROM orders o0 WHERE o0.status = 'DELIVERED'
```

### Comparison Operators (Object Style)

Use `{ operator: value }` syntax for comparisons:

```graphql
{
  order(total_amount: { gt: 100, lt: 1000 }) {
    id
    total_amount
  }
}
```

Available operators:

| Operator | Meaning | Example |
|----------|---------|---------|
| `eq` | Equal | `field: { eq: 5 }` |
| `ne` | Not equal | `field: { ne: 0 }` |
| `gt` | Greater than | `field: { gt: 100 }` |
| `gte` | Greater or equal | `field: { gte: 100 }` |
| `lt` | Less than | `field: { lt: 1000 }` |
| `lte` | Less or equal | `field: { lte: 1000 }` |
| `like` | Pattern match (ILIKE) | `field: { like: "%smith%" }` |
| `in` | In list | `field: { in: ["A", "B"] }` |
| `not_in` | Not in list | `field: { not_in: ["X"] }` |
| `null` | Is null / not null | `field: { null: true }` |

### Suffix Shorthand

For simple comparisons, append the operator as a suffix:

```graphql
{
  order(total_amount_gt: 100, total_amount_lt: 1000) {
    id
    total_amount
  }
}
```

Suffix equivalents: `_gt`, `_gte`, `_lt`, `_lte`, `_eq`, `_ne`, `_like`, `_in`, `_not_in`, `_null`.

### Multiple Filters

Combine multiple filters (AND logic):

```graphql
{
  order(status: "DELIVERED", total_amount_gt: 500, ordered_at: { gte: "2024-01-01" }) {
    id
    ordered_at
    total_amount
  }
}
```

### String Filters

```graphql
{
  customer(name: { like: "%smith%" }) {
    name
    email
  }
}
```

```graphql
{
  product(name: { like: "iPhone%" }) {
    name
    price
  }
}
```

### Enum Filters

```graphql
{
  order(status: "DELIVERED") { ... }
  order(status: { in: ["DELIVERED", "SHIPPED"] }) { ... }
  order(status: { not_in: ["CANCELLED"] }) { ... }
}
```

### Null Checks

```graphql
{
  order(shipped_at: { null: true }) {      # WHERE shipped_at IS NULL
    id
    status
  }
}

{
  order(shipped_at: { null: false }) {     # WHERE shipped_at IS NOT NULL
    id
    shipped_at
  }
}
```

### Special Filters

Special filters are named, reusable conditions defined in the ontology:

```graphql
# Ontology definition:
#   special_filters:
#     large_order:
#       type: integer
#       sql: "{order}.total_amount > {value}"

{
  order(large_order: 500) {        # WHERE total_amount > 500
    id
    total_amount
  }
}
```

```graphql
# Boolean special filter:
#   active:
#     sql: "{customer}.status = 'ACTIVE'"

{
  customer(active: true) {
    name
    email
  }
}
```

---

## Edge Traversals

Edges define relationships between nodes (foreign key joins). Traverse them by nesting a child node inside the parent:

```graphql
{
  order {
    id
    total_amount
    customer {              # edge: order → customer (auto-joined)
      name
      email
    }
  }
}
```

```sql
-- Compiles to:
SELECT o0.id, o0.total_amount, c1.name, c1.email
FROM orders o0
JOIN customers c1 ON c1.id = o0.customer_id
```

### Multi-Level Traversals

Chain edges to traverse multiple levels:

```graphql
{
  customer {
    name
    orders {                  # customer → order
      ordered_at
      total_amount
      items {                 # order → order_item
        quantity
        unit_price
        product {             # order_item → product
          name
          sku
          category {          # product → category
            name
          }
        }
      }
    }
  }
}
```

This generates JOINs across 5 tables in a single query.

### Filters on Edges

Apply filters at any level of the traversal:

```graphql
{
  customer(status: "ACTIVE") {
    name
    orders(status: "DELIVERED", total_amount_gt: 100) {
      ordered_at
      total_amount
      items(quantity_gt: 1) {
        quantity
        unit_price
        product(is_active: true) {
          name
          price
        }
      }
    }
  }
}
```

### Directives on Edges

```graphql
{
  customer {
    name
    orders @orderby(ordered_at, DESC) @limit(5) {
      ordered_at
      total_amount
    }
  }
}
```

---

## Aggregations

Aggregation functions compute summaries across rows. When used, non-aggregated fields become GROUP BY columns automatically.

### Available Functions

| Function | Description | Example |
|----------|-------------|---------|
| `count()` | Count rows | `total: count()` |
| `sum(field)` | Sum values | `revenue: sum(total_amount)` |
| `avg(field)` | Average | `avg_order: avg(total_amount)` |
| `min(field)` | Minimum | `earliest: min(ordered_at)` |
| `max(field)` | Maximum | `latest: max(ordered_at)` |

### Basic Aggregation

```graphql
{
  order {
    total_orders: count()
    total_revenue: sum(total_amount)
    avg_order: avg(total_amount)
    largest_order: max(total_amount)
  }
}
```

```sql
-- Compiles to:
SELECT COUNT(*) AS total_orders,
       SUM(o0.total_amount) AS total_revenue,
       AVG(o0.total_amount) AS avg_order,
       MAX(o0.total_amount) AS largest_order
FROM orders o0
```

### Group By (Automatic)

Mix scalar fields with aggregations — scalar fields become GROUP BY:

```graphql
{
  order {
    status                          # ← automatic GROUP BY
    order_count: count()
    total_revenue: sum(total_amount)
  }
}
```

```sql
SELECT o0.status, COUNT(*) AS order_count, SUM(o0.total_amount) AS total_revenue
FROM orders o0
GROUP BY o0.status
```

### Aggregation with Filters

```graphql
{
  order(status: { in: ["DELIVERED", "SHIPPED"] }) {
    status
    order_count: count()
    total_revenue: sum(total_amount)
  }
}
```

### Aggregation on Edges

Aggregate data from a joined table:

```graphql
{
  order_item {
    product_id                       # GROUP BY product_id
    items_sold: count()
    total_revenue: sum(unit_price)
    avg_price: avg(unit_price)
  }
}
```

### Aggregation with Ordering

```graphql
{
  order_item @orderby(total_revenue, DESC) @limit(10) {
    product_id
    total_revenue: sum(unit_price)
    items_sold: count()
  }
}
```

---

## Computed Fields (calc)

`calc()` creates computed columns using SQL expressions. Field names in the expression are automatically qualified with table aliases.

### Basic Calculations

```graphql
{
  order_item {
    quantity
    unit_price
    line_total: calc(quantity * unit_price)
  }
}
```

```sql
SELECT oi0.quantity, oi0.unit_price, oi0.quantity * oi0.unit_price AS line_total
FROM order_items oi0
```

### Arithmetic Operators

```graphql
{
  order_item {
    unit_price
    discounted: calc(unit_price * 0.9)             # 10% discount
    with_tax: calc(unit_price * 1.08)              # 8% tax
    margin: calc(unit_price - 10)                  # fixed cost subtracted
  }
}
```

### SQL Functions in calc

```graphql
{
  order {
    ordered_at
    days_ago: calc(CURRENT_DATE - ordered_at)       # date arithmetic
    year: calc(EXTRACT(YEAR FROM ordered_at))       # extract year
    month: calc(EXTRACT(MONTH FROM ordered_at))     # extract month
  }
}
```

Supported functions: `EXTRACT`, `DATE_TRUNC`, `DATE_PART`, `AGE`, `ROUND`, `CEIL`, `FLOOR`, `ABS`, `GREATEST`, `LEAST`, `COALESCE`, `NULLIF`, `TO_DATE`, `NOW`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`.

### Cross-Entity calc (Dot Notation)

Reference fields from related entities using `edge_name.field_name`:

```graphql
{
  order_item {
    quantity
    unit_price
    price_diff: calc(unit_price - product.price)     # compare invoice vs catalog price
    product {
      name
      price
    }
  }
}
```

The engine auto-joins the `product` table and resolves `product.price` to the correct alias. This works for any edge defined in the ontology.

### calc in Filters

Use `calc()` as a filter condition — filter by computed values:

```graphql
# Find line items where extended price exceeds $500
{
  order_item(calc(quantity * unit_price): { gt: 500 }) {
    quantity
    unit_price
    line_total: calc(quantity * unit_price)
    product {
      name
    }
  }
}
```

```sql
SELECT oi0.quantity, oi0.unit_price, oi0.quantity * oi0.unit_price AS line_total, p1.name
FROM order_items oi0
JOIN products p1 ON p1.id = oi0.product_id
WHERE (oi0.quantity * oi0.unit_price) > 500
```

### calc Filter with Comparison Object

```graphql
{
  order_item(calc(quantity * unit_price): { gte: 100, lte: 1000 }) {
    quantity
    unit_price
    line_total: calc(quantity * unit_price)
  }
}
```

### calc Filter with Cross-Entity Reference

```graphql
# Find items where the invoice price exceeds the catalog price
{
  order_item(calc(unit_price - product.price): { gt: 0 }) {
    unit_price
    overcharge: calc(unit_price - product.price)
    product {
      name
      price
    }
  }
}
```

---

## Directives

Directives modify query behavior. They appear after the node name (and filters) prefixed with `@`.

### @limit

Restrict the number of rows returned:

```graphql
{
  order @limit(10) {
    id
    total_amount
  }
}
```

### @offset

Skip rows (for pagination):

```graphql
{
  order @limit(10) @offset(20) {     # page 3 (10 per page)
    id
    total_amount
  }
}
```

### @orderby

Sort results:

```graphql
{
  order @orderby(ordered_at, DESC) {
    id
    ordered_at
    total_amount
  }
}
```

```graphql
# ASC is the default if direction is omitted
{
  customer @orderby(name, ASC) {
    name
    email
  }
}
```

### @distinct

Remove duplicate rows:

```graphql
{
  order @distinct {
    status
  }
}
```

### Combining Directives

```graphql
{
  order @orderby(total_amount, DESC) @limit(25) @offset(0) {
    id
    ordered_at
    total_amount
  }
}
```

---

## Combining Features

### Full Example: Sales Report

```graphql
query SalesReport {
  order(status: "DELIVERED", ordered_at: { gte: "2024-01-01" })
    @orderby(total_amount, DESC)
    @limit(100) {
    id
    ordered_at
    total_amount
    customer {
      name
      region
    }
    items {
      quantity
      unit_price
      line_total: calc(quantity * unit_price)
      product {
        name
        sku
        category {
          name
        }
      }
    }
  }
}
```

### Full Example: Revenue by Category

```graphql
query RevenueByCategory {
  order_item @orderby(total_revenue, DESC) {
    product_id
    total_revenue: sum(unit_price)
    items_sold: count()
    avg_unit_price: avg(unit_price)
  }
}
```

### Full Example: Customer Lifetime Value

```graphql
query TopCustomers {
  customer(status: "ACTIVE")
    @orderby(lifetime_value, DESC)
    @limit(20) {
    name
    email
    region
    lifetime_value
    orders {
      id
      ordered_at
      total_amount
    }
  }
}
```

### Full Example: High-Value Overpriced Items

```graphql
query OverpricedItems {
  order_item(
    calc(quantity * unit_price): { gt: 500 }
    calc(unit_price - product.price): { gt: 0 }
  ) {
    quantity
    unit_price
    line_total: calc(quantity * unit_price)
    overcharge: calc(unit_price - product.price)
    order {
      id
      ordered_at
      customer {
        name
      }
    }
    product {
      name
      price
    }
  }
}
```

### Full Example: Monthly Order Trends

```graphql
query MonthlyTrends {
  order(ordered_at: { gte: "2024-01-01" }) @orderby(month, ASC) {
    month: calc(EXTRACT(MONTH FROM ordered_at))
    order_count: count()
    total_revenue: sum(total_amount)
    avg_order_value: avg(total_amount)
  }
}
```

---

## Formal Grammar (EBNF)

```ebnf
Query        = [ "query" Identifier ] "{" NodeSelection "}"
NodeSelection = Identifier [ "(" FilterList ")" ] Directives "{" FieldList "}"

FieldList    = { Field "," }
Field        = ScalarField | AliasedField | CalcField | AggField | EdgeField
ScalarField  = Identifier
AliasedField = Identifier ":" Identifier
CalcField    = Identifier ":" "calc" "(" Expression ")"
AggField     = Identifier ":" AggFunc "(" [ Identifier | "*" ] ")"
EdgeField    = NodeSelection

AggFunc      = "sum" | "avg" | "min" | "max" | "count"

FilterList   = { Filter "," }
Filter       = Identifier ":" Value
             | Identifier ":" "{" ObjectFilter "}"
             | "calc" "(" Expression ")" ":" Value
             | "calc" "(" Expression ")" ":" "{" ObjectFilter "}"
ObjectFilter = { Operator ":" Value "," }
Operator     = "eq" | "ne" | "gt" | "gte" | "lt" | "lte"
             | "like" | "in" | "not_in" | "null"

Directives   = { "@" DirectiveName [ "(" DirectiveArgs ")" ] }
DirectiveName = "limit" | "offset" | "orderby" | "distinct"
DirectiveArgs = Value { "," Value }

Expression   = Term { ("+" | "-" | "*" | "/") Term }
Term         = Identifier [ "." Identifier ]     (* cross-entity ref *)
             | Number | String | FunctionCall | "(" Expression ")"
FunctionCall = Identifier "(" [ ArgList ] ")"
ArgList      = Expression { "," Expression }

Value        = String | Integer | Float | Boolean | Null | Array
Array        = "[" { Value "," } "]"
Identifier   = [a-zA-Z_][a-zA-Z0-9_]*
String       = '"' ... '"' | "'" ... "'"
Integer      = [-]?[0-9]+
Float        = [-]?[0-9]+"."[0-9]+
Boolean      = "true" | "false"
Null         = "null"
```

---

## Token Types

NexaQL has 23 token types:

| Token | Symbol | Example |
|-------|--------|---------|
| IDENT | identifier | `order`, `name`, `total_amount` |
| KEYWORD | `query` | `query MyQuery { ... }` |
| INT | integer | `42`, `-1` |
| FLOAT | decimal | `3.14`, `-0.5` |
| STRING | quoted | `"hello"`, `'world'` |
| BOOL | boolean | `true`, `false` |
| NULL | null | `null` |
| LBRACE | `{` | |
| RBRACE | `}` | |
| LPAREN | `(` | |
| RPAREN | `)` | |
| LBRACKET | `[` | |
| RBRACKET | `]` | |
| COLON | `:` | |
| COMMA | `,` | |
| AT | `@` | |
| DOT | `.` | `product.price` |
| PLUS | `+` | `calc(a + b)` |
| MINUS | `-` | `calc(a - b)` |
| STAR | `*` | `calc(a * b)`, `count(*)` |
| SLASH | `/` | `calc(a / b)` |
| EOF | end of input | |

---

## Comments

```graphql
# This is a line comment
// This is also a line comment

{
  order {
    id           # inline comment
    total_amount // another inline comment
  }
}
```
