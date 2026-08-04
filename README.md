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

### Connect Your Data

NexaQL supports three ways to bring data in:

**1. Database connector** — connect to PostgreSQL, MySQL, or DuckDB:

```bash
curl -X POST localhost:3717/api/connectors \
  -H 'Content-Type: application/json' \
  -d '{"name":"mydb","type":"postgresql","connection_url":"postgresql://user:pass@localhost:5432/mydb"}'
```

**2. Spreadsheet upload** — drag-and-drop CSV, TSV, or XLSX files directly in the UI. NexaQL auto-detects headers, infers column types, and ingests into a shared DuckDB instance for querying.

**3. Cloud drive** — connect Google Drive (OneDrive and Dropbox coming soon), browse folders, and import spreadsheets directly. Files are downloaded, ingested into DuckDB, and immediately queryable via chat.

### Generate Schemas

```bash
# Generate schemas (all tables)
nexaql generate mydb --domain my_domain

# Generate schemas (specific tables only)
nexaql generate mydb --domain my_domain -t orders -t customers -t products

# Regenerate a single schema after DB changes
nexaql regenerate orders --domain my_domain
```

NexaQL introspects your database schema, detects relationships, enums, and PII fields, then generates per-table schemas with automatic edge discovery across all nodes in the domain - including cross-datasource relationships.

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

### Agent Chat
- **Natural language queries** - ask questions in plain English, get structured results with summaries
- **Two-pass architecture** - LLM extracts structured intent (JSON), deterministic builder constructs the query — small models work well
- **Date-aware** - current date context injected into prompts so "last month" and "this quarter" resolve correctly
- **Chat threads** - persistent conversation history with sidebar navigation, collapsible thread panel
- **Business ontology** - define domain-specific terms, acronyms, and SQL hints so the LLM understands your business vocabulary
- **Auto-retry** - if a generated query fails validation, the agent corrects it
- **Result summarization** - natural language summary of query results

### Data Sources
- **Database connectors** - PostgreSQL, MySQL, DuckDB with full schema introspection
- **CSV / TSV / XLSX upload** - drag-and-drop spreadsheet files with smart header detection, type inference, and data preview
- **Google Drive integration** - OAuth-based connection, folder browsing, and direct import of Google Sheets, XLSX, and CSV files from your drive
- **Cross-source joins** - data from different databases joined in memory via DuckDB
- **8 SQL dialects** - PostgreSQL, MySQL, DuckDB, Snowflake, BigQuery, Presto, Spark, MSSQL

### Agent Integration (MCP)
- **MCP server** - Model Context Protocol connector for Claude Desktop, Cursor, and any MCP-compatible AI agent
- **11 tools + 3 resources** - ask, query, validate, describe ontology, SQL preview, auth configuration, and more
- **Deterministic translation** - natural language → NexaQL → SQL, no hallucinated queries
- **Ontology-aware prompts** - the agent knows your schema, field types, and available filters
- **JWT authentication** - tamper-proof user identity for production deployments

### Admin Panel
- **Domain management** - create, switch, and delete domains from the UI
- **Schema generation** - add schemas from database connectors, CSV uploads, or cloud drive imports
- **Connector registry** - manage database connections and cloud drive OAuth credentials in one place
- **Business ontology editor** - define domain-specific terms and rules that improve query accuracy
- **Role editor** - define and manage access control roles from the UI
- **User management** - create and manage users with role assignments
- **API key management** - configure LLM provider keys (Anthropic, OpenAI, OpenRouter, Google, Meta)
- **Ontology generation** - introspect databases and auto-generate ontologies with nodes, edges, enums, and PII detection

### BYOLLM (Bring Your Own LLM)
- **No bundled LLM** - purely BYOLLM; bring Anthropic, OpenAI, OpenRouter, Google, or Meta keys
- **Auto-configure** - saving an API key automatically switches the active provider and model
- **Provider priority** - Anthropic → OpenAI → OpenRouter → Google

### Developer Experience
- **Playground UI** - Monaco editor with syntax highlighting, schema explorer, SQL preview
- **Role switcher** - test access control live in the playground
- **CLI** - `nexaql install`, `nexaql serve`, `nexaql query`, `nexaql generate`, `nexaql regenerate`, `nexaql mcp`
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

### User Context

The calling application sends user identity via the `X-User-Context` header:

