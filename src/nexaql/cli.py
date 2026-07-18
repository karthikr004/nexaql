# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL command-line interface.

Core commands:

- ``nexaql serve``      -- start the FastAPI server
- ``nexaql init``       -- create an ``nexaql.yaml`` template
- ``nexaql query``      -- run a query from the command line
- ``nexaql generate``   -- generate per-table schemas from a saved connector
- ``nexaql regenerate`` -- regenerate a single schema/node
- ``nexaql mcp``        -- start the MCP server for AI agents
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
from importlib import resources
from typing import Optional

import click

# ── Template ────────────────────────────────────────────────────────────────

INIT_TEMPLATE = """\
# NexaQL configuration
# See https://github.com/karthikr004/nexaql for documentation.

ontology:
  path: ./ontologies/sample_ecommerce.yaml

datasources:
  # Quick start: in-memory DuckDB with sample e-commerce data.
  # No external database needed — just run `nexaql serve` and start querying.
  default:
    type: duckdb
    path: ":memory:"
    seed_file: ./ontologies/sample_ecommerce_seed.sql

  # To use your own PostgreSQL database instead, uncomment below:
  # default:
  #   type: postgresql
  #   url: postgresql://user:pass@localhost:5432/mydb

llm:
  # Configure your LLM provider. NexaQL works with any OpenAI-compatible API.
  # See nexaql.yaml.example for all options.
  provider: ""     # Set to: ollama, openrouter, or openai
  model: ""        # Set to your chosen model
  max_tokens: 4096
  summary_max_tokens: 2048

server:
  host: 0.0.0.0
  port: 3717
  cors_origins:
    - "*"
"""


# ── CLI group ───────────────────────────────────────────────────────────────


@click.group()
@click.version_option(package_name="nexaql")
def main() -> None:
    """NexaQL -- a GraphQL-inspired query language for any structured data."""
    pass


# ── nexaql serve ───────────────────────────────────────────────────────────


@main.command()
@click.option("--host", default=None, help="Bind host (overrides config)")
@click.option("--port", default=None, type=int, help="Bind port (overrides config)")
@click.option("--config", "config_path", default="nexaql.yaml", help="Path to nexaql.yaml (legacy)")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: Optional[str], port: Optional[int], config_path: str, reload: bool) -> None:
    """Start the NexaQL API server."""
    import uvicorn

    os.environ.setdefault("NEXAQL_CONFIG", config_path)

    from nexaql import bootstrap as bs
    from nexaql.api.deps import get_config

    cfg = get_config()
    srv = bs.get_server_config()

    bind_host = host or srv.get("host") or cfg.server.host
    bind_port = port or srv.get("port") or cfg.server.port

    click.echo(f"Starting NexaQL server on {bind_host}:{bind_port}")
    click.echo(f"Bootstrap DB: {bs._get_db_path()}")

    uvicorn.run(
        "nexaql.api.app:create_app",
        factory=True,
        host=bind_host,
        port=bind_port,
        reload=reload,
    )


# ── nexaql init ────────────────────────────────────────────────────────────


@main.command()
@click.option("--path", default="nexaql.yaml", help="Output path for the config file")
@click.option("--force", is_flag=True, help="Overwrite if file already exists")
def init(path: str, force: bool) -> None:
    """Create an nexaql.yaml config and sample ontology + seed data."""
    if os.path.exists(path) and not force:
        click.echo(f"Config already exists: {path}")
        click.echo(f"Run 'nexaql serve' to start, or 'nexaql init --force' to regenerate.")
        return

    # Write config
    with open(path, "w") as f:
        f.write(INIT_TEMPLATE)
    click.echo(f"Created {path}")

    # Copy bundled sample files into ./ontologies/
    ontologies_dir = os.path.join(os.path.dirname(os.path.abspath(path)), "ontologies")
    os.makedirs(ontologies_dir, exist_ok=True)

    data_pkg = resources.files("nexaql.data")
    for filename in ["sample_ecommerce.yaml", "sample_ecommerce_seed.sql"]:
        dest = os.path.join(ontologies_dir, filename)
        if not os.path.exists(dest) or force:
            src = data_pkg.joinpath(filename)
            with resources.as_file(src) as src_path:
                shutil.copy2(str(src_path), dest)
            click.echo(f"Created {os.path.relpath(dest)}")

    click.echo()
    click.echo("Quick start:")
    click.echo("  nexaql install   # set up sample database + config")
    click.echo("  nexaql serve     # start the server")


