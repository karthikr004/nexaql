# NexaQL

**The query language built for AI agents.** One unified syntax to deterministically query, join, and aggregate data across any database - with built-in privacy enforcement.

NexaQL is not a GraphQL wrapper. It's a standalone query engine that translates natural language questions into a single, deterministic query representation, then compiles that into the native dialect of whatever database holds the data - PostgreSQL, MySQL, DuckDB, Snowflake, BigQuery, or any SQL engine. Data living across different databases? NexaQL joins it in memory. Sensitive fields? The policy engine strips or masks them before results leave the server.

```
"Which customers spent the most last quarter?"
         ↓ Agent (deterministic)
    NexaQL query
         ↓ Translator
    Native SQL dialect (PostgreSQL, MySQL, DuckDB, ...)
         ↓ Adapter
    Execute → Results
         ↓ Policy enforcer
    Stripped / masked per user role
```

## Why NexaQL?

| Problem | How NexaQL solves it |
|---------|----------------------|
| Agents generate unreliable SQL | NexaQL is a constrained, deterministic intermediate language - the agent generates NexaQL (not raw SQL), and the engine compiles it to correct, optimized SQL |
| Data scattered across databases | One query can traverse and join data from PostgreSQL, MySQL, DuckDB in a single request |
| No access control on agent queries | Built-in RBAC, field-level security, row-level security, and PII masking - enforced at the engine level, invisible to the agent |
| Schema drift breaks queries | Ontology-driven validation catches errors before execution, not after |
| Every database has different SQL | NexaQL compiles to 8 SQL dialects from one syntax |

## Quick Start

```bash
pip install nexaql
nexaql install
nexaql serve
```

Open http://localhost:3717 — a playground with sample e-commerce data loads instantly. No external database needed.

### Connect Your Own Database

```bash
# Add a PostgreSQL connector via the Admin panel or API
curl -X POST localhost:3717/api/connectors \
  -H 'Content-Type: application/json' \
  -d '{"name":"mydb","type":"postgresql","config":{"url":"postgresql://user:pass@localhost:5432/mydb"}}'

# Generate an ontology from it
curl -X POST localhost:3717/api/connectors/generate-ontology \
  -d '{"connector_name":"mydb","domain":"my_domain","output_schema_name":"main"}'
```

NexaQL introspects your database schema, detects relationships, enums, and PII fields, then generates a full ontology with default roles and access policies - ready to query.

## How It Works

### 1. Write a query (or let an agent generate one)

```
{
  order(status: "DELIVERED") @orderby(ordered_at, DESC) @limit(10) {
    id
    ordered_at
    total_amount
    customer {
      name
      email
    }
    items {
      quantity
      unit_price
      product {
        name
      }
    }
  }
}
```

This single query traverses 4 tables (`orders → customers`, `orders → order_items → products`) with automatic join resolution. No manual JOINs, no subqueries, no dialect-specific syntax.

### 2. The engine translates it

NexaQL compiles the query into the native SQL dialect of your database:

```sql
SELECT o0.id, o0.ordered_at, o0.total_amount,
       c1.name, c1.email,
       oi2.quantity, oi2.unit_price,
       p3.name
FROM orders o0
JOIN customers c1 ON c1.id = o0.customer_id
LEFT JOIN order_items oi2 ON oi2.order_id = o0.id
JOIN products p3 ON p3.id = oi2.product_id
WHERE o0.status = 'DELIVERED'
ORDER BY o0.ordered_at DESC
LIMIT 10
```

### 3. Privacy policies are enforced automatically

If the user is an `analyst`, the engine silently strips sensitive fields before translation:

```yaml
# In the ontology:
customer:
  visible_to: [analyst, manager, admin]
  fields:
    email:
      visible_to: [manager, admin]   # analysts can't see emails
      pii: true
      mask_with: email               # managers see "a***@example.com"
    lifetime_value:
      visible_to: [manager, admin]   # analysts can't see spend data
```

The analyst's query returns `name` but not `email` or `lifetime_value`. The manager sees all fields but with masked emails. The admin sees everything. **The agent doesn't need to know about access control - the engine handles it.**

## Features

> **Full grammar reference with 20+ examples**: [docs/grammar.md](docs/grammar.md)

### Query Language
- **Filters** - equality, comparison (`gt`, `lt`, `gte`, `lte`), `like`, `in`, `not_in`, null checks
- **Edge traversals** - traverse relationships across tables with automatic join resolution
- **Aggregations** - `sum()`, `avg()`, `min()`, `max()`, `count()` with automatic GROUP BY
- **Computed fields** - `calc(quantity * unit_price)` with cross-entity references
- **Directives** - `@limit`, `@offset`, `@orderby`, `@distinct`
- **Special filters** - named, reusable WHERE clauses defined in the ontology

