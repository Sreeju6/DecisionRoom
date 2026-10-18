"""FastAPI adapter for DecisionRoom.

Exposes REST API endpoints backed by the centralized multi-agent pipeline.

Security note: Company/project IDs passed as query strings are namespaces, NOT authentication.
This app is designed for single-user/local-only use. Backend binds to 127.0.0.1 in development.
Do NOT expose this to the public internet without adding proper authentication.

Supports:
- POST /api/analyze: Legacy startup market-entry analysis.
- POST /api/decision: Generalized business case decision room evaluation.
- GET /api/runs, GET /api/runs/{run_id}: Audit run history and execution traces.
- GET /api/memory, POST /api/memory, DELETE /api/memory/{memory_id}: Persistent memory CRUD.
- GET /api/documents: List documents (company + project scoped).
- POST /api/documents/ingest: Pasted-text ingestion (backward compat).
- POST /api/documents/upload: Multipart file upload (PDF, DOCX, TXT, CSV, XLSX).
- DELETE /api/documents/{doc_hash}: Delete document chunks.
- GET /api/agent-memory: Per-run agent memory for observability.
- GET /health, GET /api/config/status: System status and redacted configuration.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.pipeline import json_safe, run_business_decision, run_pipeline
from config.config import settings
from schemas.decision import BusinessCase
from tools.document_parser import DocumentChunk, DocumentParser, FileValidationError, ParsingError
from tools.memory import AgentMemoryItem, MemoryStore, ProjectMemoryItem, ProvenanceType
from tools.vector_store import get_vector_store

logger = logging.getLogger("decisionroom.api")

ROOT = Path(__file__).resolve().parent
app = FastAPI(
    title="DecisionRoom API",
    version="2.0.0",
    description="Multi-agent business decision support system. Local-only; not production-secure multi-tenancy.",
)

# Local development + Netlify frontend CORS configuration
origins = os.getenv(
    "DECISIONROOM_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,https://*.netlify.app",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in origins.split(",") if item.strip() and "*" not in item],
    # Local-only API: trust any loopback port (Vite auto-increments when 5173 is busy)
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"
    + (r"|https://[a-zA-Z0-9-]+\.netlify\.app" if "*.netlify.app" in origins else ""),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Allowed file types for upload
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB (matches document_parser.py)


class AnalysisRequest(BaseModel):
    """Legacy input payload for decision analysis."""
    target_state: str = Field(min_length=2, max_length=100)
    decision_question: str = Field(min_length=10, max_length=3000)


class DocumentIngestRequest(BaseModel):
    """Payload for direct text or chunk ingestion into the vector store (pasted-text path)."""
    company_id: str = Field(default="default", min_length=1)
    project_id: str = Field(default="default", min_length=1)
    document_name: str = Field(..., min_length=1)
    text: str = Field(..., min_length=10)
    page_or_section: str = Field(default="General")


def _error(status_code: int, detail: str) -> HTTPException:
    """Return an HTTPException without leaking local paths or tracebacks in message."""
    return HTTPException(status_code=status_code, detail=detail)


@app.get("/")
def root():
    return {"name": "DecisionRoom API", "status": "ok", "docs": "/docs", "version": "2.0.0"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "DecisionRoom API"}


@app.get("/api/config/status")
def config_status():
    """Return redacted system configuration status."""
    return settings.safe_dict()


# -------------------------------------------------------------
# Decision Pipeline Endpoints
# -------------------------------------------------------------
@app.post("/api/analyze")
def analyze(request: AnalysisRequest):
    """Legacy market-entry analysis endpoint."""
    state = request.target_state.strip()
    question = request.decision_question.strip()

    if not state or not question:
        raise _error(422, "Target state and decision question are required.")

    try:
        payload = run_pipeline(
            target_state=state,
            decision_question=question,
            save_report=True,
            report_prefix="decisionroom_web_report",
        )
        return json_safe(payload)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("analyze endpoint failed: %s", type(exc).__name__, exc_info=True)
        raise _error(500, f"DecisionRoom analysis failed: {type(exc).__name__}") from exc


@app.post("/api/decision")
def evaluate_decision(
    case: BusinessCase,
    company_id: str = Query(default="default"),
    project_id: str = Query(default="default"),
):
    """Generalized business decision support room evaluation."""
    try:
        result = run_business_decision(
            case=case,
            company_id=company_id.strip(),
            project_id=project_id.strip(),
            save_report=True,
        )
        return json_safe(result)
    except Exception as exc:
        logger.error("decision endpoint failed: %s", type(exc).__name__, exc_info=True)
        raise _error(500, f"Business decision evaluation failed: {type(exc).__name__}") from exc


# -------------------------------------------------------------
# Run History & Observability Traces
# -------------------------------------------------------------
@app.get("/api/runs")
def list_runs(
    company_id: str = Query(default="default"),
    project_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List historical analysis runs with tenant isolation."""
    try:
        mem = MemoryStore()
        runs = mem.list_runs(company_id=company_id, project_id=project_id, limit=limit)
        return json_safe([r.model_dump() for r in runs])
    except Exception as exc:
        raise _error(500, str(exc)) from exc


