from __future__ import annotations

import io
import json
import os
from pathlib import Path

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "https://contract-redliner-pro.fly.dev")
SAMPLE = Path(__file__).resolve().parents[3] / "data" / "nda_sample.txt"
LOGO = Path(__file__).resolve().parents[4] / "assets" / "cf_logo.png"

st.set_page_config(
    page_title="Contract Redliner Pro",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), use_container_width=True)
    st.title("⚖️ Contract Redliner Pro")
    st.caption("AI-powered NDA redlining")
    st.divider()

    st.subheader("LLM Provider")
    provider = st.selectbox(
        "Provider",
        options=["mock", "openai", "gemini"],
        index=0,
        help="'mock' works offline for demos. OpenAI / Gemini require an API key.",
    )
    openai_api_key: str | None = None
    gemini_api_key: str | None = None

    if provider == "openai":
        openai_api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=os.getenv("OPENAI_API_KEY", ""),
            placeholder="sk-...",
        )
        st.caption("Uses gpt-4.1-mini via Responses API")
    elif provider == "gemini":
        gemini_api_key = st.text_input(
            "Gemini API Key",
            type="password",
            value=os.getenv("GEMINI_API_KEY", ""),
            placeholder="AIza...",
        )
        st.caption("Uses gemini-2.5-flash")

    st.divider()
    st.subheader("Upload Contract")
    uploaded = st.file_uploader(
        "Upload .txt, .md, or .docx",
        type=["txt", "md", "docx"],
        help="Overrides the text editor below",
    )

    st.divider()
    st.subheader("Export")
    docx_title = st.text_input("DOCX title", value="Redlined Contract")

    # Health check indicator
    st.divider()
    try:
        hc = requests.get(f"{API_BASE}/health", timeout=3)
        if hc.ok:
            info = hc.json()
            st.success(f"API online · {info.get('provider', '?')} provider")
        else:
            st.warning("API returned non-OK status")
    except Exception:
        st.error("API offline — start with `uvicorn contract_redliner.api.main:app`")

# ── Main area ──────────────────────────────────────────────────────────────────
hcol1, hcol2 = st.columns([1, 4])
with hcol1:
    if LOGO.exists():
        st.image(str(LOGO), use_container_width=True)
with hcol2:
    st.header("Contract Review")
    st.caption("Powered by Contract Redliner Pro")

# Text input: file upload wins if present
if uploaded:
    raw_bytes = uploaded.read()
    if uploaded.name.endswith(".docx"):
        # Let the API handle DOCX parsing — send as file upload
        contract_text = None
        contract_bytes = raw_bytes
        contract_filename = uploaded.name
    else:
        contract_text = raw_bytes.decode("utf-8", errors="ignore")
        contract_bytes = None
        contract_filename = None
else:
    default_text = SAMPLE.read_text(encoding="utf-8") if SAMPLE.exists() else ""
    contract_text = st.text_area(
        "Contract text",
        value=default_text,
        height=360,
        help="Paste or edit your NDA here, or upload a file in the sidebar.",
    )
    contract_bytes = None
    contract_filename = None

col_run, col_clear = st.columns([1, 5])
with col_run:
    run = st.button("▶ Review", type="primary", use_container_width=True)
with col_clear:
    if st.button("Clear results", use_container_width=False):
        st.session_state.pop("review_data", None)
        st.rerun()

# ── Run review ─────────────────────────────────────────────────────────────────
if run:
    with st.spinner("Running AI review…"):
        try:
            if contract_bytes is not None:
                # File upload path (DOCX)
                resp = requests.post(
                    f"{API_BASE}/review/file",
                    files={"file": (contract_filename, io.BytesIO(contract_bytes))},
                    timeout=180,
                )
            else:
                payload: dict = {"document_text": contract_text, "provider": provider}
                if openai_api_key:
                    payload["openai_api_key"] = openai_api_key
                if gemini_api_key:
                    payload["gemini_api_key"] = gemini_api_key
                resp = requests.post(f"{API_BASE}/review/text", json=payload, timeout=180)
            resp.raise_for_status()
            st.session_state["review_data"] = resp.json()
        except requests.HTTPError as exc:
            try:
                detail = exc.response.json().get("detail", str(exc))
            except Exception:
                detail = str(exc)
            st.error(f"Review failed: {detail}")
        except requests.ConnectionError:
            st.error("Cannot reach the API. Is the backend running?")

