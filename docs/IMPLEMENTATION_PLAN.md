# DecisionRoom — Updated Implementation Plan

**Purpose:** Evolve the existing DecisionRoom repository into an evidence-grounded, multi-agent business decision-support application while preserving useful legacy policy-research behavior and the existing React/FastAPI foundation.

**Working rule for Antigravity:** Implement one phase at a time. Do not start a later phase until the current phase's checkpoint passes. Make small changes, inspect diffs, keep existing reports readable, and never report a test as passed unless it was actually run.

---

## 1. Review of the Existing Repository

This repository has useful working components, but it is not yet the target multi-agent decision room.

| Area | Observed state | Required direction |
|---|---|---|
| CLI/API | `main.py` and `api.py` duplicate orchestration logic. API import has been reported to fail when FAISS is unavailable. | Move orchestration into one shared pipeline; CLI and API become thin adapters. |
| Configuration | `config/config.py` is empty. | Central, validated settings loaded from environment variables. |
| Current agents | Data/research/TANSEED verification exist, alongside largely rule-based risk/critic/planner and a decision agent. | Preserve useful behavior behind adapters, but introduce independent Sales, Finance, Legal, Technical and Risk specialists. |
| RAG/vector search | FAISS index and government-policy documents exist; `tools/rag_tools.py` is empty. | Add company-document ingestion and a vector-store interface. Choose Qdrant as the target; retain FAISS until migration tests pass. |
| Tools | `tools/calculation_tools.py` is empty; there are existing data and index-building tools. | Add tested deterministic finance calculations and reusable retrieval/research tools. |
| Frontend | React/Vite UI exists with state/policy-specific controls. | Generalize the existing UI; do not replace it wholesale. Keep compatibility for old reports. |
| Dependencies/tests | `requirements.txt` is empty; `requirements-api.txt` is incomplete. | Define tested dependencies and establish unit/integration tests before broad refactoring. |
| Memory/audit | No complete persistent global + agent memory design is established. | SQLite for structured records and audit history; Qdrant for source/document retrieval and, if useful, semantic memory. |

The current state-specific policy corpus and historic TANSEED use case must remain available as a regression scenario, but must not define the new product's workflow or UI.

---

## 2. Target Workflow (Source of Truth)

```text
User creates a Business Case
        |
        v
Validate intake + identify missing inputs
        |
        v
Ingest/retrieve relevant company documents + external web evidence
        |
        v
Run specialist agents:
  Sales | Finance | Legal | Technical | Risk
        |
        v
Business Decision Agent reconciles evidence, risks, assumptions,
conflicts and alternatives; returns one validated outcome
        |
        +-------------------+--------------------+
        |                   |                    |
     PROCEED          DO_NOT_PROCEED      HOLD_FOR_EVIDENCE
        |                   |                    |
        v                   v                    v
 Planning Agent        Critic Agent        Missing evidence,
 phased execution      rejection rationale questions and blockers
 plan                  and alternatives
        |
        v
Persist report, citations, run trace, agent memory and final decision
        |
        v
UI: live progress, findings, evidence, decision branch, reports and audit
```

**Important workflow rules:**
- The workflow orchestrator, not an LLM, enforces branch rules.
- The default final outcome has three valid values: `PROCEED`, `DO_NOT_PROCEED`, and `HOLD_FOR_EVIDENCE`.
- A `PROCEED` outcome may invoke Planning Agent. A `DO_NOT_PROCEED` outcome may invoke Critic Agent. `HOLD_FOR_EVIDENCE` returns missing inputs and does not invoke either branch as the final response.
- Agents do not vote blindly or treat another agent's conclusion as verified fact. The Business Decision Agent weighs evidence quality and decision criteria, explains conflicts, and discloses assumptions.
- Every material factual claim should have a source citation or be explicitly labelled as an assumption, estimate, inference, or unverified claim.

---

## 3. Technology Decisions

