"""Deterministic mock LLM client for demos and offline testing.

Applies simple keyword rules against the clause text to produce
realistic-looking ``ClauseReview`` payloads without making any network
calls.  Useful for CI and for demos where no API key is available.

Trigger rules (checked in order, first match wins):
  - ``"in perpetuity"`` / ``"perpetual"``   → MEDIUM risk (duration issue)
  - ``"california"`` / ``"san francisco county"`` → HIGH risk (jurisdiction)
  - *(default)*                              → LOW risk (compliant)
"""
from __future__ import annotations

from contract_redliner.integrations.llm_base import LLMClient


class MockLLMClient(LLMClient):
    """Rule-based mock that mimics real LLM output without network calls."""

    async def review_clause(self, title: str, text: str, playbook: dict) -> dict:
        """Apply keyword heuristics to classify and suggest revisions for a clause.

        Args:
            title:    Clause heading (unused by mock rules, included for
                      interface parity with real clients).
            text:     Full clause body searched for trigger keywords.
            playbook: Policy dict; ``approved_confidentiality_term``,
                      ``preferred_governing_law``, and ``preferred_venue``
                      are used when constructing suggested text.

        Returns:
            Dict with ``risk_level``, ``issue_type``, ``rationale``,
            ``suggested_text``, and ``confidence``.
        """
        text_lower = text.lower()

        # Perpetual confidentiality exceeds the approved term.
        if "perpetuity" in text_lower or "perpetual" in text_lower:
            return {
                "risk_level": "medium",
                "issue_type": "Confidentiality duration",
                "rationale": "Perpetual confidentiality exceeds standard low-risk NDA policy.",
                "suggested_text": text
                    .replace("in perpetuity", f"for {playbook['approved_confidentiality_term']} from the date of disclosure")
                    .replace("perpetual", playbook["approved_confidentiality_term"]),
                "confidence": 0.96,
            }

        # Non-approved jurisdiction — requires human escalation.
        if "california" in text_lower or "san francisco county" in text_lower:
            return {
                "risk_level": "high",
                "issue_type": "Jurisdiction",
                "rationale": "Jurisdiction is outside approved policy and requires escalation.",
                "suggested_text": (
                    f"This Agreement shall be governed by the laws of the State of "
                    f"{playbook['preferred_governing_law']}, without regard to conflict of laws "
                    f"principles, and the parties agree to jurisdiction in the state or federal "
                    f"courts located in {playbook['preferred_venue']}."
                ),
                "confidence": 0.94,
            }

        # Clause aligns with playbook — no changes needed.
        return {
            "risk_level": "low",
            "issue_type": "No issue",
            "rationale": "Clause aligns with the standard playbook.",
            "suggested_text": text,
            "confidence": 0.98,
        }
