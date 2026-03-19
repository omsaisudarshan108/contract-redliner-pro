from __future__ import annotations

import io
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

# ── Tour definition ────────────────────────────────────────────────────────────
TOUR_STEPS = [
    {
        "icon": "⚖️",
        "title": "Welcome to Contract Redliner Pro",
        "body": """
Contract Redliner Pro uses AI to automatically review NDAs against your
company's legal playbook — flagging risky clauses, proposing rewrites,
and exporting a Word document with full track-change markup.

**What you'll be able to do after this tour:**
- Review an NDA in seconds using AI
- Spot high, medium, and low-risk clauses at a glance
- Download a redlined `.docx` ready for Word review
        """,
        "tip": ("The sample NDA is pre-loaded so you can try everything without "
                "uploading your own document."),
        "tip_type": "info",
    },
    {
        "icon": "🤖",
        "title": "Step 1 — Choose your LLM provider",
        "body": """
Open the **sidebar on the left** and look for the **LLM Provider** section.

| Provider | When to use |
|---|---|
| **mock** | Instant offline demo — no API key needed |
| **openai** | Production reviews via GPT-4.1-mini |
| **gemini** | Production reviews via Gemini 2.5 Flash |

For OpenAI or Gemini, paste your API key in the field that appears.
The key is sent directly to the provider and never stored.
        """,
        "tip": "Start with **mock** to explore the interface — it triggers realistic "
               "risk findings on the pre-loaded NDA without any API cost.",
        "tip_type": "info",
    },
    {
        "icon": "📄",
        "title": "Step 2 — Load your contract",
        "body": """
You have two options:

**Option A — Use the text editor (default)**
The pre-loaded sample NDA is already in the editor.
Edit it freely or paste your own contract text.

**Option B — Upload a file**
In the sidebar, use **Upload Contract** to drag-and-drop a
`.txt`, `.md`, or `.docx` file. The uploaded file overrides the editor.

The sample NDA deliberately contains two policy violations so you can
see what a real redline looks like straight away.
        """,
        "tip": "The sample NDA has a **perpetual confidentiality term** (medium risk) "
               "and a **California jurisdiction clause** (high risk) — both will be caught.",
        "tip_type": "warning",
    },
    {
        "icon": "▶",
        "title": "Step 3 — Run the review",
        "body": """
Click the **▶ Review** button below the contract editor.

The AI will:
1. Split the document into individual clauses
2. Send each clause to the LLM with your policy playbook
3. Score each clause as **low / medium / high** risk
4. Propose revised text where the clause falls outside policy
5. Decide whether to escalate for human review

A spinner shows while the review runs (~2 s with mock, ~10–20 s with a live LLM).
        """,
        "tip": "If the API is on a cold start it may take a few extra seconds to wake up — "
               "just wait for the spinner to finish.",
        "tip_type": "info",
    },
    {
        "icon": "📊",
        "title": "Step 4 — Read the results",
        "body": """
Once the review completes you'll see:

**Metrics strip** — clauses reviewed, redlines proposed, risk counts, escalation flag.

**Summary banner** — green (auto-approved) or amber (escalated to legal).

**Risk chart** — bar chart of high / medium / low clause distribution.

**Three tabs:**
- 📝 **Redlines** — side-by-side original vs. suggested text with reason
- 🔍 **All Reviews** — every clause with its risk score and rationale
- **{ } Raw JSON** — full API response for debugging or downstream use
        """,
        "tip": "🔴 **HIGH** risk clauses always trigger escalation regardless of confidence. "
               "🟠 **MEDIUM** only escalates if model confidence drops below 75%.",
        "tip_type": "warning",
    },
    {
        "icon": "📥",
        "title": "Step 5 — Export a tracked Word document",
        "body": """
Scroll down past the tabs to the **Export** section.

1. Enter your **name** in the *Reviewer name* field in the sidebar —
   this stamps your name on every track change in Word.
2. Click **📄 Generate tracked DOCX**.
3. Click **⬇ Download** to save the file.

When you open the `.docx` in **Microsoft Word** or **LibreOffice Writer**,
it opens directly in **All Markup** view. Each reviewer's changes appear
in a distinct colour, and you can accept or reject them one by one.

Multiple team members can each export with their own name — Word
colour-codes them automatically.
        """,
        "tip": "Leave the reviewer name blank and the changes will be attributed to "
               "**AI Redliner** — useful when you want to make clear the suggestions "
               "are machine-generated and still pending human sign-off.",
        "tip_type": "info",
    },
    {
        "icon": "🎉",
        "title": "You're all set!",
        "body": """
Here's a quick recap of the full workflow:

```
1. Choose provider   →  sidebar: mock / openai / gemini
2. Load contract     →  paste text or upload a file
3. Click ▶ Review   →  AI analyses every clause
4. Read results      →  metrics, risk chart, redline tabs
5. Export DOCX       →  tracked changes, ready for Word review
```

**Need help or have feedback?**
Open an issue on [GitHub](https://github.com/omsaisudarshan108/contract-redliner-pro).

Hit **Close** to start reviewing contracts.
        """,
        "tip": "You can relaunch this tour any time from the **? Tour** button in the sidebar.",
        "tip_type": "success",
    },
]