### Privacy & Access Control
- **Node-level RBAC** - control which roles can access which tables
- **Field-level security** - strip sensitive columns based on user role
- **Row-level security (RLS)** - auto-inject WHERE clauses based on user attributes (region, department, etc.)
- **PII masking** - mask emails, phones, names in query results (5 strategies)
- **Policy-in-ontology** - access rules live alongside schema definitions

### Agent Integration
- **Deterministic translation** - natural language → NexaQL → SQL, no hallucinated queries
- **Auto-retry** - if the generated query fails validation, the agent corrects it
- **Result summarization** - agent generates a natural language summary of query results
- **Ontology-aware prompts** - the agent knows your schema, field types, and available filters

### Multi-Database
- **8 SQL dialects** - PostgreSQL, MySQL, DuckDB, Snowflake, BigQuery, Presto, Spark, MSSQL
- **Cross-source joins** - data from different databases joined in memory via DuckDB
- **Pluggable adapters** - add new databases by implementing a simple interface

### Admin Panel
- **Domain management** - create, switch, and delete domains from the UI
- **Schema management** - add schemas from connected databases, regenerate, or delete
- **Ontology generation** - introspect any connected database and auto-generate ontology with nodes, edges, enums, and PII detection
- **Duplicate prevention** - unique schema names per domain; add rejects duplicates, regenerate upserts
- **Default roles & policies** - every generated ontology bootstraps with admin/analyst/manager roles and common access functions (owns_record, same_department, same_region)
- **API Keys** - manage LLM provider keys (Anthropic, OpenAI, OpenRouter, Google); auto-detects active provider from saved keys
- **Connector registry** - add/remove PostgreSQL, MySQL, DuckDB connections

### BYOLLM (Bring Your Own LLM)
- **No bundled LLM** - purely BYOLLM; bring Anthropic, OpenAI, OpenRouter, or Google keys
- **Auto-configure** - saving an API key automatically switches the active provider and model
- **Provider priority** - Anthropic → OpenAI → OpenRouter → Google

### Developer Experience
- **Playground UI** - Monaco editor with syntax highlighting, schema explorer, SQL preview
- **Role switcher** - test access control live in the playground
- **CLI** - `nexaql install`, `nexaql serve`, `nexaql query`
- **Zero config** - ships with sample data, works after `nexaql install`

## Query Syntax Reference

### Filters

```graphql
# Equality
order(status: "DELIVERED")

# Comparison operators (object style)
order(total_amount: { gt: 100, lt: 1000 })

# Suffix shorthand
order(total_amount_gt: 100)

# Special filters (defined in ontology)
order(large_order: 500)

# Calc filters - computed conditions across entities
order_item(calc(quantity * unit_price): { gt: 500 })
```

### Edge Traversals

```graphql
{
  customer {
    name
    orders {          # edge → order table (auto-joined)
      total_amount
      items {         # edge → order_item table
        quantity
        product {     # edge → product table
          name
          price
        }
      }
    }
  }
}
```

### Aggregations & Computed Fields

```graphql
{
  order {
    customer_id
    total_orders: count()
    total_revenue: sum(total_amount)
    avg_order: avg(total_amount)
  }
}

{
  order_item {
    quantity
    unit_price
    line_total: calc(quantity * unit_price)
  }
}
```

## Access Control

NexaQL enforces privacy at the query engine level - RBAC, field-level security, row-level security, and PII masking.

> **Full access control guide**: [docs/access-control.md](docs/access-control.md)

### Role Registry

Define valid roles in the ontology. All access policies validate against this list:

```yaml
roles:
  admin:
    description: "Full access to all data"
  manager:
    description: "Regional data access with all fields"
  analyst:
    description: "Read access without PII or financial data"
```

### Policy Functions

Reusable, named access policies for row-level security:

```yaml
access_functions:
  same_team:
    description: "Records created by users on the same team"
    sql: "{field} IN (SELECT user_id FROM employees WHERE team_id = '{user.team_id}')"
    requires: ["user.team_id"]

nodes:
  customer:
    visible_to: [analyst, manager, admin]
    row_policies:
      - function: same_team       # reference a named policy function
        field: created_by          # which column it applies to
        roles: [manager]
        except_roles: [admin]
    fields:
      email:
        visible_to: [manager, admin]
        pii: true
        mask_with: email
```

### Admin UI