# ── nexaql install ─────────────────────────────────────────────────────────


SAMPLE_CONNECTOR_NAME = "sample"


@main.command()
@click.option("--skip-sample", is_flag=True, help="Skip sample data seeding")
@click.option("--config", "config_path", default="nexaql.yaml", help="Config file path")
@click.option("--force", is_flag=True, help="Overwrite existing config and data")
def install(skip_sample: bool, config_path: str, force: bool) -> None:
    """Set up NexaQL: bootstrap config + sample database.

    This is the zero-to-running command. After install, configure your LLM
    provider in nexaql.yaml, then run: nexaql serve

    \b
    What it does:
      1. Initializes the bootstrap config database (SQLite)
      2. Creates a sample DuckDB with e-commerce data (unless --skip-sample)
      3. Registers the sample connector and ontology
      4. Generates nexaql.yaml config

    \b
    Examples:
      nexaql install               # full setup with sample data
      nexaql install --skip-sample # config only, bring your own database
      nexaql install --force       # recreate everything from scratch
    """
    import re

    from nexaql import bootstrap as bs

    click.echo()
    click.echo("  NexaQL Installer")
    click.echo("  ================")
    click.echo()

    # ── Step 1: Bootstrap config DB ──────────────────────────────────────

    click.echo(f"  [1/2] Bootstrap config database")
    click.echo(f"         Path: {bs._get_db_path()}")

    if skip_sample:
        click.echo("         Skipping sample data (--skip-sample)")
        click.echo()
        click.echo("  Setup complete! Next:")
        click.echo("    1. Add a connector:   nexaql connector add mydb --type postgresql --url postgresql://...")
        click.echo("    2. Generate schemas:  nexaql generate mydb --domain mydomain")
        click.echo("    3. Start the server:  nexaql serve")
        click.echo()
        bs.close()
        return

    # ── Step 2: Sample data ─────────────────────────────────────────────

    click.echo(f"  [2/2] Setting up sample data")

    # Load the bundled ontology YAML
    import yaml

    data_pkg = resources.files("nexaql.data")
    ontology_file = data_pkg.joinpath("sample_ecommerce.yaml")
    with resources.as_file(ontology_file) as ont_path:
        with open(ont_path) as f:
            ont_data = yaml.safe_load(f)

    domain_name = ont_data.get("domain", "sample")
    nodes = ont_data.get("nodes", {})

    # Create the DuckDB data file in ~/.nexaql/ (same dir as bootstrap DB)
    db_dir = os.path.dirname(bs._get_db_path())
    sample_db_path = os.path.join(db_dir, "sample_ecommerce.duckdb")

    if force and os.path.exists(sample_db_path):
        os.remove(sample_db_path)
        wal_path = sample_db_path + ".wal"
        if os.path.exists(wal_path):
            os.remove(wal_path)

    if os.path.exists(sample_db_path):
        click.echo(f"         Database exists: {sample_db_path}")
        click.echo(f"         Use --force to recreate.")
    else:
        import duckdb

        seed_file = data_pkg.joinpath("sample_ecommerce_seed.sql")
        with resources.as_file(seed_file) as seed_path:
            seed_sql = seed_path.read_text()

        data_conn = duckdb.connect(sample_db_path)
        cleaned = re.sub(r"^\s*--.*$", "", seed_sql, flags=re.MULTILINE)
        for stmt in cleaned.split(";"):
            stmt = stmt.strip()
            if stmt:
                data_conn.execute(stmt)

        tables = [r[0] for r in data_conn.execute("SHOW TABLES").fetchall()]
        data_conn.close()
        click.echo(f"         Created: {sample_db_path}")
        click.echo(f"         Seeded {len(tables)} tables: {', '.join(tables)}")

    # Register connector (upsert — reuse existing if present)
    existing_connector = bs.get_connector(SAMPLE_CONNECTOR_NAME)
    if existing_connector:
        connector_id = existing_connector["id"]
        click.echo(f"         Connector '{SAMPLE_CONNECTOR_NAME}' already exists (id={connector_id})")
    else:
        connector_id = bs.save_connector(
            name=SAMPLE_CONNECTOR_NAME,
            type="duckdb",
            url=sample_db_path,
        )
        click.echo(f"         Registered connector '{SAMPLE_CONNECTOR_NAME}' (id={connector_id})")

    # Register per-node schemas (clear stale ones first)
    for old_schema in bs.list_schemas(domain_name):
        bs.delete_schema(domain_name, old_schema["name"])

    for node_name, node_def in nodes.items():
        single_node_ont = {
            "domain": domain_name,
            "nodes": {node_name: node_def},
        }
        bs.save_schema(
            domain_name=domain_name,
            schema_name=node_name,
            connector_id=connector_id,
            ontology_json=single_node_ont,
        )

    click.echo(f"         Saved {len(nodes)} schemas in domain '{domain_name}'")

    # Set active domain
    bs.set_active_domain(domain_name)
    click.echo(f"         Active domain: {domain_name}")

    # ── Done ──────────────────────────────────────────────────────────────

    click.echo()
    click.echo("  Setup complete!")
    click.echo()
    click.echo("  Next steps:")
    click.echo("    1. nexaql serve")
    click.echo("    2. Open http://localhost:3717")
    click.echo("    3. Add your LLM API key in the Admin panel")
    click.echo()
    bs.close()


