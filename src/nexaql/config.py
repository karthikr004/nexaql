"""NexaQL configuration loader with environment variable substitution."""

from __future__ import annotations

import os
import re
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


# ── Config models ────────────────────────────────────────────────────────────


class OntologyConfig(BaseModel):
    path: Optional[str] = None
    domain: Optional[str] = None


class DatasourceEntry(BaseModel):
    type: str
    url: Optional[str] = None
    path: Optional[str] = None
    ssl: Optional[bool] = None
    seed_file: Optional[str] = None  # SQL file to auto-run on empty DuckDB databases
    # Snowflake / BigQuery / Presto extras
    account: Optional[str] = None
    warehouse: Optional[str] = None
    database: Optional[str] = None
    schema_: Optional[str] = Field(None, alias="schema")
    project_id: Optional[str] = None
    dataset: Optional[str] = None
    catalog: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    # REST extras
    base_url: Optional[str] = None

    model_config = {"populate_by_name": True}


class LLMConfig(BaseModel):
    provider: str = ""       # User must configure: ollama, openrouter, openai, etc.
    api_key: Optional[str] = None
    base_url: Optional[str] = None  # custom endpoint override
    model: str = ""          # User must configure: any OpenAI-compatible model
    max_tokens: int = 4096
    summary_max_tokens: int = 2048  # extra headroom for thinking models (Qwen, etc.)
    generation_mode: str = "intent"  # "intent" (structured JSON→builder) or "raw" (LLM generates NexaQL)


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 3717
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class AuthConfig(BaseModel):
    mode: str = "dev"  # "dev" | "jwt"
    # JWT settings (future):
    # jwks_url: Optional[str] = None
    # role_claim: str = "roles"
    # attribute_claims: list[str] = []


class NexaQLConfig(BaseModel):
    ontology: OntologyConfig
    datasources: dict[str, DatasourceEntry] = Field(default_factory=dict)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)


# ── Env-var substitution ─────────────────────────────────────────────────────

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _substitute_env(value: Any) -> Any:
    """Recursively replace ``${ENV_VAR}`` placeholders with env values."""
    if isinstance(value, str):
        def _replacer(m: re.Match[str]) -> str:
            env_key = m.group(1)
            env_val = os.environ.get(env_key)
            if env_val is None:
                # Return empty string for unset env vars (optional fields like API keys)
                return ""
            return env_val

        return _ENV_PATTERN.sub(_replacer, value)

    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_substitute_env(item) for item in value]

    return value


# ── Public API ───────────────────────────────────────────────────────────────


def load_config_from_bootstrap() -> NexaQLConfig:
    """Load configuration from the bootstrap DuckDB database.

    This is the primary config loader. Falls back to nexaql.yaml only if
    the bootstrap DB has no LLM config (legacy/first-run scenario).
    """
    from nexaql import bootstrap as bs

    # LLM config — auto-detect provider from saved API keys
    llm_data = bs.get_active_llm_config()
    provider = llm_data.get("provider", "") if llm_data else ""
    api_key = bs.get_api_key(provider) if provider else None

    # If configured provider has no key, find one that does
    if not api_key and provider and provider.lower() != "ollama":
        _provider_models = {
            "anthropic": "claude-sonnet-4-6",
            "openai": "gpt-4o",
            "openrouter": "anthropic/claude-sonnet-4-6",
            "google": "gemini-2.0-flash",
        }
        for candidate in _provider_models:
            key = bs.get_api_key(candidate)
            if key:
                provider = candidate
                api_key = key
                break

    if llm_data:
        model = llm_data.get("model", "")
        if provider != llm_data.get("provider", ""):
            _fallback_models = {
                "anthropic": "claude-sonnet-4-6",
                "openai": "gpt-4o",
                "openrouter": "anthropic/claude-sonnet-4-6",
                "google": "gemini-2.0-flash",
            }
            model = _fallback_models.get(provider, model)
        llm = LLMConfig(
            provider=provider,
            model=model,
            max_tokens=llm_data.get("max_tokens", 4096),
            summary_max_tokens=llm_data.get("summary_max_tokens", 2048),
            generation_mode=llm_data.get("generation_mode", "intent"),
            api_key=api_key,
        )
    else:
        llm = LLMConfig()

    # Server config
    srv_data = bs.get_server_config()
    server = ServerConfig(
        host=srv_data.get("host", "0.0.0.0"),
        port=srv_data.get("port", 3717),
        cors_origins=srv_data.get("cors_origins", ["*"]),
    )

    # Active domain
    active_domain = srv_data.get("active_domain")
    ontology = OntologyConfig(domain=active_domain)

    # Build datasources from connectors linked to active domain schemas
    datasources: dict[str, DatasourceEntry] = {}
    if active_domain:
        schemas = bs.list_schemas(active_domain)
        seen_connectors: set[int] = set()
        for schema in schemas:
            cid = schema["connector_id"]
            if cid in seen_connectors:
                continue
            seen_connectors.add(cid)
            conn_data = bs.get_connector_by_id(cid)
            if conn_data:
                ds_name = conn_data["name"]
                ds_type = conn_data.get("type", "postgresql")
                ds_url = conn_data.get("url", "")
                if ds_type == "duckdb":
                    datasources[ds_name] = DatasourceEntry(type=ds_type, path=ds_url)
                else:
                    datasources[ds_name] = DatasourceEntry(type=ds_type, url=ds_url)

    # If no datasources from bootstrap, try first connector
    if not datasources:
        connectors = bs.list_connectors()
        if connectors:
            c = connectors[0]
            ds_type = c.get("type", "postgresql")
            ds_url = c.get("url", "")
            if ds_type == "duckdb":
                datasources[c["name"]] = DatasourceEntry(type=ds_type, path=ds_url)
            else:
                datasources[c["name"]] = DatasourceEntry(type=ds_type, url=ds_url)

    return NexaQLConfig(
        ontology=ontology,
        datasources=datasources,
        llm=llm,
        server=server,
    )


def load_config(path: str = "nexaql.yaml") -> NexaQLConfig:
    """Load configuration -- bootstrap DB first, YAML fallback.

    Tries the bootstrap DuckDB database first. If it has no meaningful
    config (no LLM, no connectors), falls back to loading nexaql.yaml
    and migrates its data into the bootstrap DB.
    """
    # Try bootstrap DB first
    try:
        cfg = load_config_from_bootstrap()
        if cfg.llm.provider or cfg.datasources:
            return cfg
    except Exception:
        pass

    # Fallback: load from YAML (legacy)
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        try:
            return load_config_from_bootstrap()
        except Exception:
            return NexaQLConfig(ontology=OntologyConfig())

    with open(abs_path) as f:
        raw = yaml.safe_load(f)

    substituted = _substitute_env(raw)
    return NexaQLConfig(**substituted)
