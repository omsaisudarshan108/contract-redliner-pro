from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from contract_redliner.core.config import get_settings
from contract_redliner.core.models import ExportRequest, ReviewRequest, ReviewResponse
from contract_redliner.services.docx_exporter import export_docx_with_track_changes
from contract_redliner.services.review_service import review_file_bytes, review_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Contract Redliner Pro starting — provider=%s port=%s", settings.llm_provider, settings.port)
    yield
    logger.info("Contract Redliner Pro shutting down")


app = FastAPI(title="Contract Redliner Pro", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s → %s (%.0fms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "type": type(exc).__name__})


@app.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "provider": settings.llm_provider,
        "openai_configured": bool(settings.openai_api_key),
        "gemini_configured": bool(settings.gemini_api_key),
    }


@app.post("/review/text", response_model=ReviewResponse)
async def review_text_endpoint(request: ReviewRequest):
    if not request.document_text.strip():
        raise HTTPException(status_code=400, detail="document_text must not be empty")
    logger.info("Review request: %d chars, provider=%s", len(request.document_text), request.provider or "default")
    try:
        return await review_text(
            request.document_text,
            provider=request.provider,
            openai_api_key=request.openai_api_key,
            gemini_api_key=request.gemini_api_key,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/review/file", response_model=ReviewResponse)
async def review_file_endpoint(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    logger.info("File review: %s (%d bytes)", file.filename, len(content))
    try:
        return await review_file_bytes(file.filename or "upload.txt", content)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/export/docx")
async def export_docx_endpoint(request: ExportRequest):
    if not request.redlines:
        raise HTTPException(status_code=400, detail="No redlines provided")
    logger.info("DOCX export: %d redlines, title=%s", len(request.redlines), request.title)
    blob = export_docx_with_track_changes(request.title, request.redlines)
    headers = {"Content-Disposition": 'attachment; filename="redlined_contract.docx"'}
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )
