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
  provider: anthropic
  api_key: ${ANTHROPIC_API_KEY}
  model: claude-sonnet-4-20250514
  max_tokens: 4096
  summary_max_tokens: 1024

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
    click.echo("Quick start (works immediately with sample data):")
    click.echo("  nexaql serve")
    click.echo()
    click.echo("To use your own database:")
    click.echo("  1. Edit nexaql.yaml — update datasource and ontology path")
    click.echo("  2. Set ANTHROPIC_API_KEY for agent chat (optional)")
    click.echo("  3. nexaql serve")


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