```bash
curl -H 'X-User-Context: {"user_id":"alice","roles":["manager"],"region":"US-EAST","team_id":"eng-platform"}' \
     -X POST localhost:3717/api/execute \
     -d '{"query": "{ customer @limit(5) { name email } }"}'
```

Standard user context fields: `user_id`, `name`, `email`, `manager_id`, `region`, `department`, `team_id`, `level`, `job_role`, `org_id`. Custom attributes are also supported.

## MCP Server (AI Agent Integration)

NexaQL ships with a built-in [Model Context Protocol](https://modelcontextprotocol.io/) server, so any MCP-compatible AI agent (Claude Desktop, Cursor, custom agents) can query your data with full access control enforcement.

### Start the MCP Server

```bash
# stdio transport (for Claude Desktop / Cursor)
nexaql mcp

# HTTP transport (for remote agents)
nexaql mcp --transport streamable-http --port 8080
```

### Claude Desktop Configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nexaql": {
      "command": "nexaql",
      "args": ["mcp"]
    }
  }
}
```

### Tools

| Tool | Description |
|------|-------------|
| `ask` | Natural language question → NexaQL → SQL → results with summary |
| `query` | Execute a NexaQL query directly |
| `validate_query` | Parse and validate a query without executing it |
| `sql_preview` | Translate NexaQL to native SQL without executing |
| `list_domains` | List all available domains and the active domain |
| `switch_domain` | Switch the active domain |
| `describe_node` | Describe a node's fields, edges, types, and PII flags |
| `describe_ontology` | Full ontology overview — all nodes, fields, edges |
| `list_connectors` | List configured database connectors |
| `generate_schema` | Generate per-table schemas from a saved connector with edge discovery |
| `regenerate_schema` | Regenerate a single schema/node from its original connector |
| `user_context_schema` | Discover supported user context fields, roles, and RLS attributes |
| `configure_auth` | Switch between `dev` and `jwt` auth modes |

### Resources

| URI | Description |
|-----|-------------|
| `nexaql://ontology` | Full ontology as JSON |
| `nexaql://grammar` | NexaQL query syntax reference |
| `nexaql://roles` | Defined roles with permissions and field restrictions |

### Authentication

In **dev mode** (default), agents pass user identity as a raw dict:

```python
result = await ask(
    question="top customers by revenue",
    user_context={"user_id": "alice", "roles": ["analyst"], "region": "US-EAST"}
)
```

In **jwt mode** (production), agents pass a signed JWT token. This prevents impersonation — the server verifies the signature before extracting user claims:

```python
# Configure JWT mode (one-time setup)
await configure_auth(auth_mode="jwt", auth_secret="your-secret-key")

# Agents pass signed tokens
token = jwt.encode({"sub": "alice", "roles": ["analyst"]}, "your-secret-key", algorithm="HS256")
result = await ask(question="top customers", auth_token=token)
```

Access control (RBAC, field stripping, RLS, PII masking) is enforced on every query — including agent chat responses. An analyst asking "show me customer emails" gets results with the email column stripped automatically.

## Configuration

All configuration lives in the bootstrap database (`~/.nexaql/nexaql.sqlite`) and is managed through the Admin UI or API. No config files required.

```bash
# Add your LLM API key (enables agent chat)
curl -X POST localhost:3717/api/api-keys \
  -H 'Content-Type: application/json' \
  -d '{"provider":"anthropic","name":"anthropic","key":"sk-ant-..."}'

# Connect a database
curl -X POST localhost:3717/api/connectors \
  -H 'Content-Type: application/json' \
  -d '{"name":"prod","type":"postgresql","connection_url":"postgresql://..."}'
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
│   ├── chat/             # NL → NexaQL agent pipeline (intent extraction + query builder)
│   ├── cloud_drive/      # Cloud drive providers (Google Drive, OneDrive, Dropbox)
│   ├── spreadsheet/      # CSV/TSV/XLSX ingestion into shared DuckDB
│   ├── mcp_server.py     # MCP server (13 tools, 3 resources)
│   ├── auth.py           # JWT authentication & user context resolution
│   ├── bootstrap.py      # SQLite-backed state (domains, schemas, connectors, keys, cloud accounts)
│   └── cli.py            # CLI: install, serve, query, generate, regenerate, mcp
├── frontend/             # React + TypeScript + Tailwind admin panel & agent chat
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
