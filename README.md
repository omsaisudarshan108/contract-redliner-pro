# Contract Redliner Pro

A demo-ready LangGraph project for low-risk NDA redlining.

## Included
- LangGraph orchestration
- FastAPI backend
- Streamlit UI
- OpenAI / Gemini / Mock provider adapters
- DOCX exporter with revision markup (`w:ins` / `w:del`) for Word track changes demo
- Dockerfile and docker-compose

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn contract_redliner.api.main:app --reload
```

Open the UI:
```bash
streamlit run src/contract_redliner/ui/streamlit_app.py
```

## Run with Docker
```bash
docker compose up --build
```

## API
- `GET /health`
- `POST /review/text`
- `POST /review/file`
- `POST /export/docx`

## Notes
- The DOCX exporter is built for a demo and writes Word revision XML for inserted/deleted text at paragraph level. It does not preserve every possible formatting edge case from complex source documents.
- For production, plug in your DMS, clause library, policy store, vector index, auth, and audit sink.