# ── Results dashboard ──────────────────────────────────────────────────────────
if "review_data" in st.session_state:
    data = st.session_state["review_data"]
    reviews: list[dict] = data.get("reviews", [])
    redlines: list[dict] = data.get("redlines", [])
    escalated: bool = data.get("escalated", False)

    risk_counts = {"high": 0, "medium": 0, "low": 0}
    for r in reviews:
        lvl = r.get("risk_level", "low")
        risk_counts[lvl] = risk_counts.get(lvl, 0) + 1

    # ── Metric strip ──
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Clauses reviewed", len(reviews))
    m2.metric("Redlines proposed", len(redlines))
    m3.metric("High risk", risk_counts["high"], delta=None)
    m4.metric("Medium risk", risk_counts["medium"], delta=None)
    m5.metric("Escalated", "Yes" if escalated else "No")

    # Summary banner
    if escalated:
        st.warning(f"🔴 **Escalated to human review** — {data.get('summary', '')}")
    else:
        st.success(f"✅ {data.get('summary', '')}")

    # Risk distribution chart
    if reviews:
        st.subheader("Risk distribution")
        chart_data = {"Risk level": ["High", "Medium", "Low"], "Clauses": [risk_counts["high"], risk_counts["medium"], risk_counts["low"]]}
        import pandas as pd
        df = pd.DataFrame(chart_data).set_index("Risk level")
        st.bar_chart(df, color=["#e53935"])

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_red, tab_all, tab_json = st.tabs(["📝 Redlines", "🔍 All Reviews", "{ } Raw JSON"])

    with tab_red:
        if redlines:
            for r in redlines:
                risk = r["risk_level"].upper()
                badge = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}.get(risk, "⚪")
                with st.expander(f"{badge} {r['title']} — {risk}  ·  conf {r['confidence']:.0%}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Original**")
                        st.code(r["original_text"], language=None)
                    with c2:
                        st.markdown("**Suggested**")
                        st.code(r["suggested_text"], language=None)
                    st.info(f"**Reason:** {r['reason']}")
        else:
            st.info("No redlines — contract aligns with playbook.")

    with tab_all:
        for r in reviews:
            risk = r["risk_level"].upper()
            badge = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}.get(risk, "⚪")
            with st.expander(f"{badge} {r['title']} — {risk}"):
                st.markdown(f"**Issue type:** {r.get('issue_type', '—')}")
                st.markdown(f"**Rationale:** {r.get('rationale', '—')}")
                st.markdown(f"**Confidence:** {r.get('confidence', 0):.0%}")

    with tab_json:
        st.json(data)

    # ── DOCX export ───────────────────────────────────────────────────────────
    st.divider()
    if redlines:
        if st.button("📄 Generate tracked DOCX", type="secondary"):
            with st.spinner("Building DOCX…"):
                try:
                    exp_resp = requests.post(
                        f"{API_BASE}/export/docx",
                        json={"title": docx_title, "redlines": redlines},
                        timeout=60,
                    )
                    exp_resp.raise_for_status()
                    st.session_state["docx_bytes"] = exp_resp.content
                except requests.HTTPError as exc:
                    st.error(f"Export failed: {exc}")

        if "docx_bytes" in st.session_state:
            st.download_button(
                label="⬇ Download redlined_contract.docx",
                data=st.session_state["docx_bytes"],
                file_name="redlined_contract.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
            )
    else:
        st.info("No redlines to export.")