# ── nexaql query ───────────────────────────────────────────────────────────


@main.command()
@click.argument("query_text")
@click.option("--config", "config_path", default="nexaql.yaml", help="Path to nexaql.yaml")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "csv"]), default="table")
@click.option("--limit", default=None, type=int, help="Override result limit")
def query(query_text: str, config_path: str, output_format: str, limit: Optional[int]) -> None:
    """Run an NexaQL query from the command line.

    Example:

        nexaql query '{ invoice_header @limit(10) { invoice_number, status } }'
    """
    os.environ.setdefault("NEXAQL_CONFIG", config_path)

    from nexaql.adapters import get_adapter
    from nexaql.api.deps import get_config, get_ontology
    from nexaql.engine.parser import ParseError, parse
    from nexaql.engine.translator import translate
    from nexaql.engine.validator import validate

    try:
        cfg = get_config()
        ontology = get_ontology()
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

    # Parse
    try:
        ast = parse(query_text)
    except ParseError as e:
        click.echo(f"Parse error: {e}", err=True)
        sys.exit(1)

    # Validate
    validation = validate(ast, ontology)
    if not validation.valid:
        for err in validation.errors:
            click.echo(f"Validation error: {err.message}", err=True)
        sys.exit(1)

    for warning in validation.warnings:
        click.echo(f"Warning: {warning}", err=True)

    # Resolve adapter
    try:
        root_node = ast.body.name
        node_def = ontology.nodes.get(root_node)
        ds_name = getattr(node_def, "datasource", None) if node_def else None
        if ds_name and cfg.datasources and ds_name in cfg.datasources:
            adapter = get_adapter(cfg.datasources[ds_name])
        elif cfg.datasources:
            adapter = get_adapter(next(iter(cfg.datasources.values())))
        else:
            click.echo("Error: no datasources configured", err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(f"Error creating adapter: {e}", err=True)
        sys.exit(1)

    # Execute
    t0 = time.time()
    try:
        result = asyncio.run(adapter.execute(ast, ontology))
    except Exception as e:
        click.echo(f"Execution error: {e}", err=True)
        sys.exit(1)

    duration_ms = (time.time() - t0) * 1000

    # SQL preview
    click.echo(f"\n-- SQL ({result.adapter_type}) --", err=True)
    click.echo(result.query_preview, err=True)
    click.echo(f"\n{result.row_count} row(s) in {duration_ms:.0f}ms\n", err=True)

    # Output
    if output_format == "json":
        rows_out = result.rows[:limit] if limit else result.rows
        click.echo(json.dumps(rows_out, indent=2, default=str))

    elif output_format == "csv":
        import csv
        import io

        buf = io.StringIO()
        col_names = [c.name for c in result.columns]
        writer = csv.DictWriter(buf, fieldnames=col_names, extrasaction="ignore")
        writer.writeheader()
        rows_out = result.rows[:limit] if limit else result.rows
        for row in rows_out:
            writer.writerow(row)
        click.echo(buf.getvalue().rstrip())

    else:
        # Table format
        _print_table(result.rows, result.columns, limit)


# ── nexaql status ─────────────────────────────────────────────────────────


@main.command()
def status() -> None:
    """Show current NexaQL configuration from the bootstrap database."""
    from nexaql import bootstrap as bs

    click.echo(f"\n  NexaQL Status")
    click.echo(f"  =============")
    click.echo(f"  Bootstrap DB: {bs._get_db_path()}")

    # Server
    srv = bs.get_server_config()
    click.echo(f"\n  Server: {srv['host']}:{srv['port']}")
    click.echo(f"  Active domain: {srv.get('active_domain') or '(none)'}")

    # LLM
    llm = bs.get_active_llm_config()
    if llm:
        has_key = bool(bs.get_api_key(llm["provider"]))
        click.echo(f"\n  LLM: {llm['provider']} / {llm['model']}")
        click.echo(f"  API key: {'configured' if has_key else 'NOT SET'}")
        click.echo(f"  Mode: {llm.get('generation_mode', 'intent')}")
    else:
        click.echo(f"\n  LLM: not configured")

    # Connectors
    connectors = bs.list_connectors()
    click.echo(f"\n  Connectors ({len(connectors)}):")
    for c in connectors:
        import re
        masked = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", c.get("url", ""))
        click.echo(f"    [{c['id']}] {c['name']} ({c['type']}) — {masked}")

    # Domains
    domains = bs.list_domains()
    click.echo(f"\n  Domains ({len(domains)}):")
    for d in domains:
        active = " *" if d["name"] == srv.get("active_domain") else ""
        click.echo(f"    {d['name']}{active} — {d.get('schema_count', 0)} schemas")

    # API keys
    keys = bs.list_api_keys()
    click.echo(f"\n  API Keys ({len(keys)}):")
    for k in keys:
        masked = k["key"][:4] + "..." + k["key"][-4:] if len(k["key"]) > 8 else "***"
        click.echo(f"    {k['provider']}: {masked}")

    click.echo()
    bs.close()


# ── nexaql mcp ────────────────────────────────────────────────────────────


@main.command()
@click.option("--transport", type=click.Choice(["stdio", "streamable-http"]), default="stdio",
              help="MCP transport mode (stdio for Claude Desktop, streamable-http for web)")
@click.option("--port", default=8080, type=int, help="Port for streamable-http transport")
def mcp(transport: str, port: int) -> None:
    """Start the NexaQL MCP server for AI agent integration.

    Examples:

        nexaql mcp                          # stdio (Claude Desktop)
        nexaql mcp --transport streamable-http  # HTTP server
    """
    from nexaql.mcp_server import mcp as mcp_app

    if transport == "streamable-http":
        mcp_app.run(transport="streamable-http", port=port)
    else:
        mcp_app.run(transport="stdio")


# ── nexaql generate ────────────────────────────────────────────────────────


@main.command()
@click.argument("connector_name")
@click.option("--domain", required=True, help="Domain name (e.g. 'ecommerce', 'hr')")
@click.option("--tables", "-t", multiple=True, help="Tables to include (repeatable). If omitted, all tables.")
@click.option("--exclude", multiple=True, help="Tables to exclude (repeatable)")
@click.option("--schema", default="public", help="Database schema to introspect (default: public)")
@click.option("--description", default=None, help="Description for the domain")
@click.option("--no-enums", is_flag=True, help="Skip enum detection (faster)")
@click.option("--no-pii", is_flag=True, help="Skip PII detection")
@click.option("--no-replace", is_flag=True, help="Skip existing schemas instead of replacing")
def generate(
    connector_name: str,
    domain: str,
    tables: tuple[str, ...],
    exclude: tuple[str, ...],
    schema: str,
    description: Optional[str],
    no_enums: bool,
    no_pii: bool,
    no_replace: bool,
) -> None:
    """Generate per-table schemas from a saved connector.

    Saves schemas to the bootstrap DB with automatic edge discovery.

    Examples:

        nexaql generate my_postgres --domain ecommerce

        nexaql generate my_duckdb --domain sales -t orders -t customers

        nexaql generate my_postgres --domain hr --exclude audit_log --exclude migrations
    """
    from nexaql.ontology.service import generate_schemas

    click.echo(f"Generating schemas from connector '{connector_name}' into domain '{domain}'...")

    include_tables = list(tables) if tables else None
    exclude_tables = list(exclude) if exclude else None

    result = asyncio.run(generate_schemas(
        connector_name=connector_name,
        domain=domain,
        include_tables=include_tables,
        exclude_tables=exclude_tables,
        schema_name=schema,
        description=description or "",
        detect_enums=not no_enums,
        detect_pii=not no_pii,
        replace=not no_replace,
    ))

    if "error" in result:
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    click.echo(f"Generated {result['node_count']} schemas, "
               f"{result['total_fields']} fields, {result['total_edges']} edges")
    click.echo()

    for name, info in result["nodes"].items():
        edge_names = ", ".join(info["edges"]) or "—"
        click.echo(f"  {name} ({info['table']}): "
                   f"{info['field_count']} fields | edges: {edge_names}")

    click.echo(f"\nDomain '{domain}' is now active.")


# ── nexaql regenerate ──────────────────────────────────────────────────────


@main.command()
@click.argument("node_name")
@click.option("--domain", default=None, help="Domain name (uses active domain if not specified)")
def regenerate(node_name: str, domain: Optional[str]) -> None:
    """Regenerate a single schema/node from its original connector.

    Re-introspects the table, regenerates the schema, and re-runs edge
    discovery across the domain.

    Examples:

        nexaql regenerate orders

        nexaql regenerate customers --domain ecommerce
    """
    from nexaql import bootstrap as _bs
    from nexaql.ontology.service import regenerate_schema

    target_domain = domain or _bs.get_active_domain()
    if not target_domain:
        click.echo("Error: No active domain. Specify --domain.", err=True)
        sys.exit(1)

    click.echo(f"Regenerating schema '{node_name}' in domain '{target_domain}'...")

    result = asyncio.run(regenerate_schema(node_name=node_name, domain=target_domain))

    if "error" in result:
        click.echo(f"Error: {result['error']}", err=True)
        sys.exit(1)

    edge_names = ", ".join(result.get("edges", [])) or "—"
    click.echo(f"Regenerated: {result['node']} ({result['table']})")
    click.echo(f"  {result['field_count']} fields | edges: {edge_names}")


# ── nexaql taxonomy ───────────────────────────────────────────────────────


@main.command()
@click.option("--category", "-c", default=None, help="Filter by category (financial, legal, etc.)")
@click.option("--type", "-t", "type_name", default=None, help="Show details for a specific type (e.g. financial.invoice)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def taxonomy(category: Optional[str], type_name: Optional[str], output_format: str) -> None:
    """Browse the document taxonomy registry.

    Shows all registered document types, their subtypes, entity templates,
    and context tier definitions.

    Examples:

        nexaql taxonomy

        nexaql taxonomy -c financial

        nexaql taxonomy -t legal.contract
    """
    from nexaql.taxonomy import get_registry

    registry = get_registry()

    if type_name:
        # Show details for a specific type
        doc_type = registry.get(type_name)
        if not doc_type:
            click.echo(f"Unknown type: {type_name}", err=True)
            click.echo(f"Available: {', '.join(t.qualified_name for t in registry.list_types())}", err=True)
            sys.exit(1)

        if output_format == "json":
            click.echo(doc_type.model_dump_json(indent=2, exclude_none=True))
        else:
            click.echo(f"\n{doc_type.category.value.upper()} / {doc_type.type_name}")
            click.echo(f"  {doc_type.description}")
            click.echo(f"\n  Subtypes: {', '.join(doc_type.subtypes.keys()) or '—'}")

            click.echo(f"\n  Entity Fields ({len(doc_type.entity_template.fields)}):")
            for fname, fdef in doc_type.entity_template.fields.items():
                req = " *" if fdef.required else ""
                click.echo(f"    {fname} ({fdef.type}){req}: {fdef.description}")

            click.echo(f"\n  Context Tiers:")
            for tier_name, tier_def in doc_type.context_tiers.items():
                click.echo(f"    {tier_name.upper()} ({tier_def.scope}): {tier_def.description}")
                click.echo(f"      Group by: {', '.join(tier_def.group_by)}")
                if tier_def.link_strategy:
                    click.echo(f"      Link: match on {tier_def.link_strategy.match_fields}")
                    if tier_def.link_strategy.match_types:
                        click.echo(f"             across {tier_def.link_strategy.match_types}")

            if doc_type.message_intents:
                click.echo(f"\n  Message Intents:")
                for mi in doc_type.message_intents:
                    action = " [ACTION REQUIRED]" if mi.action_required else ""
                    click.echo(f"    {mi.intent}{action}: {mi.description}")

    else:
        # List all types
        types = registry.list_types(category)
        if not types:
            click.echo(f"No types found{' for category: ' + category if category else ''}.", err=True)
            sys.exit(1)

        if output_format == "json":
            data = [t.model_dump(exclude_none=True) for t in types]
            click.echo(json.dumps(data, indent=2))
        else:
            click.echo(f"\nDocument Taxonomy ({len(types)} types registered)\n")
            current_cat = ""
            for dt in sorted(types, key=lambda t: (t.category.value, t.type_name)):
                if dt.category.value != current_cat:
                    current_cat = dt.category.value
                    click.echo(f"  {current_cat.upper()}")

                sub_count = len(dt.subtypes)
                field_count = len(dt.entity_template.fields)
                subs = f" ({sub_count} subtypes)" if sub_count else ""
                click.echo(f"    {dt.type_name}{subs} — {field_count} entity fields — {dt.description}")

            click.echo(f"\nUse 'nexaql taxonomy -t <category.type>' for details.")


def _print_table(
    rows: list[dict],
    columns: list,
    limit: Optional[int] = None,
) -> None:
    """Print results as an ASCII table."""
    if not columns:
        click.echo("(no columns)")
        return

    col_names = [c.name.replace("__", ".") for c in columns]

    # Calculate column widths
    widths = [len(name) for name in col_names]
    display_rows = rows[:limit] if limit else rows

    for row in display_rows:
        for i, col in enumerate(columns):
            val = row.get(col.name)
            val_str = "null" if val is None else str(val)
            widths[i] = max(widths[i], len(val_str))

    # Cap column widths at 40 characters
    widths = [min(w, 40) for w in widths]

    # Header
    header = " | ".join(name.ljust(widths[i]) for i, name in enumerate(col_names))
    separator = "-+-".join("-" * widths[i] for i in range(len(col_names)))

    click.echo(header)
    click.echo(separator)

    # Rows
    for row in display_rows:
        cells = []
        for i, col in enumerate(columns):
            val = row.get(col.name)
            val_str = "null" if val is None else str(val)
            if len(val_str) > widths[i]:
                val_str = val_str[: widths[i] - 1] + "~"
            cells.append(val_str.ljust(widths[i]))
        click.echo(" | ".join(cells))


# ── nexaql domain ─────────────────────────────────────────────────────────


@main.group()
def domain() -> None:
    """Manage domains."""
    pass


@domain.command("list")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def domain_list(output_format: str) -> None:
    """List all available data domains."""
    from nexaql import bootstrap as bs

    active = bs.get_active_domain()
    domains = bs.list_domains()

    if output_format == "json":
        result = []
        for d in domains:
            name = d["name"]
            schemas = bs.list_schemas(name)
            node_count = 0
            for s in schemas:
                try:
                    ont_data = json.loads(s.get("ontology_json", "{}"))
                    node_count += len(ont_data.get("nodes", {}))
                except Exception:
                    pass
                result.append({
                    "name": name,
                    "description": d.get("description", ""),
                    "node_count": node_count,
                    "active": name == active,
                })
        click.echo(json.dumps({"domains": result, "active_domain": active}, indent=2))
        return

    if not domains:
        click.echo("No domains configured.")
        return

    click.echo(f"\n  Domains ({len(domains)})")
    click.echo(f"  {'─' * 40}")
    for d in domains:
        name = d["name"]
        marker = " *" if name == active else ""
        schemas = bs.list_schemas(name)
        node_count = 0
        for s in schemas:
            try:
                ont_data = json.loads(s.get("ontology_json", "{}"))
                node_count += len(ont_data.get("nodes", {}))
            except Exception:
                pass
        click.echo(f"  {name}{marker} — {node_count} nodes")
    click.echo()
    bs.close()


@domain.command("switch")
@click.argument("name")
def domain_switch(name: str) -> None:
    """Switch to a different data domain."""
    from nexaql import bootstrap as bs

    d = bs.get_domain(name)
    if not d:
        click.echo(f"Error: domain '{name}' not found.", err=True)
        sys.exit(1)

    schemas = bs.list_schemas(name)
    if not schemas:
        click.echo(f"Error: domain '{name}' has no schemas.", err=True)
        sys.exit(1)

    bs.set_active_domain(name)
    click.echo(f"Switched to domain '{name}'.")
    bs.close()


@domain.command("describe")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def domain_describe(output_format: str) -> None:
    """Describe the active domain's ontology."""
    from nexaql import bootstrap as bs
    from nexaql.api.deps import load_ontology_from_dict

    active = bs.get_active_domain()
    if not active:
        click.echo("Error: no active domain. Use 'nexaql domain switch <name>'.", err=True)
        sys.exit(1)

    ont_data = bs.get_domain_ontology(active)
    if not ont_data:
        click.echo(f"Error: could not load ontology for domain '{active}'.", err=True)
        sys.exit(1)

    ontology = load_ontology_from_dict(ont_data)

    if output_format == "json":
        nodes_out = {}
        for nname, ndef in ontology.nodes.items():
            fields = []
            for fname, fdef in ndef.fields.items():
                fields.append({"name": fname, "type": fdef.type, "filterable": fdef.filterable or False})
            edges = []
            for ename, edef in (ndef.edges or {}).items():
                edges.append({"name": ename, "target_node": edef.node})
            nodes_out[nname] = {"table": ndef.table, "fields": fields, "edges": edges}
        click.echo(json.dumps({"domain": active, "nodes": nodes_out}, indent=2))
        return

    click.echo(f"\n  Domain: {active}")
    click.echo(f"  Nodes: {len(ontology.nodes)}")
    click.echo(f"  {'─' * 40}")
    for nname, ndef in ontology.nodes.items():
        field_count = len(ndef.fields)
        edge_count = len(ndef.edges) if ndef.edges else 0
        click.echo(f"  {nname} ({ndef.table}) — {field_count} fields, {edge_count} edges")
    click.echo()
    bs.close()


# ── nexaql connector ──────────────────────────────────────────────────────


@main.group()
def connector() -> None:
    """Manage data connectors."""
    pass


@connector.command("list")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def connector_list(output_format: str) -> None:
    """List configured database connectors."""
    from nexaql import bootstrap as bs

    connectors = bs.list_connectors()

    if output_format == "json":
        click.echo(json.dumps({"connectors": connectors}, indent=2))
        bs.close()
        return

    if not connectors:
        click.echo("No connectors configured.")
        bs.close()
        return

    click.echo(f"\n  Connectors ({len(connectors)})")
    click.echo(f"  {'─' * 40}")
    for c in connectors:
        import re
        masked = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", c.get("url", "") or "")
        click.echo(f"  [{c['id']}] {c['name']} ({c['type']}) — {masked}")
    click.echo()
    bs.close()


@connector.command("add")
@click.argument("name")
@click.option("--type", "conn_type", required=True, type=click.Choice(["postgresql", "duckdb", "mysql"]),
              help="Connector type")
@click.option("--url", required=True, help="Connection URL or file path")
def connector_add(name: str, conn_type: str, url: str) -> None:
    """Add a new database connector."""
    from nexaql import bootstrap as bs

    existing = bs.get_connector(name)
    if existing:
        click.echo(f"Error: connector '{name}' already exists.", err=True)
        sys.exit(1)

    connector_id = bs.save_connector(name=name, type=conn_type, url=url)
    click.echo(f"Saved connector '{name}' (id={connector_id}, type={conn_type}).")
    bs.close()


@connector.command("remove")
@click.argument("name")
@click.confirmation_option(prompt="Are you sure you want to remove this connector?")
def connector_remove(name: str) -> None:
    """Remove a database connector."""
    from nexaql import bootstrap as bs

    existing = bs.get_connector(name)
    if not existing:
        click.echo(f"Error: connector '{name}' not found.", err=True)
        sys.exit(1)

    bs.delete_connector(name)
    click.echo(f"Removed connector '{name}'.")
    bs.close()


# ── nexaql schema ─────────────────────────────────────────────────────────


@main.group()
def schema() -> None:
    """Manage schemas."""
    pass


@schema.command("list")
@click.option("--domain", "domain_name", default=None, help="Domain name (uses active domain if not specified)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def schema_list(domain_name: Optional[str], output_format: str) -> None:
    """List schemas in a domain."""
    from nexaql import bootstrap as bs

    target = domain_name or bs.get_active_domain()
    if not target:
        click.echo("Error: no active domain. Specify --domain.", err=True)
        sys.exit(1)

    schemas = bs.list_schemas(target)

    if output_format == "json":
        click.echo(json.dumps({"domain": target, "schemas": schemas}, indent=2, default=str))
        bs.close()
        return

    if not schemas:
        click.echo(f"No schemas in domain '{target}'.")
        bs.close()
        return

    click.echo(f"\n  Schemas in '{target}' ({len(schemas)})")
    click.echo(f"  {'─' * 40}")
    for s in schemas:
        node_count = 0
        try:
            ont_data = json.loads(s.get("ontology_json", "{}"))
            node_count = len(ont_data.get("nodes", {}))
        except Exception:
            pass
        click.echo(f"  {s['name']} — connector: {s.get('connector_name', '?')}, {node_count} nodes")
    click.echo()
    bs.close()


@schema.command("describe")
@click.argument("node_name")
@click.option("--domain", "domain_name", default=None, help="Domain name (uses active domain if not specified)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def schema_describe(node_name: str, domain_name: Optional[str], output_format: str) -> None:
    """Describe a specific node's fields, edges, and filters."""
    from nexaql import bootstrap as bs
    from nexaql.api.deps import load_ontology_from_dict

    target = domain_name or bs.get_active_domain()
    if not target:
        click.echo("Error: no active domain. Specify --domain.", err=True)
        sys.exit(1)

    ont_data = bs.get_domain_ontology(target)
    if not ont_data:
        click.echo(f"Error: could not load ontology for domain '{target}'.", err=True)
        sys.exit(1)

    ontology = load_ontology_from_dict(ont_data)

    defn = ontology.nodes.get(node_name)
    if not defn:
        available = list(ontology.nodes.keys())
        click.echo(f"Error: node '{node_name}' not found. Available: {', '.join(available)}", err=True)
        sys.exit(1)

    if output_format == "json":
        fields = []
        for fname, fdef in defn.fields.items():
            f = {"name": fname, "type": fdef.type, "filterable": fdef.filterable or False}
            if fdef.description:
                f["description"] = fdef.description
            if fdef.values:
                f["enum_values"] = fdef.values
            if fdef.pii:
                f["pii"] = True
            fields.append(f)
        edges = []
        for ename, edef in (defn.edges or {}).items():
            edges.append({"name": ename, "target_node": edef.node, "description": edef.description})
        result = {"node": node_name, "table": defn.table, "fields": fields, "edges": edges}
        click.echo(json.dumps(result, indent=2))
        bs.close()
        return

    click.echo(f"\n  Node: {node_name}")
    click.echo(f"  Table: {defn.table}")
    click.echo(f"  {'─' * 40}")

    click.echo(f"\n  Fields ({len(defn.fields)}):")
    for fname, fdef in defn.fields.items():
        filterable = " [filterable]" if fdef.filterable else ""
        pii = " [PII]" if fdef.pii else ""
        click.echo(f"    {fname} ({fdef.type}){filterable}{pii}")

    if defn.edges:
        click.echo(f"\n  Edges ({len(defn.edges)}):")
        for ename, edef in defn.edges.items():
            click.echo(f"    {ename} → {edef.node}")

    if defn.special_filters:
        click.echo(f"\n  Special Filters ({len(defn.special_filters)}):")
        for sname, sdef in defn.special_filters.items():
            click.echo(f"    @{sname}: {sdef.description}")

    click.echo()
    bs.close()


# ── Entry point guard ───────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
