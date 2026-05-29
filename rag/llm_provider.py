"""Provider capability helpers for LLM integrations."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    """Capability flags for a configured LLM provider."""

    provider: str
    supports_prompt_caching: bool
    supports_local_runtime: bool


def get_llm_provider() -> str:
    """Return normalized LLM provider name from environment."""
    return os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()


def get_provider_capabilities(provider: str | None = None) -> ProviderCapabilities:
    """Return capabilities for the requested (or configured) provider."""
    resolved = (provider or get_llm_provider()).strip().lower()
    local_runtime = resolved in {"ollama", "local"}
    return ProviderCapabilities(
        provider=resolved,
        supports_prompt_caching=(resolved == "anthropic"),
        supports_local_runtime=local_runtime,
    )
