"""LLM prompt templates used by all provider clients.

Keeping prompts in one place makes it easy to iterate on instructions
without touching client code.  Both constants are injected into every
``review_clause`` call regardless of provider.
"""

SYSTEM_PROMPT = """
You are a legal AI assistant for low-risk NDA review.
You must stay grounded in the company playbook and never invent policy.
Escalate when jurisdiction or material legal risk falls outside the approved policy.
""".strip()
"""Sets the LLM's persona and ground rules for every review session."""

REVIEW_PROMPT = """
Review the clause against the company playbook.
Return strict JSON with keys:
- risk_level
- issue_type
- rationale
- suggested_text
- confidence
""".strip()
"""Instructs the model to return structured JSON matching the ``ClauseReview`` schema."""
