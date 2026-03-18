"""DOCX generator that embeds Word track-change markup (revisions).

Produces a well-formed ``.docx`` ZIP archive containing:
  - ``word/document.xml``            – body with ``<w:ins>`` / ``<w:del>`` revision runs
  - ``word/styles.xml``              – Title and Heading1 paragraph styles
  - ``word/_rels/document.xml.rels`` – relationship to styles (required by Word)
  - ``[Content_Types].xml``          – OOXML part declarations
  - ``_rels/.rels``                  – package-level relationships
  - ``docProps/core.xml``            – document metadata (title, author, timestamps)
  - ``docProps/app.xml``             – application metadata

Track changes use word-level diffs so reviewers can accept or reject each
token individually inside Microsoft Word or LibreOffice Writer.
"""
from __future__ import annotations

import html
import io
import zipfile
from datetime import datetime, timezone
from lxml import etree

from contract_redliner.core.models import RedlineEntry
from contract_redliner.utils.text import inline_diff_tokens

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W_NS}


def _w(tag: str) -> str:
    """Return the fully qualified ``{namespace}tag`` name for a Word XML element."""
    return f"{{{W_NS}}}{tag}"


def _run(text: str, bold: bool = False):
    """Build a ``<w:r>`` (run) element containing plain text.

    Preserves leading/trailing whitespace via ``xml:space="preserve"`` when
    the text starts or ends with a space.

    Args:
        text: The literal text content.
        bold: When ``True``, wraps the run in ``<w:rPr><w:b/></w:rPr>``.
    """
    r = etree.Element(_w("r"))
    if bold:
        rpr = etree.SubElement(r, _w("rPr"))
        etree.SubElement(rpr, _w("b"))
    t = etree.SubElement(r, _w("t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return r


def _ins(text: str, idx: int):
    """Build a ``<w:ins>`` revision run marking inserted text.

    Word renders inserted text in the review pane and colour-codes it as an
    addition.  Each revision needs a unique ``w:id`` within the document.

    Args:
        text: The inserted word or token.
        idx:  Unique integer revision ID for this change.
    """
    ins = etree.Element(_w("ins"))
    ins.set(_w("id"), str(idx))
    ins.set(_w("author"), "AI Redliner")
    ins.set(_w("date"), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    ins.append(_run(text))
    return ins


def _delete(text: str, idx: int):
    """Build a ``<w:del>`` revision run marking deleted text.

    Word renders deleted text as strikethrough in the review pane.
    Text goes inside ``<w:delText>`` (not ``<w:t>``) per the OOXML spec.

    Args:
        text: The deleted word or token.
        idx:  Unique integer revision ID for this change.
    """
    deletion = etree.Element(_w("del"))
    deletion.set(_w("id"), str(idx))
    deletion.set(_w("author"), "AI Redliner")
    deletion.set(_w("date"), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    r = etree.SubElement(deletion, _w("r"))
    dt = etree.SubElement(r, _w("delText"))
    if text.startswith(" ") or text.endswith(" "):
        dt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    dt.text = text
    return deletion


def _risk_color(risk_level: str) -> str:
    """Map a risk level to a six-digit hex RGB colour for heading text.

    Returns:
        ``"FF0000"`` (red) for high, ``"FF8C00"`` (orange) for medium,
        ``"107C10"`` (green) for low, ``"000000"`` (black) as fallback.
    """
    return {"high": "FF0000", "medium": "FF8C00", "low": "107C10"}.get(risk_level, "000000")


def export_docx_with_track_changes(title: str, redlines: list[RedlineEntry]) -> bytes:
    """Build a ``.docx`` file with Word track-change markup for each redline.

    For each ``RedlineEntry`` the function:
      1. Emits a colour-coded ``Heading1`` paragraph with the clause title
         and risk badge (e.g. ``"3. Governing Law [HIGH]"``).
      2. Produces an inline word-diff paragraph using ``<w:ins>`` /
         ``<w:del>`` elements so reviewers can accept/reject per token.
      3. Appends a plain-text "Reason:" paragraph with the AI rationale
         and a "Confidence:" line showing the model's certainty.

    Args:
        title:    Document title written in the ``Title``-styled first paragraph
                  and in ``docProps/core.xml``.
        redlines: Ordered list of redlines to include; each must have
                  ``original_text``, ``suggested_text``, ``reason``,
                  ``risk_level``, and ``confidence``.

    Returns:
        Raw bytes of a valid ``.docx`` (ZIP/OOXML) archive ready for
        ``Content-Type: application/vnd.openxmlformats-officedocument…``.
    """
    body = etree.Element(_w("body"), nsmap=NSMAP)

    # ── Title paragraph ───────────────────────────────────────────────────────
    p_title = etree.SubElement(body, _w("p"))
    ppr = etree.SubElement(p_title, _w("pPr"))
    ps = etree.SubElement(ppr, _w("pStyle"))
    ps.set(_w("val"), "Title")
    p_title.append(_run(title))

    rid = 1  # Monotonically increasing revision ID across the whole document.
    for redline in redlines:
        # ── Section heading with risk colour ──────────────────────────────────
        p1 = etree.SubElement(body, _w("p"))
        ppr1 = etree.SubElement(p1, _w("pPr"))
        ps1 = etree.SubElement(ppr1, _w("pStyle"))
        ps1.set(_w("val"), "Heading1")
        r_head = etree.SubElement(p1, _w("r"))
        rpr_head = etree.SubElement(r_head, _w("rPr"))
        color_el = etree.SubElement(rpr_head, _w("color"))
        color_el.set(_w("val"), _risk_color(redline.risk_level))
        t_head = etree.SubElement(r_head, _w("t"))
        t_head.text = f"{redline.title} [{redline.risk_level.upper()}]"

        # ── Word-level diff paragraph ─────────────────────────────────────────
        p2 = etree.SubElement(body, _w("p"))
        for kind, tok in inline_diff_tokens(redline.original_text, redline.suggested_text):
            token_text = tok if tok.endswith(" ") else tok + " "
            if kind == "equal":
                p2.append(_run(token_text))
            elif kind == "insert":
                p2.append(_ins(token_text, rid))
                rid += 1
            elif kind == "delete":
                p2.append(_delete(token_text, rid))
                rid += 1

        # ── Rationale and confidence ──────────────────────────────────────────
        p3 = etree.SubElement(body, _w("p"))
        p3.append(_run("Reason: ", bold=True))
        p3.append(_run(redline.reason))

        p4 = etree.SubElement(body, _w("p"))
        p4.append(_run("Confidence: ", bold=True))
        p4.append(_run(f"{redline.confidence:.0%}"))

        etree.SubElement(body, _w("p"))  # Visual spacer between redlines.

    # ── Page layout (letter size, 1-inch margins) ─────────────────────────────
    sect = etree.SubElement(body, _w("sectPr"))
    pg_sz = etree.SubElement(sect, _w("pgSz"))
    pg_sz.set(_w("w"), "12240")   # 8.5 in × 1440 twips/in
    pg_sz.set(_w("h"), "15840")   # 11  in × 1440 twips/in
    pg_mar = etree.SubElement(sect, _w("pgMar"))
    for attr, val in [("top", "1440"), ("right", "1440"), ("bottom", "1440"),
                      ("left", "1440"), ("header", "720"), ("footer", "720"), ("gutter", "0")]:
        pg_mar.set(attr, val)

    document = etree.Element(_w("document"), nsmap=NSMAP)
    document.append(body)
    xml_bytes = etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone=True)

    # ── OOXML package parts ───────────────────────────────────────────────────
    content_types = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''

    rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

    # Without this file Word silently ignores styles.xml.
    word_rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

    styles = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:after="240"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="52"/><w:szCs w:val="52"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr>
  </w:style>
</w:styles>'''

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{html.escape(title)}</dc:title>
  <dc:creator>Contract Redliner Pro</dc:creator>
  <cp:lastModifiedBy>AI Redliner</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>'''.encode("utf-8")

    app = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Contract Redliner Pro</Application>
</Properties>'''

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", word_rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("word/document.xml", xml_bytes)
        z.writestr("word/styles.xml", styles)
    return buf.getvalue()
