# NexaQL Access Control Guide

NexaQL enforces privacy at the query engine level. Access policies are defined in the ontology and enforced automatically — the querying agent or user never sees restricted data.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Roles](#roles)
- [Node-Level Access](#node-level-access)
- [Field-Level Access](#field-level-access)
- [Row-Level Security (RLS)](#row-level-security-rls)
- [Policy Functions](#policy-functions)
- [PII Masking](#pii-masking)
- [User Context](#user-context)
- [Admin UI](#admin-ui)
- [Testing Access Policies](#testing-access-policies)

---

## How It Works

```
Query → Parse → 🔒 ENFORCE POLICIES → Validate → Translate → Execute → 🔒 MASK RESULTS
                        ↑                                                      ↑
                   UserContext                                           PII masking
```

The policy enforcer sits between the parser and validator. It:
1. Checks if the user's role can access the queried node
2. Injects row-level security filters into the query
3. Strips fields the user can't see
4. Flags PII fields for post-query masking

All of this is invisible to the user — they write a normal query and get back only what they're allowed to see.

---

## Roles

Roles are the foundation of access control. Define them in the ontology:

```yaml
roles:
  admin:
    description: "Full access to all data and schemas"
  manager:
    description: "Regional data access with all fields visible"
  analyst:
    description: "Read access without PII or financial data"
  viewer:
    description: "Limited read-only access"
```

**Key points:**
- NexaQL has **no predefined roles** — you define whatever roles make sense for your organization
- All `visible_to` and `row_policies.roles` references are validated against this list
- Attempting to use an undefined role (e.g., typo) is rejected on save
- Role-to-user mapping is managed by your auth system, not NexaQL

### Managing Roles

In the Admin UI (⚙ gear icon → Roles):
- Add, rename, or delete roles
- Each role has a name and description
- Changes are saved to the ontology YAML

---

## Node-Level Access

Control which roles can query a node (table):

```yaml
nodes:
  customer:
    visible_to: [analyst, manager, admin]    # anonymous users → denied
```

- If `visible_to` is not set → all roles can access the node
- If set → only listed roles can query it
- Denied users get a clear error: *"Access denied: node 'customer' requires role 'analyst', 'manager', or 'admin'"*

---

## Field-Level Access

Control which roles can see specific fields:

```yaml
nodes:
  customer:
    fields:
      name:
        type: string
        # No visible_to → all roles can see this field
      email:
        type: string
        visible_to: [manager, admin]         # analysts can't see emails
      lifetime_value:
        type: numeric
        visible_to: [manager, admin]         # analysts can't see spend data
```

- Fields without `visible_to` are visible to all roles that can access the node
- Hidden fields are silently stripped from the query — the user doesn't see an error, the column simply doesn't appear in results
- The SQL Preview shows the stripped query so you can see what actually executes

---

## Row-Level Security (RLS)

Filter rows based on user attributes. Two modes:

### Function Reference (recommended)

Reference a named policy function:

```yaml
nodes:
  customer:
    row_policies:
      - function: region_match       # name of an access_function
        field: region                # which column it applies to
        roles: [manager]             # which roles this policy applies to
        except_roles: [admin]        # exempt roles (admin sees all rows)
```

### Raw SQL Condition

For one-off conditions:

```yaml
nodes:
  order:
    row_policies:
      - condition: "status != 'CANCELLED'"
        roles: [viewer]
```

### How RLS works

1. When a user with a matching role queries the node, the condition is injected as a WHERE clause
2. The user never sees the injected condition — it's invisible in their query
3. `except_roles` allows specific roles to bypass the filter (e.g., admin sees all rows)
4. Multiple policies can apply to the same node — they stack as AND conditions

---

## Policy Functions

Reusable, named access policies defined at the ontology level:

```yaml
access_functions:
  self_only:
    description: "Only records created by the current user"
    sql: "{field} = '{user.user_id}'"
    requires: ["user.user_id"]

  same_team:
    description: "Records created by users on the same team"
    sql: "{field} IN (SELECT user_id FROM employees WHERE team_id = '{user.team_id}')"
    requires: ["user.team_id"]

  same_manager:
    description: "Records created by users reporting to the same manager"
    sql: "{field} IN (SELECT user_id FROM employees WHERE manager_id = '{user.manager_id}')"
    requires: ["user.manager_id"]

  direct_reports:
    description: "Records created by the user's direct reports"
    sql: "{field} IN (SELECT user_id FROM employees WHERE manager_id = '{user.user_id}')"
    requires: ["user.user_id"]

  region_match:
    description: "Records where region matches the user's region"
    sql: "{field} = '{user.region}'"
    requires: ["user.region"]

  department_match:
    description: "Records created by users in the same department"
    sql: "{field} IN (SELECT user_id FROM employees WHERE department = '{user.department}')"
    requires: ["user.department"]
```

### Placeholders

- `{field}` — replaced with the column name specified in the row policy
- `{user.xxx}` — replaced with the corresponding value from the user context
- String values are SQL-escaped; numeric values are not quoted

### Why use policy functions?

- **Reusable** — define once, use on any node
- **Validated** — the Admin UI validates field names and tests execution
- **Documented** — `description` and `requires` make policies self-documenting
- **Less error-prone** — no raw SQL to fat-finger

---

## PII Masking

Mark fields as PII and define masking strategies:

```yaml
fields:
  email:
    type: string
    pii: true
    mask_with: email           # alice@example.com → a***@example.com
  phone:
    type: string
    pii: true
    mask_with: phone           # +1-555-0101 → +1***101
```

### Masking Strategies

| Strategy | Input | Output |
|----------|-------|--------|
| `email` | alice@example.com | a***@example.com |
| `phone` | +1-555-0101 | +1***101 |
| `redact` | any value | [REDACTED] |
| `hash` | any value | a1b2c3d4 (first 8 chars of SHA-256) |
| `truncate` | Alice Johnson | Ali*** |

### When masking applies

- PII masking applies when the user has access to the field (`visible_to` matches) but the field is marked as PII
- If the user has direct `visible_to` access to a PII field (e.g., admin with `visible_to: [admin]`), they see **unmasked** data
- If `visible_to` is not set (all roles can see), PII masking applies to everyone except `*` (superadmin)

---

## User Context

NexaQL expects user identity via the `X-User-Context` HTTP header:

```json
{
  "user_id": "alice",
  "roles": ["manager"],
  "name": "Alice Johnson",
  "email": "alice@company.com",
  "manager_id": "mgr-east",
  "region": "US-EAST",
  "department": "Engineering",
  "team_id": "eng-platform",
  "level": "L6",
  "job_role": "Engineering Manager"
}
```

### Canonical Fields

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string or int | Unique user identifier (required) |
| `roles` | string[] | User's roles (required) |
| `name` | string | Display name |
| `email` | string | Email address |
| `manager_id` | string or int | User's manager ID |
| `region` | string | Geographic region |
| `department` | string | Department name |
| `team_id` | string or int | Team identifier |
| `level` | string | Seniority level |
| `job_role` | string | Job title/role |
| `org_id` | string or int | Organization ID |

Numeric values (int/float) are not quoted in SQL. String values are escaped.

### Custom Attributes

Any additional fields in the JSON are available as custom attributes:

```json
{
  "user_id": "alice",
  "roles": ["manager"],
  "cost_center": "CC-1234",
  "clearance_level": 3
}
```

Referenced in policies as `{user.cost_center}` and `{user.clearance_level}`.

### Who sends the user context?

Your application or API gateway. NexaQL does not manage authentication or role-to-user mapping. The typical flow:

```
User → Your Auth System → Resolves roles → Sends X-User-Context → NexaQL
```

In dev mode (no header), NexaQL defaults to anonymous with no roles. The playground's Role Switcher sends test contexts for development.

---

## Admin UI

Click the ⚙ gear icon in the playground header to open the full-page admin view.

### Sections

- **Roles** — Define valid role names and descriptions
- **Policy Functions** — Create reusable access policy templates
- **Schema nodes** — Edit per-node access (visible_to, row policies, field PII/masking)

### Validation

The admin validates before saving:

**Client-side checks:**
- Required fields (primary_key, description, field types)
- Row policy field names exist on the node
- Access function SQL includes `{field}` placeholder

**Server-side checks:**
- Pydantic schema validation
- Role reference validation — all `visible_to` and `row_policies.roles` must use roles defined in the `roles:` section

### Test Policy

Each row policy has a "Test Policy" button that:
1. Resolves `{user.xxx}` placeholders with sample values
2. Validates the field exists on the node
3. Shows the resolved SQL condition

---

## Testing Access Policies

### In the Playground

Use the **Role** dropdown in the header to switch between roles and see access control in action:

| Role | Behavior |
|------|----------|
| Anonymous | No roles — strictest access, many nodes/fields denied |
| Analyst (bob) | Can query most nodes, PII and amounts hidden |
| Manager (alice, US-EAST) | All fields visible, only US-EAST rows |
| Manager (carol, US-WEST) | All fields visible, only US-WEST rows |
| Admin | Full access, no restrictions |

### Via API

```bash
# Anonymous — no header
curl -X POST localhost:3717/api/execute \
  -d '{"query": "{ customer @limit(3) { name email } }"}'

# Analyst — email stripped
curl -H 'X-User-Context: {"user_id":"bob","roles":["analyst"]}' \
  -X POST localhost:3717/api/execute \
  -d '{"query": "{ customer @limit(3) { name email } }"}'

# Manager — region-filtered
curl -H 'X-User-Context: {"user_id":"alice","roles":["manager"],"region":"US-EAST"}' \
  -X POST localhost:3717/api/execute \
  -d '{"query": "{ customer @limit(3) { name email region } }"}'
```

### Via CLI

```bash
# The CLI doesn't send user context by default (anonymous)
nexaql query '{ product @limit(5) { name price } }'
```

---

## Example: Complete Access Policy

```yaml
roles:
  admin:
    description: "Full access"
  manager:
    description: "Regional access"
  analyst:
    description: "No PII or amounts"

access_functions:
  region_match:
    description: "Records matching user's region"
    sql: "{field} = '{user.region}'"
    requires: ["user.region"]
  self_only:
    description: "Only user's own records"
    sql: "{field} = '{user.user_id}'"
    requires: ["user.user_id"]

nodes:
  customer:
    visible_to: [analyst, manager, admin]
    row_policies:
      - function: region_match
        field: region
        roles: [manager]
        except_roles: [admin]
    fields:
      id:     { type: integer, filterable: true }
      name:   { type: string, filterable: true }
      email:  { type: string, visible_to: [manager, admin], pii: true, mask_with: email }
      region: { type: string, filterable: true }
      lifetime_value: { type: numeric, visible_to: [manager, admin] }
```

**Result by role:**

| Query: `customer { name email region lifetime_value }` | Anonymous | Analyst | Manager (US-EAST) | Admin |
|---|---|---|---|---|
| Node access | ❌ Denied | ✅ | ✅ | ✅ |
| name | — | ✅ | ✅ | ✅ |
| email | — | ❌ stripped | ✅ unmasked | ✅ unmasked |
| region | — | ✅ | ✅ | ✅ |
| lifetime_value | — | ❌ stripped | ✅ | ✅ |
| Rows | — | All | US-EAST only | All |
