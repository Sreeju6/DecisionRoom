import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import {
  BrainCircuit,
  Sparkles,
  ArrowRight,
  LoaderCircle,
  Download,
  ChevronDown,
  AlertCircle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ShieldCheck,
  Database,
  History,
  FileText,
  Sliders,
  Trash2,
  Plus,
  RefreshCw,
  ExternalLink,
  Layers,
  Scale,
  TrendingUp,
  Cpu,
  Lock,
  Sun,
  Moon,
  Upload
} from "lucide-react";
import "./styles.css";

const API = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const THEME_KEY = "dr-theme";

function initialTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* storage unavailable */ }
  try {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  } catch {
    return "dark";
  }
}

function useDebounced(value, delay = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// Backend errors arrive as {detail: string} or pydantic's {detail: [{loc, msg}, ...]}
function errMsg(data, fallback) {
  const detail = data?.detail ?? data?.error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
  }
  return fallback;
}

const DEFAULT_PROPOSAL = "Should our B2B SaaS company expand operations into the German DACH market with a local European cloud infrastructure deployment, and what regulatory, unit economics, and competitive barriers must be resolved?";

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function textOf(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(textOf).filter(Boolean).join("\n");
  if (typeof value === "object") {
    if (value.summary) return textOf(value.summary);
    if (value.description) return textOf(value.description);
    if (value.content) return textOf(value.content);
    return Object.entries(value)
      .filter(([, v]) => v !== null && v !== undefined && typeof v !== "object")
      .map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`)
      .join(" · ");
  }
  return "";
}

function BranchBadge({ outcome, confidence }) {
  if (outcome === "PROCEED") {
    return (
      <div className="branch-badge proceed">
        <CheckCircle2 size={18} />
        <div>
          <span className="badge-title">PROCEED</span>
          <span className="badge-subtitle">{confidence || "HIGH"} CONFIDENCE</span>
        </div>
      </div>
    );
  }
  if (outcome === "DO_NOT_PROCEED") {
    return (
      <div className="branch-badge reject">
        <XCircle size={18} />
        <div>
          <span className="badge-title">DO NOT PROCEED</span>
          <span className="badge-subtitle">{confidence || "HIGH"} CONFIDENCE</span>
        </div>
      </div>
    );
  }
  return (
    <div className="branch-badge hold">
      <HelpCircle size={18} />
      <div>
        <span className="badge-title">HOLD FOR EVIDENCE</span>
        <span className="badge-subtitle">{confidence || "LOW"} CONFIDENCE</span>
      </div>
    </div>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState("decision_room");
  const [companyId, setCompanyId] = useState("acme_corp");
  const [projectId, setProjectId] = useState("eu_expansion");

  // Theme (index.html sets data-theme pre-paint; this syncs toggles + persists)
  const [theme, setTheme] = useState(initialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === "light" ? "#f4f5fa" : "#090a15";
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* ignore */ }
  }, [theme]);

  // Debounced tenant/project inputs drive passive fetches (per-keystroke fetch storms otherwise)
  const debouncedCompanyId = useDebounced(companyId);
  const debouncedProjectId = useDebounced(projectId);

  // Decision Room State
  const [proposal, setProposal] = useState(DEFAULT_PROPOSAL);
  const [objective, setObjective] = useState("Strategic Expansion Evaluation");
  const [targetMarket, setTargetMarket] = useState("European Union (Germany)");
  const [budgetLimit, setBudgetLimit] = useState("150000");
  const [currency, setCurrency] = useState("USD");
  const [constraintsText, setConstraintsText] = useState("Statutory compliance clearance, Positive unit margin runway");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  // Runs / History State
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runTraces, setRunTraces] = useState([]);
  const [loadingRuns, setLoadingRuns] = useState(false);

  // Memory State
  const [memoryItems, setMemoryItems] = useState([]);
  const [memCategory, setMemCategory] = useState("constraint");
  const [memContent, setMemContent] = useState("");
  const [memProvenance, setMemProvenance] = useState("user_confirmed");

  // Document Library & Upload State
  const [documents, setDocuments] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadFeedback, setUploadFeedback] = useState(null);
  const [showPastedText, setShowPastedText] = useState(false);

  // Document Pasted Text Ingest State (Fallback)
  const [docName, setDocName] = useState("");
  const [docSection, setDocSection] = useState("Executive Summary");
  const [docText, setDocText] = useState("");
  const [docIngestMsg, setDocIngestMsg] = useState("");

  // Config Status
  const [configStatus, setConfigStatus] = useState(null);

  // Elapsed-time ticker for the evaluate loading card (runs take minutes)
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!loading) { setElapsed(0); return; }
    const startedAt = Date.now();
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(t);
  }, [loading]);

  useEffect(() => {
    if (activeTab === "decision_room" || activeTab === "documents") fetchDocuments();
    if (activeTab === "history") fetchRuns();
    if (activeTab === "memory") fetchMemory();
    if (activeTab === "settings") fetchConfig();
  }, [activeTab, debouncedCompanyId, debouncedProjectId]);

  async function fetchConfig() {
    try {
      const res = await fetch(`${API}/api/config/status`);
      if (res.ok) setConfigStatus(await res.json());
    } catch (e) {
      console.error(e);
    }
  }

  // Passive fetchers default to the debounced tenant scope; pass live values after mutations.
  async function fetchRuns(company = debouncedCompanyId) {
    setLoadingRuns(true);
    try {
      const res = await fetch(`${API}/api/runs?company_id=${encodeURIComponent(company)}`);
      if (res.ok) setRuns(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingRuns(false);
    }
  }

  async function inspectRun(runId) {
    try {
      const res = await fetch(`${API}/api/runs/${runId}?company_id=${encodeURIComponent(companyId)}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedRun(data.run);
        setRunTraces(data.traces || []);
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function fetchMemory(company = debouncedCompanyId) {
    try {
      const res = await fetch(`${API}/api/memory?company_id=${encodeURIComponent(company)}`);
      if (res.ok) setMemoryItems(await res.json());
    } catch (e) {
      console.error(e);
    }
  }

  async function addMemoryItem(e) {
    e.preventDefault();
    if (!memContent.trim()) return;
    try {
      const res = await fetch(`${API}/api/memory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_id: companyId,
          project_id: projectId,
          category: memCategory,
          content: memContent.trim(),
          provenance: memProvenance,
        }),
      });
      if (res.ok) {
        setMemContent("");
        fetchMemory(companyId, projectId);
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function deleteMemoryItem(memId) {
    try {
      const res = await fetch(`${API}/api/memory/${memId}?company_id=${encodeURIComponent(companyId)}`, {
        method: "DELETE",
      });
      if (res.ok) fetchMemory(companyId, projectId);
    } catch (e) {
      console.error(e);
    }
  }

  async function fetchDocuments(company = debouncedCompanyId, project = debouncedProjectId) {
    setLoadingDocs(true);
    try {
      const res = await fetch(`${API}/api/documents?company_id=${encodeURIComponent(company)}&project_id=${encodeURIComponent(project)}`);
      if (res.ok) {
        setDocuments(await res.json());
      }
    } catch (e) {
      console.error("fetchDocuments error:", e);
    } finally {
      setLoadingDocs(false);
    }
  }

  async function handleFileUpload(e) {
    e.preventDefault();
    if (!selectedFile) return;
    setUploading(true);
    setUploadFeedback(null);
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const res = await fetch(
        `${API}/api/documents/upload?company_id=${encodeURIComponent(companyId)}&project_id=${encodeURIComponent(projectId)}`,
        {
          method: "POST",
          body: formData,
        }
      );
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setUploadFeedback({
          type: "success",
          message: `Indexed "${data.document_name}" (${data.chunks_indexed} chunk(s) stored in Qdrant).`,
        });
        setSelectedFile(null);
        const fileInput = document.getElementById("docFileInput");
        if (fileInput) fileInput.value = "";
        fetchDocuments(companyId, projectId);
      } else {
        setUploadFeedback({
          type: "error",
          message: errMsg(data, "File upload and indexing failed."),
        });
      }
    } catch (err) {
      setUploadFeedback({ type: "error", message: err.message });
    } finally {
      setUploading(false);
    }
  }

  async function deleteDocument(docHash, docName) {
    if (!window.confirm(`Are you sure you want to delete "${docName}" and remove all indexed vector chunks?`)) {
      return;
    }
    try {
      const res = await fetch(
        `${API}/api/documents/${encodeURIComponent(docHash)}?company_id=${encodeURIComponent(companyId)}&project_id=${encodeURIComponent(projectId)}`,
        { method: "DELETE" }
      );
      if (res.ok) {
        fetchDocuments(companyId, projectId);
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`Delete failed: ${errMsg(err, "Unknown error")}`);
      }
    } catch (err) {
      alert(`Delete error: ${err.message}`);
    }
  }

  async function ingestDocument(e) {
    e.preventDefault();
    if (!docName.trim() || !docText.trim()) return;
    setDocIngestMsg("Indexing document chunks into vector database...");
    try {
      const res = await fetch(`${API}/api/documents/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_id: companyId,
          project_id: projectId,
          document_name: docName.trim(),
          text: docText.trim(),
          page_or_section: docSection.trim() || "General",
        }),
      });
      if (res.ok) {
        const d = await res.json();
        setDocIngestMsg(`Success: Indexed ${d.chunks_indexed} chunk(s) into company isolation scope.`);
        setDocName("");
        setDocText("");
        fetchDocuments(companyId, projectId);
      } else {
        const err = await res.json().catch(() => ({}));
        setDocIngestMsg(`Error: ${errMsg(err, "Ingestion failed")}`);
      }
    } catch (err) {
      setDocIngestMsg(`Error: ${err.message}`);
    }
  }

  async function submitDecision(e) {
    e.preventDefault();
    if (!proposal.trim() || proposal.trim().length < 5) {
      setError("Please provide a proposal with at least 5 characters.");
      return;
    }
    setLoading(true);
    setError("");
    setReport(null);
    try {
      const constraintsList = constraintsText
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);

      const res = await fetch(`${API}/api/decision?company_id=${encodeURIComponent(companyId)}&project_id=${encodeURIComponent(projectId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          proposal: proposal.trim(),
          objective: objective.trim() || "Strategic Evaluation",
          company_name: companyId,
          target_market_or_state: targetMarket.trim(),
          budget_limit: budgetLimit ? parseFloat(budgetLimit) : null,
          currency: currency.trim() || "USD",
          constraints: constraintsList.length > 0 ? constraintsList : ["Statutory compliance clearance"],
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(errMsg(data, `Evaluation error (${res.status})`));
      setReport(data);
    } catch (err) {
      // Network failures (fetch rejects with TypeError) mean the backend is unreachable;
      // HTTP errors already carry a meaningful message from the API.
      setError(err instanceof TypeError
        ? `${err.message}. Verify that the DecisionRoom backend is active.`
        : err.message);
    } finally {
      setLoading(false);
    }
  }

  function downloadReport() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `decisionroom_${report.run_id || "report"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const outcome = report?.outcome || report?.final_decision_agent?.recommendation || "HOLD_FOR_EVIDENCE";
  const confidence = report?.confidence || report?.final_decision_agent?.confidence || "MEDIUM";
  const phases = report?.execution_phases || [];
  const criticRationale = report?.critic_rejection_rationale;
  const missingChecklist = report?.missing_evidence_checklist || [];
  const specialistFindings = report?.agent_findings || {};
  const evidenceList = report?.all_evidence || report?.research_agent?.results || [];

  return (
    <div className="page">
      {/* Top Header */}
      <header className="topbar">
        <div className="brand">
          <span className="brand-icon"><BrainCircuit size={28} /></span>
          Decision<span className="brand-light">Room</span>
          <span className="enterprise-tag">ENTERPRISE SUPPORT</span>
        </div>
        <div className="topbar-controls">
          <div className="tenant-selector">
            <ShieldCheck size={14} className="tenant-icon" />
            <span className="tenant-label">TENANT:</span>
            <input
              type="text"
              className="tenant-input"
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              title="Multi-tenant company isolation ID"
            />
          </div>
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <span className={`status ${loading ? "busy" : report ? "done" : ""}`}>
            <i />
            {loading ? "Reconciling Agents" : report ? "Decision Reconciled" : "System Ready"}
          </span>
        </div>
      </header>

      {/* Primary Navigation Tabs */}
      <nav className="tab-bar">
        <button
          className={`tab-btn ${activeTab === "decision_room" ? "active" : ""}`}
          onClick={() => setActiveTab("decision_room")}
        >
          <Layers size={16} /> Decision Room
        </button>
        <button
          className={`tab-btn ${activeTab === "history" ? "active" : ""}`}
          onClick={() => setActiveTab("history")}
        >
          <History size={16} /> Run History & Audit
        </button>
        <button
          className={`tab-btn ${activeTab === "memory" ? "active" : ""}`}
          onClick={() => setActiveTab("memory")}
        >
          <Database size={16} /> Project Memory
        </button>
        <button
          className={`tab-btn ${activeTab === "documents" ? "active" : ""}`}
          onClick={() => setActiveTab("documents")}
        >
          <FileText size={16} /> Document RAG
        </button>
        <button
          className={`tab-btn ${activeTab === "settings" ? "active" : ""}`}
          onClick={() => setActiveTab("settings")}
        >
          <Sliders size={16} /> Status & Providers
        </button>
      </nav>

      <main>
        {/* ============================================================== */}
        {/* TAB 1: DECISION ROOM                                           */}
        {/* ============================================================== */}
        {activeTab === "decision_room" && (
          <div className="tab-pane">
            <section className="hero">
              <div className="eyebrow"><Sparkles size={13} /> CONTROLLED MULTI-AGENT SYNTHESIS</div>
              <h1>Multi-Agent Decision Support Room</h1>
              <p>Reconciling specialist evidence with deterministic 3-way branching: Proceed, Do Not Proceed, or Hold for Evidence.</p>
            </section>

            <form className="question-card" onSubmit={submitDecision}>
              <div className="form-row">
                <div className="form-col">
                  <label htmlFor="objective">Strategic Objective</label>
                  <input
                    id="objective"
                    type="text"
                    value={objective}
                    onChange={(e) => setObjective(e.target.value)}
                    placeholder="e.g. Strategic Expansion Evaluation"
                  />
                </div>
                <div className="form-col">
                  <label htmlFor="targetMarket">Target Market / Geography</label>
                  <input
                    id="targetMarket"
                    type="text"
                    value={targetMarket}
                    onChange={(e) => setTargetMarket(e.target.value)}
                    placeholder="e.g. Germany (DACH), Tamil Nadu, California"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-col">
                  <label htmlFor="budgetLimit">Budget Limit</label>
                  <input
                    id="budgetLimit"
                    type="number"
                    value={budgetLimit}
                    onChange={(e) => setBudgetLimit(e.target.value)}
                    placeholder="e.g. 150000"
                  />
                </div>
                <div className="form-col">
                  <label htmlFor="currency">Currency</label>
                  <select
                    id="currency"
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                  >
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                    <option value="SGD">SGD (S$)</option>
                    <option value="INR">INR (₹)</option>
                  </select>
                </div>
              </div>

              <label htmlFor="constraints">Operating Constraints & Policies (comma-separated)</label>
              <input
                id="constraints"
                type="text"
                value={constraintsText}
                onChange={(e) => setConstraintsText(e.target.value)}
                placeholder="e.g. GDPR compliance, Local EU data residency, 6-month launch window"
              />

              <div className="form-doc-hint">
                <FileText size={13} />
                <span>RAG Evidence Scope: <b>{documents.length} document(s)</b> indexed for {companyId} / {projectId}.</span>
                <button type="button" className="text-link-btn" onClick={() => setActiveTab("documents")}>
                  Manage Library &rarr;
                </button>
              </div>

              <label htmlFor="proposal">Business Case Proposal / Strategic Question</label>
              <textarea
                id="proposal"
                rows={3}
                value={proposal}
                onChange={(e) => setProposal(e.target.value)}
                placeholder="Enter the business proposal or strategic question for domain specialists..."
              />

              <div className="form-footer">
                <span className="provenance-note">
                  <Lock size={12} /> Tenant scope: <b>{companyId}</b> · Strict isolation enforced
                </span>
                <button type="submit" className="primary" disabled={loading}>
                  {loading ? (
                    <><LoaderCircle className="spin" size={17} /> Running Specialist Analysis…</>
                  ) : (
                    <><Sparkles size={16} /> Evaluate Business Case <ArrowRight size={17} /></>
                  )}
                </button>
              </div>
            </form>

            {error && (
              <div className="error">
                <AlertCircle size={18} />
                <span>{error}</span>
              </div>
            )}

            {loading && (
              <div className="loading-card">
                <LoaderCircle className="spin" size={24} />
                <div>
                  <b>Evaluating Multi-Agent Decision Branches</b>
                  <p>Executing Sales, Finance, Legal, Technical, and Risk specialists; consulting vector RAG and synthesizing evidence...</p>
                  <span className="elapsed-note">{elapsed}s elapsed — multi-agent runs typically take 1–3 minutes</span>
                </div>
              </div>
            )}

            {/* Reconciled Report */}
            {report && (
              <section className="results">
                <div className="result-heading">
                  <div>
                    <div className="result-eyebrow">DECISION ROOM SYNTHESIS</div>
                    <h2>Reconciled Executive Brief</h2>
                  </div>
                  <button className="download" onClick={downloadReport}>
                    <Download size={15} /> Export Report JSON
                  </button>
                </div>

                {/* Primary Decision Card with Controlled Branching Badge */}
                <article className="decision-card">
                  <div className="decision-header">
                    <BranchBadge outcome={outcome} confidence={confidence} />
                    <div className="decision-meta">
                      <span>Run ID: <code>{report.run_id?.slice(0, 8)}</code></span>
                      <span>Target: <b>{targetMarket}</b></span>
                    </div>
                  </div>

                  <div className="decision-justification">
                    <h4>Authoritative Decision Rationale</h4>
                    <p>{report.justification || report.final_decision_agent?.justification}</p>
                  </div>

                  {report.conditions && report.conditions.length > 0 && (
                    <div className="conditions-box">
                      <b>Prerequisite Conditions & Acceptance Criteria:</b>
                      <ul>
                        {report.conditions.map((c, i) => <li key={i}>{c}</li>)}
                      </ul>
                    </div>
                  )}
                </article>

                {/* Branch 1: Execution Phases (On PROCEED) */}
                {outcome === "PROCEED" && phases.length > 0 && (
                  <section className="branch-section proceed-section">
                    <div className="branch-header">
                      <CheckCircle2 size={20} className="branch-icon-proceed" />
                      <div>
                        <h3>Sequential Phased Execution Roadmap</h3>
                        <p>Mandatory gate criteria and deliverables generated by PlanningAgent on PROCEED.</p>
                      </div>
                    </div>
                    <div className="phase-grid">
                      {phases.map((phase) => (
                        <div key={phase.phase_number} className="phase-card">
                          <div className="phase-badge">Phase {phase.phase_number}</div>
                          <h4>{phase.title}</h4>
                          <p className="phase-objective"><b>Objective:</b> {phase.objective}</p>
                          <div className="phase-stats">
                            <span>Owner: <b>{phase.owner_role}</b></span>
                            <span>Duration: <b>{phase.duration_estimate}</b></span>
                            {phase.cost_estimate && (
                              <span>Est. Cost: <b>${phase.cost_estimate.toLocaleString()}</b></span>
                            )}
                          </div>
                          <div className="phase-tasks">
                            <b>Granular Action Items:</b>
                            <ul>
                              {phase.tasks.map((task, idx) => <li key={idx}>{task}</li>)}
                            </ul>
                          </div>
                          <div className="phase-gate">
                            <b>Go / No-Go Gate:</b> {phase.acceptance_gate}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* Branch 2: Critic Rejection Rationale (On DO_NOT_PROCEED) */}
                {outcome === "DO_NOT_PROCEED" && criticRationale && (
                  <section className="branch-section reject-section">
                    <div className="branch-header">
                      <XCircle size={20} className="branch-icon-reject" />
                      <div>
                        <h3>Critic Rejection Rationale & Remediations</h3>
                        <p>Identified fatal blockers and strategic alternatives generated by CriticAgent.</p>
                      </div>
                    </div>
                    <div className="critique-content">
                      <div className="blocker-box fatal">
                        <b>Fatal Non-Viability Blockers:</b>
                        <ul>
                          {(criticRationale.fatal_blockers || []).map((b, i) => <li key={i}>{b}</li>)}
                        </ul>
                      </div>
                      {criticRationale.remediable_weaknesses?.length > 0 && (
                        <div className="blocker-box remediable">
                          <b>Remediable Weaknesses:</b>
                          <ul>
                            {criticRationale.remediable_weaknesses.map((w, i) => <li key={i}>{w}</li>)}
                          </ul>
                        </div>
                      )}
                      {criticRationale.strategic_alternatives?.length > 0 && (
                        <div className="blocker-box alternatives">
                          <b>Strategic Alternatives to Explore:</b>
                          <ul>
                            {criticRationale.strategic_alternatives.map((a, i) => <li key={i}>{a}</li>)}
                          </ul>
                        </div>
                      )}
                    </div>
                  </section>
                )}

                {/* Branch 3: Missing Evidence Checklist (On HOLD_FOR_EVIDENCE) */}
                {outcome === "HOLD_FOR_EVIDENCE" && (
                  <section className="branch-section hold-section">
                    <div className="branch-header">
                      <HelpCircle size={20} className="branch-icon-hold" />
                      <div>
                        <h3>Missing Evidence Checklist</h3>
                        <p>Proposal held pending empirical documentation. Execution plans are withheld.</p>
                      </div>
                    </div>
                    <div className="checklist-box">
                      <ul>
                        {(missingChecklist.length > 0 ? missingChecklist : report.evidence_gaps || [
                          "Verified financial unit economic model",
                          "Statutory licensing review documentation",
                          "Customer pilot LOI commitments"
                        ]).map((item, i) => (
                          <li key={i}>
                            <FileText size={14} /> <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </section>
                )}

                {/* Specialist Domain Agent Findings */}
                <section className="specialists-section">
                  <h3>Specialist Agent Assessments</h3>
                  <div className="specialists-grid">
                    {Object.entries(specialistFindings).map(([agentKey, finding]) => (
                      <div key={agentKey} className="specialist-card">
                        <div className="specialist-top">
                          <span className="specialist-name">
                            {agentKey === "sales" && <TrendingUp size={16} />}
                            {agentKey === "finance" && <Scale size={16} />}
                            {agentKey === "legal" && <Lock size={16} />}
                            {agentKey === "technical" && <Cpu size={16} />}
                            {agentKey === "risk" && <ShieldCheck size={16} />}
                            {finding.agent_name || agentKey.toUpperCase()}
                          </span>
                          <span className={`conf-badge ${finding.confidence?.toLowerCase()}`}>
                            {finding.confidence}
                          </span>
                        </div>
                        <p className="specialist-summary">{finding.summary}</p>
                        {finding.risks && finding.risks.length > 0 && (
                          <div className="specialist-risks">
                            <b>Identified Risks ({finding.risks.length}):</b>
                            {finding.risks.slice(0, 2).map((r, i) => (
                              <div key={i} className={`risk-item ${r.severity?.toLowerCase()}`}>
                                <span className="risk-sev">[{r.severity}]</span> {r.description}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>

                {/* Source-Grounded Evidence Citations */}
                {evidenceList.length > 0 && (
                  <section className="citations-section">
                    <h3>Source-Grounded Evidence Citations ({evidenceList.length})</h3>
                    <div className="citations-list">
                      {evidenceList.map((cite, i) => (
                        <div key={i} className="citation-item">
                          <div className="citation-header">
                            <span className="citation-title">
                              <FileText size={14} /> {cite.title || cite.document || `Source ${i+1}`}
                            </span>
                            {cite.page_or_section && (
                              <span className="citation-loc">{cite.page_or_section}</span>
                            )}
                            {cite.verified && <span className="verified-badge">VERIFIED</span>}
                          </div>
                          <p className="citation-snippet">"{cite.snippet}"</p>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </section>
            )}

            {!report && !loading && (
              <div className="empty-state">
                <BrainCircuit size={28} />
                <div>
                  <b>Decision Room is Standing By</b>
                  <p>Configure proposal parameters and click <b>Evaluate Business Case</b> to execute the specialist agents.</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 2: RUN HISTORY & AUDIT TRACES                              */}
        {/* ============================================================== */}
        {activeTab === "history" && (
          <div className="tab-pane">
            <div className="pane-header">
              <div>
                <h2>Execution History & Observability</h2>
                <p>Auditable log of analysis runs and granular trace events for tenant: <b>{companyId}</b></p>
              </div>
              <button className="action-btn" onClick={() => fetchRuns()} disabled={loadingRuns}>
                <RefreshCw size={14} className={loadingRuns ? "spin" : ""} /> Refresh Runs
              </button>
            </div>

            <div className="runs-layout">
              <div className="runs-table-box">
                {runs.length === 0 ? (
                  <p className="empty-msg">No historical runs recorded for this tenant yet.</p>
                ) : (
                  <table className="runs-table">
                    <thead>
                      <tr>
                        <th>Timestamp</th>
                        <th>Proposal</th>
                        <th>Outcome</th>
                        <th>Confidence</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((r) => (
                        <tr key={r.run_id} className={selectedRun?.run_id === r.run_id ? "active-row" : ""}>
                          <td>{new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
                          <td className="truncate-cell">{r.proposal}</td>
                          <td>
                            <span className={`outcome-chip ${(r.outcome || (r.status === "FAILED" ? "failed" : "")).toLowerCase()}`}>
                              {r.outcome || (r.status === "FAILED" ? "FAILED" : "PENDING")}
                            </span>
                          </td>
                          <td>{r.confidence || "N/A"}</td>
                          <td>
                            <button className="inspect-btn" onClick={() => inspectRun(r.run_id)}>
                              Inspect Traces
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Selected Run Details and Granular Audit Traces */}
              {selectedRun && (
                <div className="run-inspector">
                  <div className="inspector-header">
                    <h4>Run Audit Trace: <code>{selectedRun.run_id}</code></h4>
                    <span className="run-status-chip">{selectedRun.status}</span>
                  </div>
                  <p className="inspector-proposal"><b>Proposal:</b> {selectedRun.proposal}</p>
                  
                  <div className="trace-timeline">
                    <b>Trace Events ({runTraces.length}):</b>
                    {runTraces.map((t) => (
                      <div key={t.trace_id} className="trace-event">
                        <div className="trace-time">
                          {new Date(t.timestamp).toLocaleTimeString()}
                        </div>
                        <div className="trace-info">
                          <span className="trace-type">{t.event_type}</span>
                          <pre className="trace-details">{JSON.stringify(t.details, null, 2)}</pre>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 3: PROJECT MEMORY                                          */}
        {/* ============================================================== */}
        {activeTab === "memory" && (
          <div className="tab-pane">
            <div className="pane-header">
              <div>
                <h2>Persistent Project Memory</h2>
                <p>Curated constraints, confirmed facts, and goals with explicit provenance tracking.</p>
              </div>
              <button className="action-btn" onClick={() => fetchMemory()}>
                <RefreshCw size={14} /> Refresh
              </button>
            </div>

            {/* Ingestion form for confirmed memory */}
            <form className="memory-form" onSubmit={addMemoryItem}>
              <h4>Add Memory Item</h4>
              <div className="form-row">
                <div className="form-col">
                  <label>Category</label>
                  <select value={memCategory} onChange={(e) => setMemCategory(e.target.value)}>
                    <option value="constraint">Constraint</option>
                    <option value="goal">Goal</option>
                    <option value="confirmed_fact">Confirmed Fact</option>
                    <option value="unresolved_question">Unresolved Question</option>
                  </select>
                </div>
                <div className="form-col">
                  <label>Provenance</label>
                  <select value={memProvenance} onChange={(e) => setMemProvenance(e.target.value)}>
                    <option value="user_confirmed">USER CONFIRMED (Authoritative)</option>
                    <option value="source_derived">SOURCE DERIVED (Documented)</option>
                    <option value="ai_inference">AI INFERENCE (Hypothesis)</option>
                  </select>
                </div>
              </div>
              <textarea
                rows={2}
                value={memContent}
                onChange={(e) => setMemContent(e.target.value)}
                placeholder="Enter context, approved constraint, or confirmed decision boundary..."
              />
              <button type="submit" className="primary mem-submit">
                <Plus size={15} /> Save to Memory
              </button>
            </form>

            <div className="memory-list">
              {memoryItems.length === 0 ? (
                <p className="empty-msg">No persistent memory items configured for {companyId}.</p>
              ) : (
                memoryItems.map((item) => (
                  <div key={item.memory_id} className="memory-item-card">
                    <div className="mem-top">
                      <span className="mem-cat">{item.category.toUpperCase()}</span>
                      <span className={`mem-prov ${item.provenance}`}>{item.provenance}</span>
                      <button className="del-btn" onClick={() => deleteMemoryItem(item.memory_id)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <p className="mem-content">{item.content}</p>
                    <div className="mem-meta">
                      Project: {item.project_id} · Recorded: {new Date(item.created_at).toLocaleDateString()}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 4: DOCUMENT LIBRARY & VECTOR RAG                           */}
        {/* ============================================================== */}
        {activeTab === "documents" && (
          <div className="tab-pane">
            <div className="pane-header">
              <div>
                <h2>Document Library & Vector Ingestion</h2>
                <p>Upload PDF, DOCX, TXT, CSV, or XLSX files. Chunks are embedded and indexed into Qdrant vector storage with strict company ({companyId}) and project ({projectId}) isolation.</p>
              </div>
              <button className="action-btn" onClick={() => fetchDocuments()} disabled={loadingDocs}>
                <RefreshCw size={14} className={loadingDocs ? "spin" : ""} /> Refresh Library
              </button>
            </div>

            {/* Multipart File Upload Card */}
            <div className="upload-card">
              <div className="upload-card-header">
                <Upload size={18} />
                <div>
                  <h4>Upload Document File</h4>
                  <p className="file-help">
                    Supported formats: <b>PDF, DOCX, TXT, CSV, XLSX</b> (Max 15MB). Content is deduplicated by SHA-256 raw bytes.
                  </p>
                </div>
              </div>

              <form onSubmit={handleFileUpload} className="file-upload-form">
                <div className="file-picker-row">
                  <input
                    id="docFileInput"
                    type="file"
                    accept=".pdf,.docx,.txt,.csv,.xlsx"
                    onChange={(e) => {
                      setSelectedFile(e.target.files?.[0] || null);
                      setUploadFeedback(null);
                    }}
                    disabled={uploading}
                  />
                  <button type="submit" className="primary upload-submit" disabled={!selectedFile || uploading}>
                    {uploading ? (
                      <><LoaderCircle className="spin" size={15} /> Parsing & Indexing...</>
                    ) : (
                      <><Upload size={15} /> Upload & Index</>
                    )}
                  </button>
                </div>

                {selectedFile && !uploading && (
                  <div className="file-selected-info">
                    Selected: <b>{selectedFile.name}</b> ({formatBytes(selectedFile.size)})
                  </div>
                )}
              </form>

              {uploadFeedback && (
                <div className={`upload-alert ${uploadFeedback.type}`}>
                  {uploadFeedback.type === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                  <span>{uploadFeedback.message}</span>
                </div>
              )}
            </div>

            {/* Document Library Table */}
            <div className="docs-section">
              <div className="docs-section-header">
                <h3>Indexed Documents ({documents.length})</h3>
                <span className="tenant-scope-tag">Scope: {companyId} / {projectId}</span>
              </div>

              {loadingDocs ? (
                <div className="loading-card">
                  <LoaderCircle className="spin" size={20} />
                  <span>Loading document registry...</span>
                </div>
              ) : documents.length === 0 ? (
                <div className="empty-state doc-empty">
                  <FileText size={28} />
                  <div>
                    <b>No Documents Indexed Yet</b>
                    <p>Upload a PDF, DOCX, CSV, XLSX, or TXT file above to enable source-grounded vector RAG for specialists.</p>
                  </div>
                </div>
              ) : (
                <div className="docs-table-wrapper">
                  <table className="docs-table">
                    <thead>
                      <tr>
                        <th>Document</th>
                        <th>Type</th>
                        <th>Size</th>
                        <th>Chunks</th>
                        <th>Status</th>
                        <th>Ingested</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {documents.map((doc) => (
                        <tr key={doc.doc_hash || doc.document_name}>
                          <td className="doc-name-cell">
                            <FileText size={15} />
                            <span className="doc-name-text" title={doc.document_name}>{doc.document_name}</span>
                          </td>
                          <td>
                            <span className={`doc-type-badge ${doc.doc_type?.toLowerCase()}`}>
                              {(doc.doc_type || "txt").toUpperCase()}
                            </span>
                          </td>
                          <td className="mono-cell">{formatBytes(doc.file_size)}</td>
                          <td>
                            <span className="chunks-badge">{doc.chunk_count || 1} chunk(s)</span>
                          </td>
                          <td>
                            <span className="status-badge indexed">
                              <CheckCircle2 size={12} /> {doc.status || "indexed"}
                            </span>
                          </td>
                          <td className="time-cell">
                            {doc.created_at ? new Date(doc.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : "Just now"}
                          </td>
                          <td>
                            <button
                              className="del-doc-btn"
                              title="Delete document and vector chunks"
                              onClick={() => deleteDocument(doc.doc_hash, doc.document_name)}
                            >
                              <Trash2 size={14} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Collapsible Pasted Text Ingestion (Optional Fallback) */}
            <div className="accordion-section">
              <button
                type="button"
                className="accordion-toggle"
                onClick={() => setShowPastedText(!showPastedText)}
              >
                <span><b>Pasted-Text Ingestion (Optional Fallback)</b> — Quick paste text snippets without uploading files</span>
                <ChevronDown size={16} className={`acc-chevron ${showPastedText ? "open" : ""}`} />
              </button>

              {showPastedText && (
                <form className="ingest-form accordion-body" onSubmit={ingestDocument}>
                  <div className="form-row">
                    <div className="form-col">
                      <label>Document Name</label>
                      <input
                        type="text"
                        value={docName}
                        onChange={(e) => setDocName(e.target.value)}
                        placeholder="e.g. EU_Expansion_Financials_2024.txt"
                      />
                    </div>
                    <div className="form-col">
                      <label>Section or Page</label>
                      <input
                        type="text"
                        value={docSection}
                        onChange={(e) => setDocSection(e.target.value)}
                        placeholder="e.g. Section 3.2 - Compliance"
                      />
                    </div>
                  </div>
                  <label>Document Excerpt Text</label>
                  <textarea
                    rows={4}
                    value={docText}
                    onChange={(e) => setDocText(e.target.value)}
                    placeholder="Paste verbatim excerpt or parsed text to index for semantic retrieval..."
                  />
                  <button type="submit" className="primary">
                    <Database size={15} /> Ingest & Index Text into Qdrant
                  </button>
                  {docIngestMsg && <p className="ingest-feedback">{docIngestMsg}</p>}
                </form>
              )}
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 5: SYSTEM STATUS & PROVIDERS                               */}
        {/* ============================================================== */}
        {activeTab === "settings" && (
          <div className="tab-pane">
            <div className="pane-header">
              <div>
                <h2>System Configuration & Provider Status</h2>
                <p>Verification of approved model registry, secret redaction, and backend connectivity.</p>
              </div>
              <button className="action-btn" onClick={fetchConfig}>
                <RefreshCw size={14} /> Refresh Status
              </button>
            </div>

            {configStatus ? (
              <div className="config-grid">
                <div className="config-card">
                  <h4>Provider Connectivity</h4>
                  <div className="cfg-item">
                    <span>NVIDIA NIM:</span>
                    <b className={configStatus.is_nvidia_configured ? "active" : "inactive"}>
                      {configStatus.is_nvidia_configured ? "CONFIGURED" : "NOT CONFIGURED"}
                    </b>
                  </div>
                  <div className="cfg-item">
                    <span>Google GenAI:</span>
                    <b className={configStatus.is_google_configured ? "active" : "inactive"}>
                      {configStatus.is_google_configured ? "CONFIGURED" : "NOT CONFIGURED"}
                    </b>
                  </div>
                  <div className="cfg-item">
                    <span>Qdrant Vector DB:</span>
                    <b className={configStatus.is_qdrant_configured ? "active" : "inactive"}>
                      {configStatus.is_qdrant_configured ? "REMOTE SERVER" : "LOCAL EMBEDDED"}
                    </b>
                  </div>
                </div>

                <div className="config-card">
                  <h4>Approved Model Registry</h4>
                  <ul className="model-list">
                    {(configStatus.approved_models || []).map((m, i) => (
                      <li key={i}><code>{m}</code></li>
                    ))}
                  </ul>
                </div>

                <div className="config-card full-width">
                  <h4>Redacted Configuration Payload</h4>
                  <p className="cfg-desc">API keys are permanently masked to ensure zero secret leakage in the UI.</p>
                  <pre className="cfg-raw">{JSON.stringify(configStatus, null, 2)}</pre>
                </div>
              </div>
            ) : (
              <p className="empty-msg">Loading configuration status...</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
