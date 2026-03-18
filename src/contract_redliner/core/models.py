"""Pydantic data models shared across the API, workflow, and export layers."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high"]
"""Risk classification assigned by the LLM to each reviewed clause."""


class Clause(BaseModel):
    """A single extracted section of the contract, ready for LLM review."""

    clause_id: str
    """Stable identifier, e.g. ``"clause_3"``."""
    title: str
    """First line of the section, used as a heading in prompts and exports."""
    text: str
    """Full body text of the clause."""


class ClauseReview(BaseModel):
    """LLM assessment of one clause against the company playbook."""

    clause_id: str
    title: str
    risk_level: RiskLevel
    issue_type: str
    """Short label for the policy issue, e.g. ``"Jurisdiction"``."""
    rationale: str
    """Plain-English explanation of the finding."""
    suggested_text: str
    """AI-proposed rewrite; equals the original when no change is needed."""
    confidence: float = 0.9
    """Model certainty (0–1).  Values below 0.75 trigger escalation."""


class RedlineEntry(BaseModel):
    """A concrete change proposed by the AI, ready for DOCX track-change export."""

    clause_id: str
    title: str
    original_text: str
    suggested_text: str
    changed_by: str = "AI"
    reason: str
    """Human-readable rationale copied from ``ClauseReview.rationale``."""
    risk_level: RiskLevel
    confidence: float = 0.9


class ContractState(BaseModel):
    """Mutable state object threaded through every node of the LangGraph workflow.

    LangGraph 1.x returns this as a ``dict`` from ``ainvoke``; callers
    must use ``ContractState.model_validate(raw)`` to recover the typed model.
    """

    raw_document: str
    """Original contract text as received from the caller."""
    clauses: list[Clause] = Field(default_factory=list)
    reviews: list[ClauseReview] = Field(default_factory=list)
    redlines: list[RedlineEntry] = Field(default_factory=list)
    escalated: bool = False
    final_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    """Pass-through bag for per-request config: ``provider``, ``openai_api_key``, etc."""


class ReviewRequest(BaseModel):
    """Payload for ``POST /review/text``."""

    document_text: str
    filename: str | None = None
    provider: str | None = None
    """Override the server's default LLM provider for this request."""
    openai_api_key: str | None = None
    """Per-request OpenAI key; takes precedence over ``OPENAI_API_KEY``."""
    gemini_api_key: str | None = None
    """Per-request Gemini key; takes precedence over ``GEMINI_API_KEY``."""


class ReviewResponse(BaseModel):
    """Response body returned by both review endpoints."""

    summary: str
    """One-sentence outcome, e.g. how many clauses were reviewed and escalated."""
    escalated: bool
    reviews: list[ClauseReview]
    redlines: list[RedlineEntry]


class ExportRequest(BaseModel):
    """Payload for ``POST /export/docx``."""

    title: str = "Redlined Contract"
    """Title written into the document and its metadata."""
    redlines: list[RedlineEntry]
