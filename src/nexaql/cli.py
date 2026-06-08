# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL command-line interface.

Provides three commands:

- ``nexaql serve`` -- start the FastAPI server
- ``nexaql init``  -- create an ``nexaql.yaml`` template
- ``nexaql query`` -- run a query from the command line
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
@click.option("--config", "config_path", default="nexaql.yaml", help="Path to nexaql.yaml")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: Optional[str], port: Optional[int], config_path: str, reload: bool) -> None:
    """Start the NexaQL API server."""
    import uvicorn

    os.environ.setdefault("NEXAQL_CONFIG", config_path)

    # Import after setting env so the config loader picks up the right file
    from nexaql.api.deps import get_config

    cfg = get_config()
    bind_host = host or cfg.server.host
    bind_port = port or cfg.server.port

    click.echo(f"Starting NexaQL server on {bind_host}:{bind_port}")
    click.echo(f"Config: {os.path.abspath(config_path)}")

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


DUCKDB_FILE = "nexaql.duckdb"


@main.command()
@click.option("--skip-sample", is_flag=True, help="Skip sample data seeding")
@click.option("--config", "config_path", default="nexaql.yaml", help="Config file path")
@click.option("--force", is_flag=True, help="Overwrite existing config and data")
def install(skip_sample: bool, config_path: str, force: bool) -> None:
    """Set up NexaQL: sample database + config.

    This is the zero-to-running command. After install, configure your LLM
    provider in nexaql.yaml, then run: nexaql serve

    \b
    What it does:
      1. Creates nexaql.duckdb with sample e-commerce data
      2. Seeds the sample ontology into the database
      3. Generates nexaql.yaml config

    \b
    Examples:
      nexaql install               # full setup with sample data
      nexaql install --skip-sample # config only, bring your own database
    """

    click.echo()
    click.echo("  NexaQL Installer")
    click.echo("  ================")
    click.echo()

    # ── Step 1: Create DuckDB with sample data ────────────────────────────

    click.echo(f"  [1/2] Setting up database: {DUCKDB_FILE}")

    if not skip_sample:
        import duckdb

        db_exists = os.path.exists(DUCKDB_FILE) and not force
        conn = duckdb.connect(DUCKDB_FILE)

        if db_exists:
            # Check if tables already exist
            tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
            if tables:
                click.echo(f"         Database exists with {len(tables)} tables. Use --force to recreate.")
            else:
                db_exists = False

        if not db_exists:
            # Load and execute seed SQL
            data_pkg = resources.files("nexaql.data")
            seed_file = data_pkg.joinpath("sample_ecommerce_seed.sql")
            with resources.as_file(seed_file) as seed_path:
                seed_sql = seed_path.read_text()

            # DuckDB can execute multiple statements
            conn.execute(seed_sql)
            tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
            click.echo(f"         Seeded {len(tables)} tables: {', '.join(tables)}")

        # Seed ontology into nexaql_ontologies table
        click.echo("         Loading ontology into database...")

        # Ensure ontology table exists
        try:
            conn.execute("CREATE SEQUENCE IF NOT EXISTS nexaql_ontologies_id_seq START 1")
        except Exception:
            pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS nexaql_ontologies (
                id              INTEGER PRIMARY KEY DEFAULT nextval('nexaql_ontologies_id_seq'),
                domain          TEXT NOT NULL,
                version_num     INTEGER NOT NULL DEFAULT 1,
                data            TEXT NOT NULL,
                author          TEXT NOT NULL DEFAULT 'system',
                note            TEXT,
                is_active       BOOLEAN NOT NULL DEFAULT TRUE,
                created_at      TIMESTAMP NOT NULL DEFAULT current_timestamp,
                UNIQUE(domain, version_num)
            )
        """)

        # Load sample ontology YAML and insert into DB
        data_pkg = resources.files("nexaql.data")
        ontology_file = data_pkg.joinpath("sample_ecommerce.yaml")
        with resources.as_file(ontology_file) as ont_path:
            import yaml
            with open(ont_path) as f:
                ont_data = yaml.safe_load(f)

        domain = ont_data.get("domain", "ecommerce")

        # Check if ontology already exists
        existing = conn.execute(
            "SELECT COUNT(*) FROM nexaql_ontologies WHERE domain = ? AND is_active = TRUE",
            [domain],
        ).fetchone()[0]

        if existing > 0 and not force:
            click.echo(f"         Ontology '{domain}' already exists in database")
        else:
            if existing > 0:
                conn.execute("DELETE FROM nexaql_ontologies WHERE domain = ?", [domain])

            conn.execute(
                "INSERT INTO nexaql_ontologies (domain, version_num, data, author, note, is_active) "
                "VALUES (?, 1, ?, 'nexaql-install', 'Initial setup', TRUE)",
                [domain, json.dumps(ont_data)],
            )
            click.echo(f"         Ontology '{domain}' loaded ({len(ont_data.get('nodes', {}))} nodes)")

        conn.close()
    else:
        click.echo("         Skipping sample data (--skip-sample)")

    # ── Step 2: Generate config ───────────────────────────────────────────

    click.echo(f"  [2/2] Generating config: {config_path}")

    if os.path.exists(config_path) and not force:
        click.echo(f"         Config already exists. Use --force to overwrite.")
    else:
        install_config = f"""\
