"""Text processing utilities for clause extraction and diff generation."""
from __future__ import annotations

import re
from difflib import SequenceMatcher


def split_into_clauses(document: str) -> list[tuple[str, str]]:
    """Split a contract document into (title, body) clause pairs.

    Sections are delimited by one or more blank lines.  The first line of
    each section becomes the title (capped at 120 characters); the
    remaining lines form the body.  If a section has only one line it is
    used as both title and body so no content is lost.

    Args:
        document: Raw contract text with double-newline section breaks.

    Returns:
        Ordered list of ``(title, body)`` tuples, one per clause.
    """
    sections = [s.strip() for s in re.split(r"\n\s*\n", document) if s.strip()]
    result: list[tuple[str, str]] = []
    for idx, section in enumerate(sections, start=1):
        lines = [l for l in section.splitlines() if l.strip()]
        title = lines[0][:120] if lines else f"Clause {idx}"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else section
        result.append((title, body or section))
    return result


def inline_diff_tokens(old: str, new: str) -> list[tuple[str, str]]:
    """Compute a word-level diff between two strings.

    Uses ``difflib.SequenceMatcher`` on word tokens.  ``"replace"``
    operations are decomposed into a ``"delete"`` followed by an
    ``"insert"`` so callers receive only three unambiguous kinds.

    Args:
        old: Original clause text (before AI suggestion).
        new: Suggested clause text (after AI suggestion).

    Returns:
        List of ``(kind, text)`` tuples where ``kind`` is one of:

        - ``"equal"``  – unchanged words
        - ``"delete"`` – words present in ``old`` but not ``new``
        - ``"insert"`` – words present in ``new`` but not ``old``

        Empty-text entries are filtered out.
    """
    old_words = old.split()
    new_words = new.split()
    matcher = SequenceMatcher(a=old_words, b=new_words)
    chunks: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            chunks.append(("equal", " ".join(old_words[i1:i2])))
        elif tag == "delete":
            chunks.append(("delete", " ".join(old_words[i1:i2])))
        elif tag == "insert":
            chunks.append(("insert", " ".join(new_words[j1:j2])))
        elif tag == "replace":
            chunks.append(("delete", " ".join(old_words[i1:i2])))
            chunks.append(("insert", " ".join(new_words[j1:j2])))
    return [c for c in chunks if c[1]]
