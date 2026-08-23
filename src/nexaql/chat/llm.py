# Copyright (c) 2026-present NexaQL Contributors
"""Provider-agnostic LLM client layer.

Supported providers:

  - Ollama (local):       http://localhost:11434/v1  — free, private, no key needed
  - OpenRouter (cloud):   https://openrouter.ai/api/v1  — one key for Claude, GPT, Gemini, etc.
  - OpenAI (direct):      https://api.openai.com/v1
  - Anthropic (direct):   Native SDK — use your Anthropic API key directly for Claude

Ollama, OpenRouter, and OpenAI use the OpenAI SDK (OpenAI-compatible APIs).
Anthropic uses its own SDK since its API format differs from OpenAI's.
"""

from __future__ import annotations

import logging
from typing import Any

import re

import httpx
from openai import OpenAI

from nexaql.config import LLMConfig

# Regex to strip <think>...</think> blocks from thinking models (Qwen3, etc.)
_THINK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)

log = logging.getLogger(__name__)

# ── Provider base URLs (OpenAI-compatible providers only) ────────────────────

PROVIDER_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "meta": "https://api.meta.ai/v1",
}

# Default models per provider (used only as fallback hints in status display)
DEFAULT_MODELS: dict[str, str] = {
    "ollama": "",
    "openrouter": "",
    "openai": "",
    "anthropic": "claude-sonnet-4-6",
    "meta": "muse-spark-1.1",
}

# ── Client cache ──────────────────────────────────────────────────────────────

_client_cache: dict[str, Any] = {}


def _get_client(llm_config: LLMConfig) -> OpenAI:
    """Get or create a cached OpenAI client for the given config."""
    provider = llm_config.provider.lower()
    base_url = llm_config.base_url or PROVIDER_BASE_URLS.get(provider, PROVIDER_BASE_URLS["ollama"])

    # Ollama doesn't need a real key
    api_key = llm_config.api_key or ("ollama" if provider == "ollama" else "no-key")

    cache_key = f"{base_url}:{api_key[:8]}"
    if cache_key not in _client_cache:
        extra_headers = {}
        if provider == "openrouter":
            extra_headers["HTTP-Referer"] = "https://nexaql.dev"
            extra_headers["X-Title"] = "NexaQL"

        _client_cache[cache_key] = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=extra_headers or None,
        )
    return _client_cache[cache_key]


def _get_anthropic_client(llm_config: LLMConfig):
    """Get or create a cached Anthropic client."""
    import anthropic

    api_key = llm_config.api_key or "no-key"
    cache_key = f"anthropic:{api_key[:8]}"
    if cache_key not in _client_cache:
        _client_cache[cache_key] = anthropic.Anthropic(api_key=api_key)
    return _client_cache[cache_key]


# ── Unified chat completion ───────────────────────────────────────────────────


def chat_completion(
    llm_config: LLMConfig,
    *,
    system: str | None = None,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
) -> str:
    """Send a chat completion request and return the assistant text.

    Supports all providers: Ollama, OpenRouter, OpenAI (via OpenAI SDK),
    and Anthropic (via native Anthropic SDK).
    """
    if not llm_config.provider or not llm_config.model:
        raise RuntimeError(
            "LLM not configured. Set 'provider' and 'model' in nexaql.yaml "
            "or configure via the Admin panel. "
            "Supported providers: ollama, openrouter, openai, anthropic, meta."
        )

    provider = llm_config.provider.lower()
    tok = max_tokens or llm_config.max_tokens

    # ── Anthropic: native SDK (not OpenAI-compatible) ────────────────────────
    if provider == "anthropic":
        return _chat_completion_anthropic(
            llm_config, system=system, messages=messages, max_tokens=tok,
        )

    # ── All other providers: OpenAI SDK ──────────────────────────────────────
    client = _get_client(llm_config)

    full_messages: list[dict[str, str]] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    create_kwargs: dict[str, Any] = {
        "model": llm_config.model,
        "max_tokens": tok,
        "messages": full_messages,
    }
    if llm_config.temperature is not None:
        create_kwargs["temperature"] = llm_config.temperature
    response = client.chat.completions.create(**create_kwargs)  # type: ignore[arg-type]

    text = response.choices[0].message.content or ""
    # Strip thinking tags from models like Qwen3 that emit <think>...</think>
    text = _THINK_RE.sub("", text).strip()
    return text


def _chat_completion_anthropic(
    llm_config: LLMConfig,
    *,
    system: str | None = None,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
) -> str:
    """Chat completion via the native Anthropic SDK.

    Anthropic's Messages API differs from OpenAI's:
      - system prompt is a separate parameter, not a message
      - response is a list of content blocks, not a single string
    """
    client = _get_anthropic_client(llm_config)
    tok = max_tokens or llm_config.max_tokens or 4096

    # Filter out system messages (Anthropic uses a separate `system` param)
    user_messages = [m for m in messages if m.get("role") != "system"]

    kwargs: dict[str, Any] = {
        "model": llm_config.model,
        "max_tokens": tok,
        "messages": user_messages,
    }
    if llm_config.temperature is not None:
        kwargs["temperature"] = llm_config.temperature
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)

    # Extract text from content blocks
    text = "".join(
        block.text for block in response.content if block.type == "text"
    )

    # Strip thinking tags (some models may emit them)
    text = _THINK_RE.sub("", text).strip()
    return text


# ── Ollama health check ──────────────────────────────────────────────────────


def check_ollama_status(base_url: str = "http://localhost:11434") -> dict[str, Any]:
    """Check if Ollama is running and which models are available.

    Returns ``{"running": bool, "models": [...], "has_default_model": bool}``.
    """
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            default_model = DEFAULT_MODELS.get("ollama", "qwen3:4b")
            # Check if default model (or any variant of it) is installed
            base_name = default_model.split(":")[0]
            has_default = any(base_name in m.lower() for m in models)
            return {
                "running": True,
                "models": models,
                "has_default_model": has_default,
                "default_model": default_model,
            }
    except Exception:
        pass
    return {
        "running": False,
        "models": [],
        "has_default_model": False,
        "default_model": DEFAULT_MODELS.get("ollama", "qwen3:4b"),
    }


def invalidate_client_cache() -> None:
    """Clear the client cache (e.g. after API key change)."""
    _client_cache.clear()