@app.get("/api/runs/{run_id}")
def get_run(
    run_id: str,
    company_id: str = Query(default="default"),
):
    """Retrieve full run details and granular audit execution trace."""
    try:
        mem = MemoryStore()
        run = mem.get_run(run_id=run_id, company_id=company_id)
        if not run:
            raise _error(404, f"Run {run_id} not found.")
        traces = mem.get_audit_traces(run_id=run_id, company_id=company_id)
        return json_safe({
            "run": run.model_dump(),
            "traces": [t.model_dump() for t in traces],
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(500, str(exc)) from exc


# -------------------------------------------------------------
# Persistent Project Memory Endpoints
# -------------------------------------------------------------
@app.get("/api/memory")
def get_memory(
    company_id: str = Query(default="default"),
    project_id: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
):
    """Retrieve project memory items (confirmed constraints, goals, facts)."""
    try:
        mem = MemoryStore()
        items = mem.get_project_memory(company_id=company_id, project_id=project_id, category=category)
        return json_safe([i.model_dump() for i in items])
    except Exception as exc:
        raise _error(500, str(exc)) from exc


@app.post("/api/memory")
def save_memory(item: ProjectMemoryItem):
    """Create or update a project memory item."""
    try:
        mem = MemoryStore()
        saved = mem.save_project_memory(item)
        return json_safe(saved.model_dump())
    except Exception as exc:
        raise _error(500, str(exc)) from exc


@app.delete("/api/memory/{memory_id}")
def delete_memory(
    memory_id: str,
    company_id: str = Query(default="default"),
):
    """Delete a project memory item."""
    try:
        mem = MemoryStore()
        success = mem.delete_project_memory(memory_id=memory_id, company_id=company_id)
        if not success:
            raise _error(404, "Memory item not found or unauthorized.")
        return {"status": "deleted", "memory_id": memory_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(500, str(exc)) from exc


@app.get("/api/agent-memory")
def get_agent_memory(
    company_id: str = Query(default="default"),
    project_id: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
):
    """Retrieve per-agent memory records for a run (observability)."""
    try:
        mem = MemoryStore()
        items = mem.get_agent_memories(
            company_id=company_id, project_id=project_id, run_id=run_id
        )
        return json_safe([i.model_dump() for i in items])
    except Exception as exc:
        raise _error(500, str(exc)) from exc


# -------------------------------------------------------------
# Document & RAG Management Endpoints
# -------------------------------------------------------------

@app.get("/api/documents")
def list_documents(
    company_id: str = Query(default="default"),
    project_id: Optional[str] = Query(default=None),
):
    """List documents indexed for a company and optional project."""
    try:
        mem = MemoryStore()
        docs = mem.list_documents(company_id=company_id, project_id=project_id)
        return json_safe(docs)
    except Exception as exc:
        raise _error(500, str(exc)) from exc


@app.post("/api/documents/ingest")
def ingest_document_text(payload: DocumentIngestRequest):
    """Ingest, chunk, and index pasted text into Qdrant with tenant isolation."""
    try:
        store = get_vector_store()
        # Use SHA-256 of text for content-addressed chunk IDs
        # Full 64-char digest: must match the hash DocumentParser stores in chunk payloads,
        # or delete filters (which match on payload doc_hash) silently match nothing.
        doc_hash = hashlib.sha256(payload.text.encode("utf-8")).hexdigest()
        chunk = DocumentChunk(
            chunk_id=f"{payload.company_id}_{doc_hash[:8]}",
            company_id=payload.company_id,
            project_id=payload.project_id,
            document_name=payload.document_name,
            doc_hash=doc_hash,
            page_or_section=payload.page_or_section,
            text=payload.text,
        )
        count = store.index_chunks([chunk])

        # Register in document registry
        mem = MemoryStore()
        mem.register_document(
            company_id=payload.company_id,
            project_id=payload.project_id,
            document_name=payload.document_name,
            doc_hash=doc_hash,
            doc_type="text",
            file_size=len(payload.text.encode("utf-8")),
            chunk_count=count,
            status="indexed",
        )

        return {
            "status": "indexed",
            "document_name": payload.document_name,
            "chunks_indexed": count,
            "doc_hash": doc_hash,
            "chunk_id": chunk.chunk_id,
        }
    except Exception as exc:
        logger.error("Text ingest failed: %s", exc, exc_info=True)
        raise _error(500, f"Ingestion failed: {type(exc).__name__}") from exc


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    company_id: str = Query(default="default"),
    project_id: str = Query(default="default"),
):
    """Upload and parse a document file (PDF, DOCX, TXT, CSV, XLSX) into the vector store."""
    if not file.filename:
        raise _error(400, "Filename is required.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise _error(
            415,
            f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    try:
        raw_bytes = await file.read()
    except Exception as exc:
        raise _error(400, f"Failed to read uploaded file: {type(exc).__name__}") from exc

    if len(raw_bytes) == 0:
        raise _error(400, "Uploaded file is empty.")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise _error(
            413,
            f"File exceeds maximum size of {MAX_UPLOAD_BYTES // (1024*1024)} MB.",
        )

    # Full 64-char digest: DocumentParser recomputes and stores this exact value in chunk
    # payloads; a truncated hash here would make delete filters silently match nothing.
    doc_hash = hashlib.sha256(raw_bytes).hexdigest()
    document_name = file.filename

    try:
        parser = DocumentParser()
        chunks = parser.parse(
            file_content=raw_bytes,
            filename=document_name,
            company_id=company_id,
            project_id=project_id,
            doc_hash=doc_hash,
        )
    except FileValidationError as exc:
        raise _error(422, f"File validation failed: {exc}") from exc
    except ParsingError as exc:
        raise _error(422, f"Document parsing failed: {exc}") from exc
    except Exception as exc:
        logger.error("Document parsing unexpected error: %s", exc, exc_info=True)
        raise _error(500, f"Document parsing failed: {type(exc).__name__}") from exc

    if not chunks:
        raise _error(422, "No readable content extracted from the uploaded file.")

    try:
        store = get_vector_store()
        # Deduplicate: delete any prior version of same doc_hash in this project scope before re-indexing
        store.delete_document(company_id=company_id, doc_hash=doc_hash, project_id=project_id)
        count = store.index_chunks(chunks)
    except Exception as exc:
        logger.error("Vector indexing failed: %s", exc, exc_info=True)
        raise _error(500, f"Indexing failed: {type(exc).__name__}") from exc

    # Register in document registry
    try:
        mem = MemoryStore()
        mem.register_document(
            company_id=company_id,
            project_id=project_id,
            document_name=document_name,
            doc_hash=doc_hash,
            doc_type=ext.lstrip("."),
            file_size=len(raw_bytes),
            chunk_count=count,
            status="indexed",
        )
    except Exception as exc:
        logger.warning("Document registry update failed (chunks still indexed): %s", exc)

    return {
        "status": "indexed",
        "document_name": document_name,
        "doc_hash": doc_hash,
        "doc_type": ext.lstrip("."),
        "file_size_bytes": len(raw_bytes),
        "chunks_indexed": count,
        "company_id": company_id,
        "project_id": project_id,
    }


@app.delete("/api/documents/{doc_hash}")
def delete_document(
    doc_hash: str,
    company_id: str = Query(default="default"),
    project_id: str = Query(default="default"),
):
    """Delete document chunks by doc_hash enforcing company + project scope."""
    try:
        store = get_vector_store()
        success = store.delete_document(company_id=company_id, doc_hash=doc_hash, project_id=project_id)

        # Remove from document registry
        mem = MemoryStore()
        mem.delete_document_registry(
            company_id=company_id, project_id=project_id, doc_hash=doc_hash
        )

        return {"status": "deleted", "doc_hash": doc_hash, "success": success}
    except Exception as exc:
        logger.error("delete_document failed: %s", exc, exc_info=True)
        raise _error(500, f"Deletion failed: {type(exc).__name__}") from exc
