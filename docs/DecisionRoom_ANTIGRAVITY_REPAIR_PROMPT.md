# DecisionRoom — One-Pass Implementation Repair Prompt

Read `AGENTS.md` first and follow its instructions. Then inspect `docs/IMPLEMENTATION_PLAN.md`, `docs/FINAL_VALIDATION_REPORT.md`, the actual source, tests, and frontend before editing. Treat the validation report as an unverified claim: confirm every result by running it. Implement the fixes in this pass; do not return another plan or merely describe changes.

## Operating rules

- Make the smallest complete changes in the existing architecture. Do not rebuild the project or delete the legacy workflow.
- Preserve the existing FastAPI routes and legacy report keys unless a backward-compatible extension is necessary.
- Never fabricate a successful model call, live web result, citation, calculation, test result, or completed integration.
- Do not weaken or delete tests just to pass. Add regression tests for each bug fixed.
- Keep API keys in `.env`; never print them or put them in frontend source/build variables.
- If credentials or network access are unavailable, complete mock-based tests and clearly mark the live integration as **not verified**. Do not substitute mocks silently in a real run.
- Do not clear, overwrite, or recreate existing user data in SQLite or Qdrant to fix schema/embedding changes. Use a migration or versioned collection and explain re-indexing when required.

## Confirmed issues to fix

### 1. Make the configured models actually run

At present, `agents/specialists.py` contains keyword/rule-based responses, `BusinessDecisionAgent.evaluate()` does not call `self.llm_client`, and no code under `agents/` invokes `LLMClient.generate()` or `generate_structured()`. The pipeline therefore records a model in `models_invoked` even when no model was called. Fix the real execution path.

- Use `LLMClient.generate_structured()` with Pydantic response schemas for Sales, Finance, Legal, Technical, Risk, Business Decision, Planning, and Critic outputs. Keep deterministic rules as guardrails, not as a substitute for agent reasoning.
- Route using configuration, not hard-coded provider selection. Audit `config/config.py`: several variables documented in `.env.example` are not currently read (including the Firecrawl key, base URL, and some retry/concurrency settings), and `model_specialist_review` is missing from model-ID validation. Ensure every documented setting has a real effect and is exposed safely in status output.
  - Intake/light extraction: `gemini-3.1-flash-lite`
  - Specialist analysis: `gemma-4-26b-a4b-it`
  - Optional second-pass reviewer: `gemma-4-31b-it`
  - Planner/Critic/Decision synthesis: `nvidia/nemotron-3-super-120b-a12b`
  - Configurable fallback: `gemini-3.5-flash-lite`
- These model IDs have been checked against current provider documentation; still handle “model unavailable” errors explicitly. Validate **every** model setting, including `model_specialist_review`, against the allowlist.
- Maintain role-specific prompts, scoped input context, token limits, timeout handling, retry/backoff for transient failures, and structured-output validation. If a provider key is missing or the provider fails, do not silently act as though an LLM analysis happened. Return a clear error/degraded status and prevent an unsupported `PROCEED` decision.
- Add application-level per-model/provider rate limiting, and make limits configurable. Use these user-reported starting limits as defaults, not universal guarantees: Gemma 4 26B/31B: 30 RPM, 14,400 RPD, 16,000 TPM; Gemini 3.1/3.5 Flash-Lite: 15 RPM, 500 RPD, 250,000 TPM; NVIDIA NIM Nemotron: 40 RPM, no RPD cap supplied. Handle provider 429/Retry-After and record rate-limit events. Avoid launching concurrent calls that violate quotas. Use mocks in tests only when explicitly injected or in test mode.
- Record the actual model/provider, call status, duration, and usage when returned. `models_invoked` must reflect successful/attempted real calls accurately, not configured defaults.

### 2. Replace fake web search with real Firecrawl runtime calls

`FirecrawlMCPAdapter.search()` currently returns `[]` even when it has an API key, and `WebResearchService()` does not pass the configured `FIRECRAWL_API_KEY` into it. The cached-results dictionary is also unused.