### 3.1 Backend, persistence and retrieval

- **Backend:** Keep Python + FastAPI and the current CLI.
- **Contracts:** Pydantic models for business cases, findings, citations, risks, decisions, plans and run states.
- **Vector store target:** Qdrant. Use a local persistent Qdrant mode by default when `QDRANT_URL` is blank; use a remote Qdrant endpoint only when a URL is configured. Do not attempt a remote connection using empty credentials.
- **Migration safety:** Keep the current FAISS implementation as a compatibility/baseline path until deterministic retrieval tests pass against Qdrant. Never reuse an index if the embedding model or vector dimensions differ; re-index explicitly.
- **Structured database:** SQLite for runs, decisions, user/project metadata, memory records, audit events, document metadata and feedback. Do not store all state only in vector memory.
- **Embeddings:** Keep the embedding model independent of the generation model. Inspect the existing index/build scripts first, record the chosen embedding model and dimensions, and make it configurable. Re-index documents after any embedding-model change. Prefer local embedding for the initial prototype where practical to reduce request quotas and avoid sending full company document contents to another API.
- **File formats:** PDF, DOCX, TXT, CSV and XLSX. Preserve PDF page, DOCX section where available, spreadsheet sheet and cell/table context. Numeric spreadsheets must not be flattened into text without retaining units and table structure.

### 3.2 Model registry and routing

Implement a provider-independent interface, with an explicit registry of approved model IDs. Do not invent IDs or silently switch to an unconfigured provider.

| Purpose | Provider/model ID | Suggested use |
|---|---|---|
| Lightweight intake, metadata extraction, simple classification | Google Gemini API: `gemini-3.1-flash-lite` | Short, bounded tasks; validate structured output. |
| Alternate lightweight model | Google Gemini API: `gemini-3.5-flash-lite` | Configurable alternative/fallback after smoke testing. |
| Specialist analysis | Google Gemini API: `gemma-4-26b-a4b-it` | Initial evaluation for agent reasoning. Control context size and concurrency. |
| Optional stronger Gemma reviewer | Google Gemini API: `gemma-4-31b-it` | Explicitly enabled second-pass review or quality comparison; not required on every run. |
| Synthesis, planning and complex critique | NVIDIA NIM: `nvidia/nemotron-3-super-120b-a12b` | Primary candidate for complex reasoning and multi-agent synthesis, after an API smoke test. |