TOTAL = len(TOUR_STEPS)


def _step_dots(current: int, total: int) -> str:
    """Render a progress dot indicator, e.g. ● ● ○ ○ ○."""
    return "  ".join("●" if i == current else "○" for i in range(total))


@st.dialog("Contract Redliner Pro — Tour", width="large")
def _show_tour() -> None:
    step = st.session_state.get("tour_step", 0)
    s = TOUR_STEPS[step]

    # Progress indicator
    st.markdown(
        f"<p style='text-align:center;letter-spacing:6px;color:#888;font-size:18px'>"
        f"{_step_dots(step, TOTAL)}</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p style='text-align:center;color:#aaa;font-size:12px;margin-top:-8px'>"
        f"Step {step + 1} of {TOTAL}</p>",
        unsafe_allow_html=True,
    )

    st.markdown(f"## {s['icon']}  {s['title']}")
    st.markdown(s["body"])

    tip_fn = {"info": st.info, "warning": st.warning, "success": st.success}.get(
        s["tip_type"], st.info
    )
    tip_fn(s["tip"])

    st.write("")  # spacer

    # Navigation row
    col_prev, col_counter, col_next = st.columns([1, 2, 1])
    with col_prev:
        if step > 0:
            if st.button("← Back", use_container_width=True):
                st.session_state["tour_step"] = step - 1
                st.rerun()
    with col_counter:
        st.write("")  # empty centre column
    with col_next:
        if step < TOTAL - 1:
            if st.button("Next →", type="primary", use_container_width=True):
                st.session_state["tour_step"] = step + 1
                st.rerun()
        else:
            if st.button("Close  ✓", type="primary", use_container_width=True):
                st.session_state["tour_seen"] = True
                st.session_state["tour_step"] = 0
                st.rerun()


# Auto-show on first visit
if "tour_seen" not in st.session_state:
    st.session_state.setdefault("tour_step", 0)
    _show_tour()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), use_container_width=True)
    st.title("⚖️ Contract Redliner Pro")
    st.caption("AI-powered NDA redlining")

    if st.button("? Tour", use_container_width=True, help="Relaunch the guided walkthrough"):
        st.session_state["tour_step"] = 0
        _show_tour()

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
    reviewer_name = st.text_input(
        "Reviewer name",
        placeholder="e.g. Jane Smith — Legal",
        help="Your name is stamped on every track change in Word. "
             "Leave blank to attribute changes to the AI.",
    )

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

# ── Main header ────────────────────────────────────────────────────────────────
hcol1, hcol2 = st.columns([1, 4])
with hcol1:
    if LOGO.exists():
        st.image(str(LOGO), use_container_width=True)
with hcol2:
    st.header("Contract Review")
    st.caption("Powered by Contract Redliner Pro")

# ── Contract input ─────────────────────────────────────────────────────────────
if uploaded:
    raw_bytes = uploaded.read()
    if uploaded.name.endswith(".docx"):
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
        st.session_state.pop("docx_bytes", None)
        st.rerun()

# ── Run review ─────────────────────────────────────────────────────────────────
if run:
    with st.spinner("Running AI review…"):
        try:
            if contract_bytes is not None:
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

    # Metric strip
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Clauses reviewed", len(reviews))
    m2.metric("Redlines proposed", len(redlines))
    m3.metric("High risk", risk_counts["high"])
    m4.metric("Medium risk", risk_counts["medium"])
    m5.metric("Escalated", "Yes" if escalated else "No")

    if escalated:
        st.warning(f"🔴 **Escalated to human review** — {data.get('summary', '')}")
    else:
        st.success(f"✅ {data.get('summary', '')}")

    if reviews:
        st.subheader("Risk distribution")
        import pandas as pd
        df = pd.DataFrame(
            {"Risk level": ["High", "Medium", "Low"],
             "Clauses": [risk_counts["high"], risk_counts["medium"], risk_counts["low"]]}
        ).set_index("Risk level")
        st.bar_chart(df, color=["#e53935"])

    st.divider()

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

    # DOCX export
    st.divider()
    if redlines:
        if reviewer_name:
            st.caption(f"Track changes will be attributed to **{reviewer_name}**")
        else:
            st.caption(
                "Track changes will be attributed to **AI Redliner** "
                "(enter a name in the sidebar to override)"
            )

        if st.button("📄 Generate tracked DOCX", type="secondary"):
            with st.spinner("Building DOCX…"):
                try:
                    export_payload: dict = {"title": docx_title, "redlines": redlines}
                    if reviewer_name:
                        export_payload["reviewer"] = reviewer_name
                    exp_resp = requests.post(
                        f"{API_BASE}/export/docx",
                        json=export_payload,
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