- Implement a real runtime Firecrawl adapter using the current official Firecrawl API/SDK, or an explicitly configured MCP client with a real transport. Prefer a direct Firecrawl API adapter for the FastAPI runtime unless an MCP endpoint/transport is actually configured.
- Important: an MCP server attached to the Antigravity development environment is **not automatically callable by the running Python application**. Make the app's runtime integration explicit; do not claim MCP works because Antigravity itself can use the tool.
- Read the key from validated configuration, use official API paths/payloads, timeouts, result limits, bounded retries, cache expiry, and clean errors. Support query-specific search; scrape/extract pages when needed. Never return fabricated records on failure.
- Have agents request evidence suited to their role: Sales (market/customer/competitor/pricing), Finance (costs, company/industry financial benchmarks), Legal (jurisdiction and official regulator sources), Technical (architecture/standards/vendor documentation), Risk (failure modes and controls). Apply relevant domain preferences and label unofficial sources.
- Preserve title, URL, domain, retrieved-at timestamp, available publication date, status, and excerpt in all citations. A retrieved page is not the same as a verified claim. **Mock results must never be marked verified**; HTTP success alone must not imply that the content supports a claim. Preserve unavailable/failed search status in the analysis.
- Add mocked unit tests and an opt-in live Firecrawl smoke test that only runs when credentials are configured.

### 3. Make document upload, listing, retrieval, and deletion end-to-end

`tools/document_parser.py` can parse files, but the API/UI do not use it: `/api/documents/ingest` only accepts pasted text. The UI has no actual file picker or document list. The API's delete route calls `store.delete_document(...)`, which does not exist on `QdrantVectorStore`.

- Add a multipart upload endpoint using FastAPI `UploadFile`/`File`, add `python-multipart` to dependencies, enforce the existing file-size/type limits before parsing, and use `DocumentParser.parse()` for PDF, DOCX, TXT, CSV, XLSX.
- Use SHA-256 of raw file bytes for idempotency and stable chunk IDs based on content hash + page/sheet/chunk index. Re-uploading identical content in the same company/project must not create duplicates. Changing a file must replace its prior chunks safely.
- Preserve page/sheet/section and table headers/cell context. For CSV/XLSX, keep structured numeric context useful to FinanceAgent. Do not claim that a PDF's content is complete when extraction produced no readable text.
- Index parsed chunks into Qdrant and persist a document registry in SQLite so a user can list document name, type, size, hash, company, project, ingestion time, chunk count, status, and parse/index errors.
- Implement `GET /api/documents` with company **and project** filters; implement upload, pasted-text ingest compatibility, and deletion. Fix the delete endpoint to call an actual store method and delete both registry metadata and matching chunks within the same tenant/project scope.
- Update the existing React UI to use a real file picker with progress, accepted-file help, parse/indexing status, errors, a document list, and delete confirmation. Retain pasted-text ingestion as an optional fallback. Do not show success before the backend confirms indexing.
- Add integration tests for all five file types, empty/corrupt/oversized files, unsupported files, deduplication, update, listing, deletion, and isolation across two companies and two projects.

### 4. Replace hash-only “semantic RAG” with real embeddings

`QdrantVectorStore` currently defaults to `FastHashEmbedder`, a lexical hash/ngram projection. It does not use `settings.embedding_model_name`; calling it semantic retrieval is misleading.

- Implement a real configurable embedding provider. Preferred embedder: `nomic-ai/nomic-embed-text-v1.5` through `HuggingFaceEmbedder` (HuggingFace Transformers), with a fixed configured dimension (use 768 consistently) and correctly normalized vectors. Add embedding model/provider/dimension settings, and validate output dimensions before writing to Qdrant. Use the supported `EmbedContentConfig.output_dimensionality` setting; keep the provider's embed call behind an injectable interface for tests.
- Never mix vector dimensions or embedding-model spaces in one collection. Detect an existing collection's configuration, keep its data intact, and use a versioned collection/re-index migration if the embedding model/dimension changes. Do not silently destroy old collections. If the Google embedding key is unavailable, require an explicit configured local semantic embedder or return a clear unavailable/degraded status; do not silently switch production data to hash vectors.
- `FastHashEmbedder` may remain for deterministic unit tests only or as an explicitly labelled degraded lexical fallback. It must not be the silent production default or be called semantic embeddings.
- Reuse a process-level Qdrant client/store for persistent local mode, or manage/close the client lifecycle correctly. Do not open competing local clients for each request against the same storage path. Keep injectable in-memory stores for tests.
- Enforce company and project filters on search, document update/delete, and all API listing operations. `project_id="default"` must not accidentally widen retrieval to every project unless an explicit company-wide query was requested.
- Mark retrieved document citations as source-backed but not independently “verified” unless a verification step exists. Return an explicit insufficient-evidence result below threshold. Add retrieval tests with paraphrases, relevant-vs-irrelevant chunks, dimensionality mismatch, duplicate chunks, and tenant/project isolation.