These model IDs are documented by their providers: [Gemma 4 on Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api), [Gemini 3.1 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite), [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [NVIDIA NIM model/API page](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/build).

The names above must be used as API model IDs where applicable, rather than shortened display names such as “Gemma 4 26” or “Nemotron 120B”.

#### Model limits and reliability

The following limits are **user-reported account/project limits**, not universal provider guarantees. Verify them in the relevant console before final tuning:

| Model family / IDs | User-reported limit | Engineering implication |
|---|---|---|
| Gemma 4 26B A4B and 31B | 30 RPM, 14,400 RPD, 16,000 TPM | TPM is the tight constraint. Bound context/output tokens; throttle concurrent calls and estimate token demand before dispatch. |
| Gemini 3.5 Flash-Lite and 3.1 Flash-Lite | 15 RPM, 500 RPD, 250,000 TPM | RPD is the tight constraint. Avoid unnecessary repeated calls and cache suitable extraction/research results. |
| NVIDIA Nemotron 3 Super 120B A12B via NIM | 40 RPM; user reports unlimited RPD | Treat the limit as account/endpoint-specific; implement rate limiting and 429 handling regardless. |

Google documents that rate limits depend on project, tier and model and can change; view the active limits in AI Studio: [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). The service must not hard-code these limits as guaranteed facts. Make limits configurable and log model, request count, estimated tokens, latency, provider errors and retry count without logging secrets or complete confidential prompts.

**Initial routing policy:** Use Gemini 3.1 Flash-Lite for short intake/extraction; test Gemma 4 26B for specialist findings; use Nemotron for decision synthesis and the planning/critic branch; keep Gemini 3.5 Flash-Lite and Gemma 4 31B configurable rather than invoking every model for every run. Calls should be sequential or tightly bounded by default. Add a simple per-provider/per-model rate limiter, bounded retries with backoff, timeout handling and clear failure states. Do not retry indefinitely or silently convert a failed model call into a successful-looking result.

### 3.3 Environment variables

The user has declared these variables:

```env
NVIDIA_NIM_API_KEY=
GOOGLE_API_KEY=
QDRANT_URL=
QDRANT_API_KEY=
```

An empty value is not a credential or endpoint. Model smoke tests must report a clear “not configured” status until the relevant key is populated. Keep `.env` out of Git and never print secrets in logs, errors, reports or screenshots.

Recommended additional configurable values (names can be adapted to existing conventions):

```env
DEFAULT_LLM_PROVIDER=nvidia
MODEL_INTAKE=gemini-3.1-flash-lite
MODEL_SPECIALIST=gemma-4-26b-a4b-it
MODEL_DECISION=nvidia/nemotron-3-super-120b-a12b
MODEL_PLANNER=nvidia/nemotron-3-super-120b-a12b
MODEL_CRITIC=nvidia/nemotron-3-super-120b-a12b
MODEL_FALLBACK=gemini-3.5-flash-lite
QDRANT_LOCAL_PATH=./storage/qdrant
SQLITE_PATH=./storage/decisionroom.db
MAX_AGENT_CONCURRENCY=2
MAX_RETRIES=2
REQUEST_TIMEOUT_SECONDS=60
```

These are suggested defaults, not mandatory names. Antigravity must settle one naming scheme in `config/config.py` and `.env.example`. Use `https://integrate.api.nvidia.com/v1` as the documented NVIDIA-hosted API base URL when using the NVIDIA API endpoint; do not confuse hosted NIM API access with self-hosting the model.

Firecrawl must be configured through the actual MCP server/tool definition used in this environment. Add the documented API key/URL variables required by that MCP configuration, if any; do not invent an MCP command or pretend integration works when the server is unavailable.

---

## 4. Implementation Phases and Acceptance Gates

### Phase 0 — Repository audit (completed as planning stage; do not rebuild)

**Goal:** Establish a factual baseline, identify working features and define target architecture.

**Gate:** The developer has reviewed this plan, confirmed that the repository backup/branch exists, and is ready to implement Phase 1. Any difference between the checked-out repository and the file inventory above must be verified before editing.

### Phase 1 — Shared foundation, configuration and orchestration

**Files likely involved:** `requirements.txt`, `requirements-api.txt`, `config/config.py`, new `app/pipeline.py` or `agents/orchestrator.py`, `main.py`, `api.py`, new `models/` or `schemas/`, new `tests/`.

**Tasks:**
1. Populate dependencies based on imports actually used; pin compatible versions only after installing/testing them. Avoid installing every possible framework “just in case”.
2. Implement validated environment configuration and secret redaction.
3. Add typed Pydantic schemas for `BusinessCase`, `EvidenceCitation`, `AgentFinding`, `Risk`, `DecisionResult`, `ExecutionPhase`, and `AnalysisRun`.
4. Add a provider-independent LLM client abstraction and configure the model IDs in Section 3. Verify SDK/API compatibility with minimal smoke tests; do not invent endpoints or pretend empty keys work.
5. Move shared workflow execution into one orchestrator; leave `main.py` and `api.py` as CLI/API adapters.
6. Preserve legacy report keys or add explicit versioned adapters.

**Checkpoint:** `pytest` environment/config/schema tests pass; API import and `/health` work without calling an external LLM; CLI and frontend build still work; missing API keys produce an explicit configuration state; provider failures and malformed structured outputs are tested. Do not implement the full agents yet.

### Phase 2 — Company-document ingestion and grounded RAG

**Tasks:**
1. Add secure upload and parsers for PDF, DOCX, TXT, CSV and XLSX, with file-size/type validation and safe error responses.
2. Extract source-aware chunks and metadata: tenant/company, project, document ID/name, hash, page/sheet/section, upload time and parsing status.
3. Introduce a vector-store interface and implement persistent local Qdrant plus optional remote Qdrant when configured. Retain FAISS until retrieval comparison tests pass.
4. Reuse/configure embeddings independently of generation; persist embedding model and dimension metadata.
5. Add metadata-filtered retrieval, deduplication, relevance thresholds, source citations and a clear insufficient-evidence result.
6. Add document re-indexing, deletion and duplicate detection using content hashes. Prevent one company/project from retrieving another company's documents.
7. Treat all ingested content as untrusted data, not as system instructions or executable code.

**Checkpoint:** Each supported file format has a parser test; citations identify the correct page/sheet where available; two mock companies remain isolated; duplicate upload, changed file, corrupt file, empty file and no-hit retrieval are tested; FAISS/Qdrant results are compared on a fixed test set. Do not implement specialist reasoning yet.

### Phase 3 — Firecrawl MCP web research and source records

**Tasks:**
1. Inspect the actual configured Firecrawl MCP tools and schemas. Implement a `WebResearchService` adapter using those exact tools.
2. If the MCP server is unavailable, add a mock interface for offline tests and report the missing prerequisite. Do not claim live search succeeded.
3. Return structured source records: title, URL, domain/publisher, retrieval timestamp, extracted text, query, status and any available publication date.
4. Apply source preferences and domain allow/deny rules when the task requires authoritative sources. Preserve citations to every used page.
5. Deduplicate and limit page content, use bounded timeouts, cache with timestamps where suitable, and flag stale evidence.
6. Detect/contain prompt injection from retrieved pages; scraped content must not override agent system instructions.
7. Report retrieval failure separately from evidence that no relevant source exists. Any non-MCP fallback must be explicitly configured and independently tested.

**Checkpoint:** mock search passes offline; live smoke test passes only when MCP is available; URL and retrieval timestamp flow into the final evidence record; failures are visible; malicious page instructions do not alter workflow rules.

### Phase 4 — Specialist agents

Implement independent agents on a shared interface. Each agent receives the validated business case, scoped company evidence, relevant web evidence and only the context it needs.

- **Sales Agent:** customer segments, demand, market, competitors, pricing, distribution and go-to-market risks.
- **Finance Agent:** costs, revenue assumptions, unit economics, cash flow/runway, margins, break-even and downside scenarios. Use deterministic Python functions for arithmetic; do not rely on LLM mental math.
- **Legal Agent:** relevant jurisdictions, licenses, regulations, contracts, compliance duties and unresolved legal questions. Separate official-source findings from interpretation and flag when professional legal review is needed.
- **Technical Agent:** feasibility, architecture, integration dependencies, staffing/effort, infrastructure and operational constraints.
- **Risk Agent:** cross-functional risks, likelihood/impact rationale, mitigations, residual risk and leading indicators.

Each returns validated `AgentFinding` data: executive summary, evidence citations, assumptions, risk items, confidence rationale, contradictions and missing information. Confidence must have a defined rubric and must not be an arbitrary LLM-generated percentage. A finding may legitimately contain insufficient evidence.

**Checkpoint:** Every agent has mocked unit tests for valid, malformed, incomplete and contradictory evidence; calculation functions match hand-checked examples; claims marked as supported have source IDs; model failure does not create a fake successful finding. Avoid unbounded agent-to-agent tool calls.

### Phase 5 — Business Decision Agent and controlled branching

**Tasks:**
1. Run the specialists through the orchestrator; default to bounded concurrency because of API rate limits.
2. Synthesize agent findings, source quality, assumptions, contradictions and material unknowns.
3. Compare alternatives against explicit criteria: strategic fit, customer/commercial viability, financial sustainability, legal feasibility, technical feasibility and risk.
4. Make weights/thresholds configurable and show them in the report if used. Do not fabricate numeric scores or treat the decision as a simple majority vote.
5. Return exactly one schema-valid status: `PROCEED`, `DO_NOT_PROCEED`, or `HOLD_FOR_EVIDENCE`, with rationale, evidence, conditions and uncertainties.
6. Let deterministic orchestrator code validate the status and invoke the proper branch; the LLM must not run arbitrary tools or override branch restrictions.

**Checkpoint:** deterministic integration tests cover all three outcomes, downstream branch isolation, malformed LLM output, missing critical inputs, provider outage and conflicting agent findings. No execution plan on a `DO_NOT_PROCEED` outcome; no rejection critic branch on `PROCEED`; no false certainty when evidence is missing.

### Phase 6 — Planning and Critic branches

**Planning Agent (PROCEED only):** Create a phased plan with objective, tasks, role/owner, dependencies, timeline estimate, resources, cost estimate and assumptions, deliverables, KPIs, acceptance criteria, risks and go/no-go gates. Mark costs and timelines as sourced, calculated, inferred or illustrative. Validate arithmetic and phase dependency consistency.

**Critic Agent (DO_NOT_PROCEED only):** Explain the evidence-backed rejection rationale; classify blockers as fatal, remediable or uncertain; identify failed assumptions, legal/financial/technical risks and opportunity costs; propose alternatives or the conditions required for reconsideration.

**HOLD_FOR_EVIDENCE:** Return required documents/questions, why each matters, and which roles need to resolve it. Do not fabricate a plan or a rejection report.

**Checkpoint:** Branch tests pass; plan cost totals reconcile; phase dependencies are coherent; cited rejection claims trace to evidence/findings; missing-evidence reports list concrete questions and no forced recommendation.

### Phase 7 — Persistent global memory, per-agent memory and auditability

**Storage:** SQLite for structured state and audit records; Qdrant for document retrieval and optional semantic memory. Keep records queryable and exportable; do not use vector search as the sole source of truth.

**Record types:**
- Global/project memory: confirmed company context, approved constraints, goals, previous decisions and unresolved questions.
- Agent memory: previous findings, assumptions, relevant evidence references, unresolved issues and follow-ups.
- Run/trace log: run IDs, timestamps, agent status, model/provider, tool calls, source IDs, latency, retries, errors and output references.
- Decision history: input version, outcome, rationale, conditions, revisions and later feedback.

Add company/project/run/agent scopes; retention settings; inspect, correct and delete controls; safe resume behavior where possible; transaction-safe writes. Memory provenance must distinguish user-confirmed facts, source-derived facts, and previous AI inferences. Never silently promote an earlier AI conclusion to a verified fact. Do not save secrets or needlessly duplicate full confidential document contents into memory.

**Checkpoint:** records persist across restart; later runs can retrieve relevant permitted memory; mock companies are isolated; users can inspect/correct/delete records; audit traces show which evidence/memory items influenced a result; interrupted and duplicate runs are tested.

### Phase 8 — Frontend generalization and premium UI

Build on the existing React/Vite code and theme; do not create a second frontend.

**Screens:**
1. Overview/dashboard with recent runs, project selector, outcomes and genuine status/risk metrics.
2. New Decision form with business proposal, objective, constraints, company/project, and document uploads.
3. Document Library with parsing/index status, source metadata and deletion.
4. Decision Room with real agent progress/status, finding summaries, evidence counts, errors and run trace.
5. Decision report with prominent `PROCEED` / `DO_NOT_PROCEED` / `HOLD_FOR_EVIDENCE`, reasoning, citations, assumptions and unresolved conflicts.
6. Planning view with expandable phases, dependencies, deliverables, estimates, KPIs and acceptance gates.
7. Critic view with blockers, remediable weaknesses and alternatives.
8. Memory/Audit view for global and agent memory, runs, decisions and source references.
9. Settings and provider status; never display API key contents.

**Visual direction:** premium enterprise tool with dark graphite/navy surfaces, restrained violet/cyan accents, crisp typography, deliberate spacing, clean charts, subtle motion and high-quality empty/loading/error states. It should look intentional, not like a generic chat UI. Use only real backend data; never use fake “live” activity or fabricated KPI cards. Ensure accessible, responsive controls and safe rendering of document text/URLs.

**Checkpoint:** production frontend build passes; all three branches render; upload/list/delete work end-to-end; citations open the right source; API errors and empty states are intelligible; mobile/desktop layouts and download/export work; no dead buttons or placeholder data remain.

### Phase 9 — End-to-end validation, reliability and handover

Use synthetic company cases and mocked providers so tests do not consume external quotas:
1. Sound proposal with sufficient supporting evidence.
2. Negative unit economics.
3. Potentially material legal blocker.
4. Technical infeasibility or dependency gap.
5. Insufficient evidence.
6. Contradictory company documents and web sources.
7. Model timeout, HTTP 429, malformed JSON and unavailable provider.
8. Invalid/oversized/corrupt uploads and unsupported file types.
9. Company/project isolation and memory deletion.
10. Backend restart, interrupted run and report re-open.

**Security/reliability:** Validate request/file limits, safe file handling, scoped access, secret redaction and clear provider-error envelopes. Prevent scraped or uploaded instructions from changing the system rules. Do not execute uploaded code/macros. Do not claim production security, legal correctness or complete source verification without corresponding evidence and tests.

**Checkpoint:** run tests and frontend build; disclose failures rather than weakening tests to pass; provide exact setup commands, `.env.example`, data/index setup, a reproducible demo and `docs/FINAL_VALIDATION_REPORT.md` containing what passed, failed, could not be tested and remains out of scope.

---

## 5. Cross-Cutting Requirements

1. **Versioned contracts:** Add a report schema version and adapters for historical JSON reports so the old state-policy use case remains viewable.
2. **Observability:** Give each run, agent call, evidence record and decision a stable ID. The UI should display user-useful traces, not chain-of-thought. Store concise rationales and evidence, not private model reasoning traces.
3. **No unsupported claims:** A citation must point to an actual retrieved source. Clearly label assumptions, generated hypotheses, calculations and unresolved questions.
4. **Rate/cost control:** Per-model concurrency, request and token budgets; bounded retries; retry-after-aware 429 handling; context/output caps; caching and a model-call budget per business case.
5. **Company confidentiality:** Enforce company/project metadata filters at retrieval and memory layers. Local storage is the default when remote Qdrant is not configured. Do not send documents to external APIs unless that model call is required and the selected provider is configured.
6. **Deterministic financial math:** Unit tested calculations, currency/unit tracking, explicit assumptions and reproducible outputs.
7. **User approval boundary:** The system recommends and plans. It must not send emails, spend money, submit legal filings, execute transactions, or initiate external actions without explicit user authorization.
8. **Code discipline:** No wholesale rewrites, no unrelated cleanup, no invented successful test results, no hard-coded secrets, and no next-phase work before the current acceptance gate passes.

---

## 6. First Changes to Make

1. Confirm a clean Git commit/backup before changes.
2. Fix dependency/import/startup issues and make `/health` independent of API keys and external services.
3. Create validated configuration, schema tests and a shared orchestrator; remove duplicate pipeline logic.
4. Add model-provider smoke tests with explicit “not configured” behavior for empty keys; log the actual model ID without logging the key.
5. Build the document-ingestion/RAG interface and Qdrant local persistence; test it before changing the default away from FAISS.

**Do not start UI redesign or all specialist agents simultaneously.** Stabilize the shared contracts and evidence layer first. The acceptance checkpoints above determine when to move on.
