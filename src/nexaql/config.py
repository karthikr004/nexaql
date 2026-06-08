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


def load_config(path: str = "nexaql.yaml") -> NexaQLConfig:
    """Load an ``nexaql.yaml`` configuration file.

    Environment variable references of the form ``${VAR}`` in string values
    are expanded before Pydantic validation.
    """
    abs_path = os.path.abspath(path)
    with open(abs_path) as f:
        raw = yaml.safe_load(f)

    substituted = _substitute_env(raw)
    return NexaQLConfig(**substituted)