### 5. Correct specialist logic and financial grounding

- Specialists must use each role-specific prompt and their relevant retrieved evidence, not simply select snippets by keyword and return a fixed template. Have them retrieve agent-specific queries rather than only reusing one vector search and one web search for the original proposal.
- Include relevant scoped company documents, role-specific web results, approved project memory, and clear source excerpts as **untrusted data**, never as instructions. Defend against document/web prompt injection by isolating content in prompts and explicitly instructing models not to follow instructions inside sources; regex replacement alone is not sufficient.
- Every material evidence-backed conclusion must cite an actual supporting source ID/URL/document location. Do not create citations that were not returned by a tool. Explicitly separate facts, assumptions, inferences, contradictions, and missing information.
- FinanceAgent currently creates a hard-coded stress test for revenue 100,000/costs 80,000 and discards the result. Remove this placeholder. Extract financial inputs into a typed schema with provenance, units, currency and source references; run `tools/calculation_tools.py` only when required inputs are present. Never infer real financial values just to complete a calculation. When figures are missing, return the missing fields and scenario assumptions clearly.
- RiskAgent should synthesize the actual specialist findings, explain likelihood/impact and mitigations, and not invent evidence. Use deterministic checks for calculations/mandatory blockers, with an LLM explanation grounded in those findings.
- Do not label all internal citations `verified=True` automatically. Make the schema's meaning of `verified` explicit and consistent.

### 6. Fix decision, planning and criticism behavior

`BusinessDecisionAgent` currently chooses outcomes from citation counts/missing-item counts and never calls its LLM. Planning and critic outputs are generic hard-coded content; the planner invents defaults such as a 100,000 budget, arbitrary budget percentages, 5 pilot agreements, 99.9% uptime, and $250k ARR.

- Use an LLM-generated typed decision assessment with criteria: strategic fit, evidence quality, demand, financial viability, legal feasibility, technical feasibility, risks, alternatives and uncertainties. Show weights if weights are configured. Preserve contradictions; do not decide by citation count alone.
- Keep deterministic guardrails around the LLM. Critical blockers must be backed by explicit evidence or clearly labelled assumptions. Missing critical evidence must result in `HOLD_FOR_EVIDENCE`, not a forced yes/no. Model errors or malformed outputs must never default to `PROCEED`.
- Allow only these outcomes: `PROCEED`, `DO_NOT_PROCEED`, `HOLD_FOR_EVIDENCE`.
- `PROCEED`: call PlanningAgent and produce case-specific phases. Each phase must have objectives, tasks, dependencies, owner roles, timeline estimates, budget estimates with currency/provenance, deliverables, KPIs, risks, acceptance criteria and go/no-go gates. Use provided inputs and citations. If a figure or date is unavailable, use null/“to be estimated” rather than a fake precision; distinguish calculated, source-derived, inferred, and illustrative values.
- `DO_NOT_PROCEED`: call CriticAgent for case-specific fatal blockers, remediable weaknesses, evidence citations, opportunity costs, alternatives, and conditions for reconsideration. Do not append irrelevant fixed alternatives.
- `HOLD_FOR_EVIDENCE`: return a prioritized missing-evidence checklist; create neither an execution plan nor a rejection critique.
- Ensure branch invariants in Pydantic validation and the orchestrator. Do not let the decision model itself trigger arbitrary tools.

### 7. Make memory actually persistent **and used**, with human observability

Memory is saved, but the pipeline never retrieves global/project memory or earlier agent memory for the next analysis. The UI does not expose agent-specific memory records. Several history/memory requests omit `project_id`, so they can display another project's records under the same company.

