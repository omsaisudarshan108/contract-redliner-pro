"""Google Gemini LLM client using the generativelanguage REST API.

Uses ``httpx`` for async HTTP and ``tenacity`` for automatic retries.
Sends a ``system_instruction`` alongside the user prompt and requests
``application/json`` as the response MIME type, which reduces (but does
not eliminate) the need to strip markdown fences from the output.
"""
from __future__ import annotations

import json
import logging
import re
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from contract_redliner.integrations.llm_base import LLMClient
from contract_redliner.core.config import get_settings
from contract_redliner.core.prompts import SYSTEM_PROMPT, REVIEW_PROMPT

logger = logging.getLogger(__name__)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that wrap JSON in LLM output.

    Handles both `` ```json `` and plain `` ``` `` variants.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


class GeminiClient(LLMClient):
    """Calls the Gemini ``generateContent`` endpoint to review an NDA clause.

    Retries up to 3 times with exponential back-off on HTTP errors and
    timeouts before surfacing the exception to the caller.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """
        Args:
            api_key: Overrides ``GEMINI_API_KEY`` for this instance.
            model:   Overrides ``GEMINI_MODEL`` (default: ``gemini-2.5-flash``).
        """
        self._api_key = api_key
        self._model = model

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def review_clause(self, title: str, text: str, playbook: dict) -> dict:
        """Send a clause to the Gemini generateContent API and parse the result.

        Uses ``system_instruction`` for the legal AI persona and passes the
        review prompt, playbook, and clause in the user ``contents``.
        ``generationConfig.responseMimeType`` is set to ``application/json``
        to nudge the model toward clean JSON output.

        Args:
            title:    Clause heading for context.
            text:     Full clause body to be reviewed.
            playbook: Policy rules loaded from ``data/playbook.json``.

        Returns:
            Parsed dict with ``risk_level``, ``issue_type``, ``rationale``,
            ``suggested_text``, and ``confidence``.

        Raises:
            RuntimeError:            ``GEMINI_API_KEY`` is not set.
            httpx.HTTPStatusError:   Non-2xx response after all retries.
            json.JSONDecodeError:    Model returned malformed JSON.
        """
        settings = get_settings()
        api_key = self._api_key or settings.gemini_api_key
        model = self._model or settings.gemini_model
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                f"{REVIEW_PROMPT}\n\n"
                                f"Playbook: {json.dumps(playbook)}\n\n"
                                f"Clause title: {title}\n"
                                f"Clause text: {text}\n"
                                f"Return JSON only. No markdown."
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        logger.debug("Gemini request: model=%s clause=%s", model, title)
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        logger.debug("Gemini raw response: %s", raw[:200])
        return json.loads(_strip_fences(raw))
