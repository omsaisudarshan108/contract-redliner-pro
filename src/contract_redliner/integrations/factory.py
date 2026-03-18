"""Factory for creating the active LLM client.

Provider selection order:
  1. ``provider`` argument (per-request override from the UI or tests).
  2. ``LLM_PROVIDER`` environment variable (default: ``"mock"``).

Passing ``api_key`` / ``model`` lets callers supply credentials at
request time without mutating environment variables or cached settings.
"""
from __future__ import annotations

from contract_redliner.core.config import get_settings
from contract_redliner.integrations.gemini_client import GeminiClient
from contract_redliner.integrations.llm_base import LLMClient
from contract_redliner.integrations.mock_client import MockLLMClient
from contract_redliner.integrations.openai_client import OpenAIClient


def get_llm_client(
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """Instantiate and return the appropriate LLM client.

    Args:
        provider: ``"openai"``, ``"gemini"``, or ``"mock"``.
                  Falls back to ``settings.llm_provider`` when ``None``.
        api_key:  API key to inject into the client, overriding the
                  environment variable for this request only.
        model:    Model name override (e.g. ``"gpt-4o"``).

    Returns:
        A ready-to-use ``LLMClient`` instance.
    """
    p = (provider or get_settings().llm_provider).lower()
    if p == "openai":
        return OpenAIClient(api_key=api_key, model=model)
    if p == "gemini":
        return GeminiClient(api_key=api_key, model=model)
    return MockLLMClient()