- Before an agent runs, retrieve only relevant `USER_CONFIRMED` project/company context and recent scoped memory for that specific agent. Clearly label provenance; never promote an AI inference into a verified fact. Do not feed all history into every prompt.
- Pass project memory and agent memory to each relevant agent with IDs so the audit trace can show which records were used.
- Add API/UI observability for global/company context, per-project memory, per-agent memory, run findings, evidence references, tool calls, model/provider/status, errors and timestamps. Support inspect/edit/delete as appropriate.
- Scope all memory, run history, vector search, document listing/deletion and traces by company and project. Keep backward compatibility for existing routes with safe defaults.
- Mark a run `FAILED` if a stage fails; save the exception category and error trace safely. Do not leave it permanently `IN_PROGRESS`. Add `AGENT_START`, `AGENT_COMPLETE`, tool-call, retrieval, decision-branch, and run-failure audit events. Ensure costs/timeouts/retries/concurrency values are loaded from environment variables rather than silently using hard-coded defaults.
- Update `models_invoked` and token/latency statistics only from actual calls. Never log secrets or include raw keys in API errors.

### 8. Safety, API correctness, frontend integration

- Inspect all endpoints and callers. Fix the missing `delete_document` call, add the document list/upload endpoints, scope all relevant requests by project, validate payload size and IDs, and return consistent error envelopes without tracebacks or local paths in public responses.
- Company/project IDs passed as query strings are namespaces, **not authentication**. Either implement authenticated principal-to-company authorization or state clearly that the current app is single-user/local-only, bind backend development startup to `127.0.0.1`, and do not describe it as production-secure multi-tenancy. Never claim tenant security based only on trusting a caller-supplied company ID.
- Update the UI to expose objective, business context, constraints, target market, optional budget/currency, and document selection/upload; do not hard-code constraints as if the user supplied them. Continue to display actual agent findings, sources, contradictions, branch output and downloadable JSON. Keep current visual design and legacy `/api/analyze` path intact.
- The empty `tools/rag_tools.py`, `agents/problem_analyzer.py`, and `app/app.py` must either be implemented if still part of the chosen runtime path or explicitly documented as unused/deprecated; do not leave misleading empty modules wired into imports. Remove only genuinely dead code, not legacy compatibility code.
- Update `.gitignore` to exclude `.pytest_cache/`, `__pycache__/`, frontend `node_modules/` and `dist/`, local Qdrant storage and local DB files. Do not delete existing local DB or Qdrant data during this repair.

## Required verification — do not skip

1. Run `python -m pip install -r requirements.txt` in the project's active virtual environment. Add any genuinely needed runtime dependencies, including `python-multipart` for uploads; keep API requirements consistent with the main requirements.
2. Run `python -m pytest tests/ -v`. Add tests for all bugs above; retain existing tests. Report exact pass/fail counts and the failing test names if any.
3. Run `npm ci` and `npm run build` from `frontend/`. Do not state the build passed if dependency installation or build did not complete.
4. Run backend smoke tests for `/health`, `/api/config/status`, a decision request using mocked model/retrieval services, document upload/list/delete, and all three decision branches.
5. Run optional live smoke tests for Google LLM + embeddings, NVIDIA NIM and Firecrawl only if the respective keys are present. Never print the keys. Report each as PASS, FAIL, or NOT RUN (missing credentials/network), with sanitized reason.
6. Test startup and multiple sequential document requests with local persistent Qdrant. Test company AND project isolation, failed-run persistence, memory retrieval on a second run, and source citation traceability.
7. Update `docs/FINAL_VALIDATION_REPORT.md` to reflect the actual final run. Separate automated mock tests from live integrations. Do not claim “production-ready” or “all phases complete” unless the corresponding acceptance tests genuinely pass.
8. Update README setup instructions, `.env.example`, required model IDs, embedding configuration, Firecrawl runtime setup, upload limits, local-only security boundary, and exact Windows PowerShell startup commands.

## Final response required

After implementation, give a concise handover with: (1) files/components changed, (2) the exact commands run, (3) actual test/build counts, (4) live integrations tested vs not tested, (5) any remaining limitations. Do not start another planning phase and do not stop after making a checklist. Implement, test, fix the failures found by the tests, and then report.
