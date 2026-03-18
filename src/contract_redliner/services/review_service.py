"""Orchestration layer between the FastAPI routes and the LangGraph workflow.

This module is the single entry point for triggering a contract review.
It owns the compiled graph singleton, translates raw bytes / text into
``ContractState``, invokes the workflow, and returns a ``ReviewResponse``
ready for serialisation.
"""
from __future__ import annotations

from pathlib import Path

from contract_redliner.agents.workflow import build_graph
from contract_redliner.core.models import ContractState, ReviewResponse

# Compiled once at import time; safe to reuse across concurrent requests.
graph = build_graph()


async def review_text(
    document_text: str,
    provider: str | None = None,
    openai_api_key: str | None = None,
    gemini_api_key: str | None = None,
) -> ReviewResponse:
    """Run the full redlining workflow against plain contract text.

    Provider credentials supplied here take precedence over environment
    variables, enabling per-request LLM selection from the UI without
    restarting the server.

    Args:
        document_text:  Raw NDA text to be reviewed.
        provider:       ``"openai"``, ``"gemini"``, or ``"mock"``.
                        Defaults to the ``LLM_PROVIDER`` environment variable.
        openai_api_key: Override for ``OPENAI_API_KEY``.
        gemini_api_key: Override for ``GEMINI_API_KEY``.

    Returns:
        ``ReviewResponse`` with summary, escalation flag, all clause
        reviews, and actionable redlines.
    """
    metadata: dict = {}
    if provider:
        metadata["provider"] = provider
    if openai_api_key:
        metadata["openai_api_key"] = openai_api_key
    if gemini_api_key:
        metadata["gemini_api_key"] = gemini_api_key

    raw = await graph.ainvoke(
        ContractState(raw_document=document_text, metadata=metadata)
    )
    # LangGraph 1.x returns a dict; coerce back to the typed model.
    result = ContractState.model_validate(raw) if isinstance(raw, dict) else raw
    return ReviewResponse(
        summary=result.final_summary or "",
        escalated=result.escalated,
        reviews=result.reviews,
        redlines=result.redlines,
    )


async def review_file_bytes(filename: str, content: bytes, **kwargs) -> ReviewResponse:
    """Extract text from an uploaded file and delegate to ``review_text``.

    Supported formats:
      - ``.txt`` / ``.md`` – decoded as UTF-8 directly.
      - ``.docx``          – paragraphs joined with double newlines via
                             ``python-docx``.
      - anything else      – best-effort UTF-8 decode with error replacement.

    Args:
        filename: Original filename; used only for extension detection.
        content:  Raw file bytes from the multipart upload.
        **kwargs: Forwarded verbatim to ``review_text`` (provider, keys).

    Returns:
        ``ReviewResponse`` identical to calling ``review_text`` directly.
    """
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        text = content.decode("utf-8", errors="ignore")
    elif suffix == ".docx":
        from docx import Document
        import io
        doc = Document(io.BytesIO(content))
        text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        text = content.decode("utf-8", errors="ignore")
    return await review_text(text, **kwargs)
