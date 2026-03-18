"""DOCX generator that embeds Word track-change markup (revisions).

Produces a well-formed ``.docx`` ZIP archive containing:
  - ``word/document.xml``            – body with ``<w:ins>`` / ``<w:del>`` revision runs
  - ``word/settings.xml``            – enables Track Changes view on open (w:trackChanges)
  - ``word/styles.xml``              – Title, Heading1, and Heading2 paragraph styles
  - ``word/_rels/document.xml.rels`` – relationships to styles and settings
  - ``[Content_Types].xml``          – OOXML part declarations
  - ``_rels/.rels``                  – package-level relationships
  - ``docProps/core.xml``            – document metadata (title, author, timestamps)
  - ``docProps/app.xml``             – application metadata

Track changes use word-level diffs so reviewers can accept or reject each
token individually inside Microsoft Word or LibreOffice Writer.

Multi-user attribution: the ``w:author`` attribute on every ``<w:ins>`` and
``<w:del>`` is taken from ``RedlineEntry.changed_by``.  Word automatically
assigns a distinct colour to each unique author, so changes from different
reviewers are visually separated in the markup panel.
"""
from __future__ import annotations

import html
import io
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from lxml import etree

from contract_redliner.core.models import RedlineEntry
from contract_redliner.utils.text import inline_diff_tokens

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W_NS}
_NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _w(tag: str) -> str:
    """Return the fully qualified ``{namespace}tag`` name for a Word XML element."""
    return f"{{{W_NS}}}{tag}"