Click the ⚙ gear icon in the playground header to manage:
- **Domains & Schemas** - organize ontologies by domain, add/delete schemas, switch active domain
- **Connectors** - connect databases and generate ontologies from them
- **API Keys** - configure LLM provider credentials
- **Roles** - define valid role names
- **Policy Functions** - create reusable access policies
- **Per-node access** - visible_to, row policies, field-level PII/masking

### User Context

The calling application sends user identity via the `X-User-Context` header:

```bash
curl -H 'X-User-Context: {"user_id":"alice","roles":["manager"],"region":"US-EAST","team_id":"eng-platform"}' \
     -X POST localhost:3717/api/execute \
     -d '{"query": "{ customer @limit(5) { name email } }"}'
```

Standard user context fields: `user_id`, `name`, `email`, `manager_id`, `region`, `department`, `team_id`, `level`, `job_role`, `org_id`. Custom attributes are also supported.

## Configuration

All configuration lives in the bootstrap database (`~/.nexaql/nexaql.db`) and is managed through the Admin UI or API. No config files required.

```bash
# Add your LLM API key (enables agent chat)
curl -X POST localhost:3717/api/api-keys \
  -H 'Content-Type: application/json' \
  -d '{"provider":"anthropic","name":"anthropic","key":"sk-ant-..."}'

# Connect a database
curl -X POST localhost:3717/api/connectors \
  -H 'Content-Type: application/json' \
  -d '{"name":"prod","type":"postgresql","config":{"url":"postgresql://..."}}'
```

For advanced/legacy setups, a `nexaql.yaml` config file is also supported:

```yaml
ontology:
  path: ./ontologies/my_schema.yaml

datasources:
  default:
    type: duckdb
    path: ":memory:"
    seed_file: ./ontologies/sample_seed.sql

server:
  host: 0.0.0.0
  port: 3717
```

## Ontology

The ontology is the single source of truth for your data graph. It defines what NexaQL can query, how tables relate, and who can see what:

```yaml
version: "1"
domain: ecommerce

nodes:
  customer:
    table: customers
    primary_key: id
    visible_to: [analyst, manager, admin]
    fields:
      id:   { type: integer, filterable: true }
      name: { type: string,  filterable: true }
      email: { type: string, filterable: true, visible_to: [manager, admin], pii: true, mask_with: email }
    edges:
      orders:
        node: order
        join_steps:
          - table: orders
            alias_key: order
            condition: "{order}.customer_id = {customer}.id"
    special_filters:
      active:
        sql: "{customer}.status = 'ACTIVE'"
```

## Architecture

```
                    ┌─────────────┐
  Natural Language  │  Agent Chat │  "Which customers spent the most?"
                    └──────┬──────┘
                           ↓
                    ┌─────────────┐
  NexaQL Query     │   Parser    │  { customer @limit(10) { name, total: sum(amount) } }
                    └──────┬──────┘
                           ↓
                    ┌─────────────┐
  Access Control    │  Enforcer   │  Strip fields, inject RLS, flag PII masking
                    └──────┬──────┘
                           ↓
                    ┌─────────────┐
  Validation        │  Validator  │  Check against ontology schema
                    └──────┬──────┘
                           ↓
                    ┌─────────────┐
  Native SQL        │ Translator  │  SELECT ... FROM ... JOIN ... WHERE ...
                    └──────┬──────┘
                           ↓
                    ┌─────────────┐
  Execution         │  Adapter    │  PostgreSQL / MySQL / DuckDB / ...
                    └──────┬──────┘
                           ↓
                    ┌─────────────┐
  Post-processing   │   Masker    │  PII masking on result rows
                    └─────────────┘
```

```
nexaql/
├── src/nexaql/
│   ├── engine/           # Pure query engine (zero external deps)
│   │   ├── lexer.py      # Tokenizer
│   │   ├── parser.py     # Recursive descent parser → AST
│   │   ├── validator.py  # AST validation against ontology
│   │   ├── translator.py # AST → SQL with join resolution
│   │   └── dialect.py    # 8 SQL dialect translators
│   ├── policy/           # RBAC, field security, RLS, PII masking
│   ├── ontology/         # YAML schema + access policy loader
│   ├── adapters/         # PostgreSQL, DuckDB (+ pluggable base)
│   ├── api/              # FastAPI server + admin panel routes
│   ├── chat/             # NL → NexaQL agent pipeline
│   ├── bootstrap.py      # DuckDB-backed state (domains, schemas, connectors, keys)
│   └── cli.py            # CLI: install, serve, query
├── frontend/             # React + Tailwind admin panel & playground
└── ontologies/           # Sample schema + seed data
```

## Development

```bash
git clone https://github.com/karthikr004/nexaql
cd nexaql
pip install -e ".[dev]"
nexaql serve --reload
```

## License

Apache 2.0
