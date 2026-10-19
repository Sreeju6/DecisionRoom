# DecisionRoom — Multi-Agent Business Decision-Support System

DecisionRoom is an enterprise multi-agent decision-support platform designed to evaluate strategic business proposals (market expansions, new product launches, regulatory entries, capital investments). It synthesizes empirical evidence across five domain specialists, executes deterministic financial formulas, and routes outcomes through a controlled 3-way decision branching engine.

---

## Architecture Overview

```
User Business Case
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  Intake & Retrieval Orchestration                      │
│  - Document RAG: Qdrant Cloud (Nomic 768-dim Vectors)  │
│  - Web Research: Firecrawl Direct API / Cache          │
│  - Scoped Project Memory: SQLite WAL Mode              │
└────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  Domain Specialists (LLM + Typed Pydantic Schemas)     │
│  ├── SalesAgent: Demand, TAM, CAC/GTM, Competitors     │
│  ├── FinanceAgent: Unit Economics, Margins, Stress Test│
│  ├── LegalAgent: Compliance, GDPR, Regulatory hurdles  │
│  ├── TechnicalAgent: Architecture, SLA, Infra, Security│
│  └── RiskAgent: Cross-functional Risk Synthesis        │
└────────────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────────────┐
│  Controlled 3-Way Decision Branching Engine            │
│  (BusinessDecisionAgent — Nemotron Super 120B)         │
│  ├── Critical Blocker Detected?   ➔ DO_NOT_PROCEED     │
│  ├── Insufficient Evidence / Gaps? ➔ HOLD_FOR_EVIDENCE │
│  └── Verified Viability & Defense? ➔ PROCEED           │
└────────────────────────────────────────────────────────┘
        │
        ├─► [PROCEED] ➔ PlanningAgent (Sequential phases, KPIs, deliverables, acceptance gates)
        ├─► [DO_NOT_PROCEED] ➔ CriticAgent (Fatal blockers, remediable issues, alternatives)
        └─► [HOLD_FOR_EVIDENCE] ➔ Missing Evidence Checklist (strictly prevents fabricated plans)
```

---

## Approved Model Registry

Models are strictly routed via configuration and validated against `APPROVED_MODEL_IDS`:
- **Planning, Critic & Decision Synthesis:** `nvidia/nemotron-3-super-120b-a12b` (via NVIDIA NIM)
- **Domain Specialists:** `gemma-4-26b-a4b-it` (via Google GenAI)
- **Specialist Second-Pass Review:** `gemma-4-31b-it` (via Google GenAI)
- **Intake & Light Extraction:** `gemini-3.1-flash-lite` (via Google GenAI)
- **Configurable Fallback:** `gemini-3.5-flash-lite` (via Google GenAI)

*Fallback Behavior:* If an LLM provider key is unavailable or fails, specialists fall back to deterministic rule-based analyses grounded strictly in retrieved evidence, preventing unsupported approvals.

---

## Semantic Vector Store & Document Ingestion

- **Embeddings:** Local HuggingFace `nomic-ai/nomic-embed-text-v1.5` normalized 768-dimensional vectors.
- **Vector Store:** Qdrant Cloud collection versioned as `company_documents_v768` to preserve legacy collections and prevent vector dimension collisions.
- **Multi-Format Ingestion:** Multipart upload via `POST /api/documents/upload` supporting `.pdf`, `.docx`, `.txt`, `.csv`, and `.xlsx` (Max 20MB).
- **Idempotency & Deduplication:** Content-addressed hashing via SHA-256 of raw bytes. Re-uploading an identical file updates metadata and chunk index safely.
- **Tenant Scope:** Every document and memory record is strictly isolated by `company_id` and `project_id`.

---

## Security Boundary & Local Development Note

> [!IMPORTANT]
> `company_id` and `project_id` operate as namespace partitions for document and memory isolation, **not authenticated user authorization principals**.
> This application is configured for single-user local deployment, binding development servers strictly to `127.0.0.1`. Do not expose directly to public networks without adding an authentication middleware (e.g. JWT/OAuth).

---

## Windows PowerShell Quickstart

### 1. Prerequisites
- Python 3.13+ (or [uv](https://docs.astral.sh/uv/) for high-speed dependency resolution)
- Node.js 18+ and npm

### 2. Environment Setup

#### Option A: Using `uv` (Recommended)
```powershell
# Create environment and install dependencies
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

#### Option B: Standard Python `venv`
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure `.env`
Copy `.env.example` to `.env` and supply your credentials:
```powershell
Copy-Item .env.example .env
```
Key environment variables:
```ini
NVIDIA_NIM_API_KEY=nvapi-...
GOOGLE_API_KEY=AIzaSy...
QDRANT_URL=https://...aws.cloud.qdrant.io
QDRANT_API_KEY=...
FIRECRAWL_API_KEY=...
```

### 4. Run Pytest Verification (72 Tests)
```powershell
python -m pytest tests/ -v
```

### 5. Launch Backend Server
```powershell
.\start_backend.ps1
```
(Equivalent to `python -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload --reload-exclude "<repo>\.venv"` — the exclude is required: without it the watcher restarts the server whenever torch/pandas/openai touch caches in `.venv`, killing requests mid-flight.)
OpenAPI documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 6. Launch Frontend UI
```powershell
cd frontend
npm install
npm run build   # Validate production bundle
npm run dev     # Start development server
```
Frontend application: [http://localhost:5173](http://localhost:5173)

---

## API Endpoints

- `POST /api/decision?company_id={co}&project_id={proj}`: Run full multi-agent decision support analysis.
- `GET /api/documents?company_id={co}&project_id={proj}`: List all indexed documents in project scope.
- `POST /api/documents/upload`: Multipart file upload (PDF, DOCX, TXT, CSV, XLSX) into vector store.
- `POST /api/documents/ingest`: Pasted text ingestion fallback.
- `DELETE /api/documents/{doc_hash}?company_id={co}&project_id={proj}`: Delete document and all indexed vector chunks.
- `GET /api/runs`: List historical runs with tenant filtering.
- `GET /api/runs/{run_id}`: Retrieve full execution details and audit traces.
- `GET /api/memory`: List persistent project memory items.
- `POST /api/memory`: Save confirmed constraint, goal, or fact.
- `DELETE /api/memory/{memory_id}`: Delete memory record.
- `GET /api/config/status`: Safe provider status check with masked keys.
- `POST /api/analyze`: Backward-compatible legacy startup evaluation endpoint.