def _run(text: str, bold: bool = False, italic: bool = False, color: str | None = None):
    """Build a ``<w:r>`` run element containing plain text.

    Preserves leading/trailing whitespace via ``xml:space="preserve"``.

    Args:
        text:   Literal text content.
        bold:   Apply ``<w:b/>`` character property.
        italic: Apply ``<w:i/>`` character property.
        color:  Six-digit hex RGB colour string (e.g. ``"FF0000"``), or ``None``.
    """
    r = etree.Element(_w("r"))
    if bold or italic or color:
        rpr = etree.SubElement(r, _w("rPr"))
        if bold:
            etree.SubElement(rpr, _w("b"))
        if italic:
            etree.SubElement(rpr, _w("i"))
        if color:
            c = etree.SubElement(rpr, _w("color"))
            c.set(_w("val"), color)
    t = etree.SubElement(r, _w("t"))
    if text.startswith(" ") or text.endswith(" "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return r


def _ins(text: str, idx: int, author: str):
    """Build a ``<w:ins>`` revision run marking inserted text.

    Word renders inserted text underlined in the colour assigned to ``author``
    and lists it in the Review › Tracking pane.

    Args:
        text:   The inserted token.
        idx:    Document-unique revision ID.
        author: Reviewer name shown in the Word comment balloon and markup panel.
    """
    ins = etree.Element(_w("ins"))
    ins.set(_w("id"), str(idx))
    ins.set(_w("author"), author)
    ins.set(_w("date"), _NOW)
    ins.append(_run(text))
    return ins


def _delete(text: str, idx: int, author: str):
    """Build a ``<w:del>`` revision run marking deleted text.

    Word renders deleted text as strikethrough in the colour assigned to
    ``author``.  Text goes inside ``<w:delText>`` per the OOXML spec.

    Args:
        text:   The deleted token.
        idx:    Document-unique revision ID.
        author: Reviewer name shown in the Word comment balloon and markup panel.
    """
    deletion = etree.Element(_w("del"))
    deletion.set(_w("id"), str(idx))
    deletion.set(_w("author"), author)
    deletion.set(_w("date"), _NOW)
    r = etree.SubElement(deletion, _w("r"))
    dt = etree.SubElement(r, _w("delText"))
    if text.startswith(" ") or text.endswith(" "):
        dt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    dt.text = text
    return deletion


def _risk_color(risk_level: str) -> str:
    """Map a risk level to a six-digit hex RGB colour for heading text.

    Returns:
        ``"C00000"`` (dark red) for high, ``"C55A11"`` (dark orange) for
        medium, ``"375623"`` (dark green) for low, ``"000000"`` as fallback.
    """
    return {"high": "C00000", "medium": "C55A11", "low": "375623"}.get(risk_level, "000000")


def _para(body, style: str | None = None) -> etree._Element:
    """Append and return an empty ``<w:p>`` paragraph, optionally styled."""
    p = etree.SubElement(body, _w("p"))
    if style:
        ppr = etree.SubElement(p, _w("pPr"))
        ps = etree.SubElement(ppr, _w("pStyle"))
        ps.set(_w("val"), style)
    return p


def _reviewer_summary(body, redlines: list[RedlineEntry]) -> None:
    """Write a 'Reviewers' section listing each author and their change count.

    Word colour-codes each unique ``w:author`` value independently, so this
    table helps readers map colours to names before diving into the redlines.
    """
    counts: dict[str, int] = defaultdict(int)
    for r in redlines:
        counts[r.changed_by] += 1

    h = _para(body, style="Heading2")
    h.append(_run("Reviewers"))

    for author, n in sorted(counts.items()):
        p = _para(body)
        p.append(_run(f"  • {author}", bold=True))
        p.append(_run(f"  —  {n} change{'s' if n != 1 else ''}"))

    etree.SubElement(body, _w("p"))  # spacer


def export_docx_with_track_changes(
    title: str,
    redlines: list[RedlineEntry],
    reviewer: str | None = None,
) -> bytes:
    """Build a ``.docx`` with Word track-change markup attributed per reviewer.

    When the document is opened in Microsoft Word or LibreOffice, it
    automatically opens in "All Markup" view because ``word/settings.xml``
    contains ``<w:trackChanges/>``.  Each unique ``changed_by`` value
    receives a distinct colour in the Track Changes panel.

    Structure per redline:
      1. **Heading** — clause title + risk badge, coloured by severity.
      2. **Diff paragraph** — ``<w:ins>`` / ``<w:del>`` tokens at word
         granularity, attributed to ``redline.changed_by``.
      3. **Reason** — AI rationale in plain text.
      4. **Confidence** — model certainty percentage.

    Args:
        title:    Document title (``Title`` style + ``core.xml`` metadata).
        redlines: Ordered list of proposed changes to embed.
        reviewer: Optional human reviewer name.  When supplied, overrides
                  ``changed_by`` on every redline so the exported document
                  is attributed to the named person rather than ``"AI"``.

    Returns:
        Raw bytes of a valid ``.docx`` (ZIP/OOXML) archive.
    """
    # Apply reviewer override before building the document.
    if reviewer:
        redlines = [r.model_copy(update={"changed_by": reviewer}) for r in redlines]

    body = etree.Element(_w("body"), nsmap=NSMAP)

    # ── Cover: title ──────────────────────────────────────────────────────────
    p_title = _para(body, style="Title")
    p_title.append(_run(title))

    # ── Reviewer summary table ────────────────────────────────────────────────
    _reviewer_summary(body, redlines)

    rid = 1  # Monotonically increasing revision ID across the whole document.

    for redline in redlines:
        author = redline.changed_by

        # ── Clause heading (risk-coloured) ────────────────────────────────────
        p_head = _para(body, style="Heading1")
        rpr_head = etree.SubElement(etree.SubElement(p_head, _w("r")), _w("rPr"))  # build inline
        # Rebuild properly:
        p_head.remove(p_head[-1])
        r_head = etree.SubElement(p_head, _w("r"))
        rpr_h = etree.SubElement(r_head, _w("rPr"))
        col_h = etree.SubElement(rpr_h, _w("color"))
        col_h.set(_w("val"), _risk_color(redline.risk_level))
        t_head = etree.SubElement(r_head, _w("t"))
        t_head.text = f"{redline.title} [{redline.risk_level.upper()}]"

        # ── Attributed-by line ────────────────────────────────────────────────
        p_attr = _para(body)
        p_attr.append(_run("Reviewed by: ", bold=True))
        p_attr.append(_run(author, italic=True))

        # ── Word-level diff paragraph ─────────────────────────────────────────
        p_diff = _para(body)
        for kind, tok in inline_diff_tokens(redline.original_text, redline.suggested_text):
            token_text = tok if tok.endswith(" ") else tok + " "
            if kind == "equal":
                p_diff.append(_run(token_text))
            elif kind == "insert":
                p_diff.append(_ins(token_text, rid, author))
                rid += 1
            elif kind == "delete":
                p_diff.append(_delete(token_text, rid, author))
                rid += 1

        # ── Rationale and confidence ──────────────────────────────────────────
        p_reason = _para(body)
        p_reason.append(_run("Reason: ", bold=True))
        p_reason.append(_run(redline.reason))

        p_conf = _para(body)
        p_conf.append(_run("Confidence: ", bold=True))
        p_conf.append(_run(f"{redline.confidence:.0%}"))

        etree.SubElement(body, _w("p"))  # Visual spacer between redlines.

    # ── Page layout: US Letter, 1-inch margins ────────────────────────────────
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

    # ── settings.xml — forces Word to open in "All Markup" mode ──────────────
    # <w:trackChanges/> keeps the document in tracking mode.
    # <w:revisionView> with markup="1" ensures insertions and deletions are visible.
    settings = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:trackChanges/>
  <w:revisionView w:markup="1" w:comments="1" w:formatting="0"/>
  <w:showDfmtAttr/>
</w:settings>'''

    # ── OOXML package parts ───────────────────────────────────────────────────
    content_types = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/docProps/core.xml"
    ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml"
    ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''

    rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
  <Relationship Id="rId2"
    Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
    Target="docProps/core.xml"/>
  <Relationship Id="rId3"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
    Target="docProps/app.xml"/>
</Relationships>'''

    # word/_rels/document.xml.rels — Word requires both styles and settings here.
    word_rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
    Target="styles.xml"/>
  <Relationship Id="rId2"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings"
    Target="settings.xml"/>
</Relationships>'''

    styles_xml = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:after="240"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="56"/><w:szCs w:val="56"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:pPr><w:spacing w:before="360" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:pPr><w:spacing w:before="240" w:after="80"/></w:pPr>
    <w:rPr><w:b/><w:i/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr>
  </w:style>
</w:styles>'''

    reviewers_list = ", ".join(sorted({r.changed_by for r in redlines}))
    now = _NOW
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
  xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{html.escape(title)}</dc:title>
  <dc:creator>{html.escape(reviewers_list)}</dc:creator>
  <cp:lastModifiedBy>{html.escape(reviewers_list)}</cp:lastModifiedBy>
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
        z.writestr("word/styles.xml", styles_xml)
        z.writestr("word/settings.xml", settings)
    return buf.getvalue()
