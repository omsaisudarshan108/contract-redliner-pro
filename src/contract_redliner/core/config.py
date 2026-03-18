"""Application settings loaded from environment variables.

All settings have sensible defaults so the app runs out-of-the-box
with the mock LLM provider.  Override via a ``.env`` file or by exporting
variables before starting the server.

Example ``.env``::

    LLM_PROVIDER=openai
    OPENAI_API_KEY=sk-...
    OPENAI_MODEL=gpt-4o
"""
from functools import lru_cache
from pydantic import BaseModel
import os


class Settings(BaseModel):
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    """Active LLM backend: ``"mock"``, ``"openai"``, or ``"gemini"``."""
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton ``Settings`` instance.

    The cache means environment variables are read exactly once at startup.
    In tests, call ``get_settings.cache_clear()`` before patching env vars.
    """
    return Settings()
