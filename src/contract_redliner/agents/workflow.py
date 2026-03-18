"""LangGraph workflow for end-to-end NDA redlining.

Pipeline (linear until the gate):
    ingest → extract_clauses → review_clauses → create_redlines
        → gate (conditional)
            ├─ escalate  (any HIGH risk or confidence < 0.75)
            └─ summarize (all clauses within policy bounds)
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from contract_redliner.core.models import Clause, ClauseReview, ContractState, RedlineEntry
from contract_redliner.core.playbook import load_playbook
from contract_redliner.integrations.factory import get_llm_client
from contract_redliner.utils.text import split_into_clauses


async def ingest(state: ContractState) -> ContractState:
    """Mark the document as received and ready for processing.

    Sets ``state.metadata["ingested"] = True`` so downstream nodes can
    assert that the ingestion step completed.
    """
    state.metadata["ingested"] = True
    return state


async def extract_clauses(state: ContractState) -> ContractState:
    """Split the raw document text into individually reviewable clauses.

    Each double-newline-delimited section becomes a ``Clause`` with a
    stable ``clause_id`` (e.g. ``"clause_1"``) and a title derived from
    its first line.  The result is stored on ``state.clauses``.
    """
    clauses: list[Clause] = []
    for idx, (title, text) in enumerate(split_into_clauses(state.raw_document), start=1):
        clauses.append(Clause(clause_id=f"clause_{idx}", title=title, text=text))
    state.clauses = clauses
    return state


async def review_clauses(state: ContractState) -> ContractState:
    """Send every clause to the configured LLM for playbook-grounded review.

    The LLM provider and (optional) API key are threaded through
    ``state.metadata`` so the UI can override them per request without
    touching environment variables.

    Each call returns a structured ``ClauseReview`` containing:
      - ``risk_level``   – low / medium / high
      - ``issue_type``   – short category label
      - ``rationale``    – plain-English explanation
      - ``suggested_text`` – revised clause text (may equal the original)
      - ``confidence``   – float 0–1 indicating model certainty

    Results are collected on ``state.reviews``.
    """
    playbook = load_playbook()
    meta = state.metadata
    api_key = meta.get("openai_api_key") if meta.get("provider") == "openai" else meta.get("gemini_api_key")
    client = get_llm_client(
        provider=meta.get("provider"),
        api_key=api_key,
    )
    reviews: list[ClauseReview] = []
    for clause in state.clauses:
        result = await client.review_clause(clause.title, clause.text, playbook)
        reviews.append(
            ClauseReview(
                clause_id=clause.clause_id,
                title=clause.title,
                risk_level=result["risk_level"],
                issue_type=result["issue_type"],
                rationale=result["rationale"],
                suggested_text=result["suggested_text"],
                confidence=float(result.get("confidence", 0.9)),
            )
        )
    state.reviews = reviews
    return state


async def create_redlines(state: ContractState) -> ContractState:
    """Convert LLM reviews into concrete redline entries.

    Only clauses where the LLM's ``suggested_text`` differs from the
    original produce a ``RedlineEntry``; unchanged clauses are skipped.
    The entries are stored on ``state.redlines`` and later exported to
    the DOCX track-changes format.
    """
    clause_map = {c.clause_id: c for c in state.clauses}
    redlines: list[RedlineEntry] = []
    for review in state.reviews:
        original = clause_map[review.clause_id].text
        if review.suggested_text != original:
            redlines.append(
                RedlineEntry(
                    clause_id=review.clause_id,
                    title=review.title,
                    original_text=original,
                    suggested_text=review.suggested_text,
                    reason=review.rationale,
                    risk_level=review.risk_level,
                    confidence=review.confidence,
                )
            )
    state.redlines = redlines
    return state


def gate(state: ContractState) -> str:
    """Routing function: decide whether the review needs human escalation.

    Returns ``"escalate"`` when any of the following is true:
      - At least one clause is rated ``high`` risk.
      - Any clause has model confidence below 0.75 (uncertain output).

    Returns ``"summarize"`` when all clauses are within policy bounds and
    the model is sufficiently confident.
    """
    has_high = any(r.risk_level == "high" for r in state.reviews)
    low_conf = any(r.confidence < 0.75 for r in state.reviews)
    return "escalate" if has_high or low_conf else "summarize"


async def escalate(state: ContractState) -> ContractState:
    """Terminal node: flag the review for mandatory human legal review.

    Sets ``state.escalated = True`` and writes a summary that downstream
    consumers (API, UI) surface to the reviewer.
    """
    state.escalated = True
    state.final_summary = (
        f"Reviewed {len(state.clauses)} clauses, proposed {len(state.redlines)} redlines, "
        "and escalated to human legal review."
    )
    return state


async def summarize(state: ContractState) -> ContractState:
    """Terminal node: mark the review as auto-approved within policy.

    Sets ``state.escalated = False`` and writes a summary confirming that
    no mandatory escalation was triggered.
    """
    state.escalated = False
    state.final_summary = (
        f"Reviewed {len(state.clauses)} clauses and proposed {len(state.redlines)} redlines. "
        "No mandatory escalation triggered."
    )
    return state


def build_graph():
    """Compile the LangGraph state machine.

    Nodes are wired in a linear chain with a single conditional branch at
    ``create_redlines``.  The compiled graph is stateless and safe to
    share across concurrent ``ainvoke`` calls.

    Returns:
        A compiled ``CompiledGraph`` ready for ``await graph.ainvoke(...)``.
    """
    graph = StateGraph(ContractState)
    graph.add_node("ingest", ingest)
    graph.add_node("extract_clauses", extract_clauses)
    graph.add_node("review_clauses", review_clauses)
    graph.add_node("create_redlines", create_redlines)
    graph.add_node("escalate", escalate)
    graph.add_node("summarize", summarize)
    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "extract_clauses")
    graph.add_edge("extract_clauses", "review_clauses")
    graph.add_edge("review_clauses", "create_redlines")
    graph.add_conditional_edges("create_redlines", gate, {"escalate": "escalate", "summarize": "summarize"})
    graph.add_edge("escalate", END)
    graph.add_edge("summarize", END)
    return graph.compile()
