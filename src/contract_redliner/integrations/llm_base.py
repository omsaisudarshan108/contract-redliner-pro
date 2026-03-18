"""Abstract base class for all LLM provider clients.

Every concrete implementation (OpenAI, Gemini, Mock) must subclass
``LLMClient`` and implement ``review_clause``.  The factory in
``integrations.factory`` selects the correct implementation at runtime.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Contract for a clause-review LLM backend."""

    @abstractmethod
    async def review_clause(self, title: str, text: str, playbook: dict) -> dict:
        """Review a single NDA clause against the company playbook.

        Implementations must call the underlying LLM and return a dict
        with exactly these keys:

        .. code-block:: python

            {
                "risk_level":     "low" | "medium" | "high",
                "issue_type":     str,   # short label, e.g. "Jurisdiction"
                "rationale":      str,   # plain-English explanation
                "suggested_text": str,   # revised clause (may equal original)
                "confidence":     float, # 0.0–1.0
            }

        Args:
            title:    First line of the clause, used as a heading in prompts.
            text:     Full body text of the clause.
            playbook: Loaded policy dict from ``data/playbook.json``.

        Returns:
            Dict conforming to the schema above.

        Raises:
            RuntimeError: If a required API key is missing.
        """
        raise NotImplementedError