# NexaQL configuration — generated by nexaql install
ontology:
  domain: ecommerce

datasources:
  default:
    type: duckdb
    path: {DUCKDB_FILE}

llm:
  # Configure your LLM provider. NexaQL works with any OpenAI-compatible API.
  #
  # Option 1: Ollama (local, free)
  #   Install Ollama from https://ollama.com, then pull a model:
  #     ollama pull qwen2.5-coder:7b
  #   provider: ollama
  #   model: qwen2.5-coder:7b
  #
  # Option 2: OpenRouter (cloud — Claude, GPT, Gemini, 200+ models)
  #   provider: openrouter
  #   api_key: ${{OPENROUTER_API_KEY}}
  #   model: anthropic/claude-sonnet-4-20250514
  #
  # Option 3: OpenAI directly
  #   provider: openai
  #   api_key: ${{OPENAI_API_KEY}}
  #   model: gpt-4o-mini
  provider: ""
  model: ""
  max_tokens: 4096
  summary_max_tokens: 2048

server:
  host: 0.0.0.0
  port: 3717
  cors_origins:
    - "*"
"""
        with open(config_path, "w") as f:
            f.write(install_config)
        click.echo(f"         Created {config_path}")

    # ── Done ──────────────────────────────────────────────────────────────

    click.echo()
    click.echo("  Setup complete!")
    click.echo()
    click.echo("  Next steps:")
    click.echo("    1. Configure your LLM provider in nexaql.yaml")
    click.echo("    2. nexaql serve")
    click.echo()
    click.echo(f"  Then open: http://localhost:3717")
    click.echo()


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


# ── nexaql generate ────────────────────────────────────────────────────────


@main.command()
@click.argument("connection_url")
@click.option("--schema", default="public", help="Database schema to introspect")
@click.option("--output", "-o", default=None, help="Output YAML file path")
@click.option("--domain", default="auto_generated", help="Domain name for the ontology")
@click.option("--description", default=None, help="Description for the ontology")
@click.option("--exclude", multiple=True, help="Tables to exclude (repeatable)")
@click.option("--include", multiple=True, help="Only include these tables (repeatable)")
@click.option("--no-enums", is_flag=True, help="Skip enum detection (faster)")
@click.option("--no-pii", is_flag=True, help="Skip PII detection")
@click.option("--system-columns", is_flag=True, help="Include system columns (created_at, etc.)")
def generate(
    connection_url: str,
    schema: str,
    output: Optional[str],
    domain: str,
    description: Optional[str],
    exclude: tuple[str, ...],
    include: tuple[str, ...],
    no_enums: bool,
    no_pii: bool,
    system_columns: bool,
) -> None:
    """Generate a NexaQL ontology from a database schema.

    Connects to the database, introspects tables/columns/foreign keys,
    and generates an ontology YAML file.

    Examples:

        nexaql generate postgresql://user:pass@localhost/mydb

        nexaql generate postgresql://user:pass@localhost/mydb -o ontologies/myapp.yaml

        nexaql generate mydata.duckdb --schema main --domain inventory
    """
    from nexaql.ontology.generator import OntologyGenerator

    desc = description or f"Auto-generated ontology from {domain} database"

    click.echo(f"Connecting to {connection_url}...")

    gen = OntologyGenerator(connection_url)

    try:
        ontology = asyncio.run(gen.generate(
            schema=schema,
            domain=domain,
            description=desc,
            exclude_tables=list(exclude) if exclude else None,
            include_tables=list(include) if include else None,
            detect_enums=not no_enums,
            detect_pii=not no_pii,
            include_system_columns=system_columns,
        ))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    node_count = len(ontology.nodes)
    field_count = sum(len(n.fields) for n in ontology.nodes.values())
    edge_count = sum(len(n.edges or {}) for n in ontology.nodes.values())

    click.echo(f"Discovered {node_count} tables, {field_count} fields, {edge_count} edges")

    # Summary table
    for name, node in ontology.nodes.items():
        pii_count = sum(1 for f in node.fields.values() if f.pii)
        enum_count = sum(1 for f in node.fields.values() if f.values)
        edge_names = ", ".join((node.edges or {}).keys()) or "—"
        pii_str = f" ({pii_count} PII)" if pii_count else ""
        enum_str = f" ({enum_count} enums)" if enum_count else ""
        click.echo(f"  {name}: {len(node.fields)} fields{pii_str}{enum_str} | edges: {edge_names}")

    if output:
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
        gen.save(ontology, output)
        click.echo(f"\nSaved to {output}")
    else:
        # Print YAML to stdout
        import yaml
        data = ontology.model_dump(exclude_none=True)
        click.echo("\n---")
        click.echo(yaml.dump(data, default_flow_style=False, sort_keys=False))

    click.echo(f"\nTo enrich with LLM descriptions, run:")
    click.echo(f"  nexaql enrich {output or '<path>'}")


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


# ── Entry point guard ───────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
