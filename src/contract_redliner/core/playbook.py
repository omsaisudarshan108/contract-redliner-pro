"""Loader for the company NDA policy playbook.

The playbook (``data/playbook.json``) defines the approved parameters
used to ground all LLM reviews — approved confidentiality term,
acceptable jurisdictions, preferred governing law, and venue.  It is
loaded fresh on each workflow invocation so changes to the JSON file
take effect without restarting the server.
"""
from __future__ import annotations

import json
from pathlib import Path


PLAYBOOK_PATH = Path(__file__).resolve().parents[3] / "data" / "playbook.json"


def load_playbook() -> dict:
    """Read and return the current policy playbook from disk.

    Returns:
        Parsed JSON dict, e.g.::

            {
                "approved_confidentiality_term": "three (3) years",
                "approved_jurisdictions": ["New York", "Delaware", ...],
                "preferred_governing_law": "New York",
                "preferred_venue": "New York County, New York",
                ...
            }

    Raises:
        FileNotFoundError: If ``data/playbook.json`` does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
