"""OpenAI LLM client using the Responses API (``/v1/responses``).

Uses ``httpx`` for async HTTP and ``tenacity`` for automatic retries on
transient failures (rate limits, timeouts).  JSON fences in the model
output are stripped before parsing to handle responses that wrap JSON
in markdown code blocks.
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


class OpenAIClient(LLMClient):
    """Calls OpenAI's Responses API to review a single NDA clause.

    Retries up to 3 times with exponential back-off on HTTP errors and
    timeouts before surfacing the exception to the caller.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        """
        Args:
            api_key: Overrides ``OPENAI_API_KEY`` for this instance.
            model:   Overrides ``OPENAI_MODEL`` (default: ``gpt-4.1-mini``).
        """
        self._api_key = api_key
        self._model = model

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def review_clause(self, title: str, text: str, playbook: dict) -> dict:
        """Send a clause to the OpenAI Responses API and parse the result.

        Constructs a two-message input (system + user) containing the
        playbook, clause title, and clause body.  Expects the model to
        return strict JSON matching the ``ClauseReview`` schema.

        Args:
            title:    Clause heading for context.
            text:     Full clause body to be reviewed.
            playbook: Policy rules loaded from ``data/playbook.json``.

        Returns:
            Parsed dict with ``risk_level``, ``issue_type``, ``rationale``,
            ``suggested_text``, and ``confidence``.

        Raises:
            RuntimeError:            ``OPENAI_API_KEY`` is not set.
            httpx.HTTPStatusError:   Non-2xx response after all retries.
            json.JSONDecodeError:    Model returned malformed JSON.
        """
        settings = get_settings()
        api_key = self._api_key or settings.openai_api_key
        model = self._model or settings.openai_model
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"{REVIEW_PROMPT}\n\n"
                        f"Playbook: {json.dumps(playbook)}\n\n"
                        f"Clause title: {title}\n"
                        f"Clause text: {text}\n"
                        f"Return JSON only. No markdown."
                    ),
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        logger.debug("OpenAI request: model=%s clause=%s", model, title)
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
        raw = data.get("output", [{}])[0].get("content", [{}])[0].get("text", "{}")
        logger.debug("OpenAI raw response: %s", raw[:200])
        return json.loads(_strip_fences(raw))
