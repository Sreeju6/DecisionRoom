import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { BrainCircuit, Sparkles, ArrowRight, LoaderCircle, Download, ChevronDown, AlertCircle } from "lucide-react";
import "./styles.css";

const API = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const DEFAULT_QUESTION = "Should a women-led, early-stage climate-tech startup in Tamil Nadu apply for TANSEED funding under the Tamil Nadu Startup and Innovation Policy 2023, and what risks, eligibility conditions, and alternative funding options should it consider before applying?";

function pick(obj, keys) {
  if (!obj || typeof obj !== "object") return null;
  for (const key of keys) {
    const val = obj[key];
    if (val !== undefined && val !== null && val !== "" && !(Array.isArray(val) && val.length === 0)) return val;
  }
  return null;
}
function textOf(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(textOf).filter(Boolean).join("\n");
  if (typeof value === "object") {
    const first = pick(value, ["summary", "justification", "recommendation", "decision_note", "description", "finding", "risk", "mitigation", "action", "evidence", "text", "preferred_option", "title", "name"]);
    if (first !== null) return textOf(first);
    return Object.entries(value)
      .filter(([, v]) => v !== null && v !== undefined && typeof v !== "object" && String(v).trim())
      .slice(0, 5)
      .map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`)
      .join(" · ");
  }
  return "";
}
function asItems(value, limit = 3) {
  if (!value) return [];
  if (Array.isArray(value)) return value.slice(0, limit);
  return [value];
}
function MiniDetails({ title, items, emptyText }) {
  const arr = asItems(items);
  return <details className="mini-details">
    <summary>{title}<ChevronDown size={15}/></summary>
    <div className="detail-body">
      {arr.length ? arr.map((item, i) => <div className="detail-item" key={i}>{textOf(item)}</div>) : <p className="muted">{emptyText}</p>}
    </div>
  </details>;
}

function App() {
  const [state, setState] = useState("Tamil Nadu");
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    if (!question.trim() || question.trim().length < 10) {
      setError("Please enter a decision question.");
      return;
    }
    setLoading(true);
    setError("");
    setReport(null);
    try {
      const response = await fetch(`${API}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_state: state, decision_question: question.trim() })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || data.error || `Request failed (${response.status})`);
      setReport(data);
    } catch (err) {
      setError(`${err.message}. Check that the Python API is running.`);
    } finally {
      setLoading(false);
    }
  }

  const decision = report?.final_decision_agent || report?.final_decision || report?.decision || null;
  const recommendation = pick(decision, ["preferred_option", "recommended_option", "recommendation", "decision"]) || "Recommendation generated";
  const explanation = pick(decision, ["justification", "decision_note", "summary", "confidence_reason", "reasoning"]);
  const confidence = pick(decision, ["confidence", "confidence_level"]);
  const research = report?.research_agent;
  const risk = report?.risk_agent;
  const critic = report?.critic_agent;
  const planner = report?.planner_agent;

  function downloadReport() {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "decisionroom-report.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  return <div className="page">
    <header className="topbar">
      <div className="brand"><span className="brand-icon"><BrainCircuit size={26}/></span>Decision<span className="brand-light">Room</span></div>
      <span className={`status ${loading ? "busy" : report ? "done" : ""}`}><i/>{loading ? "Analyzing" : report ? "Complete" : "Ready"}</span>
    </header>

    <main>
      <section className="hero">
        <div className="eyebrow"><Sparkles size={13}/> AI DECISION SUPPORT</div>
        <h1>One question.<br/><span>One clear decision brief.</span></h1>
        <p>Review the agent findings and the final recommendation. Nothing extra.</p>
      </section>

      <form className="question-card" onSubmit={submit}>
        <label htmlFor="state">Target state / UT</label>
        <select id="state" value={state} onChange={e => setState(e.target.value)}>
          {["Tamil Nadu", "Karnataka", "Andhra Pradesh", "Delhi", "Gujarat", "Telangana", "Maharashtra", "Kerala", "Haryana", "India"].map(s => <option key={s}>{s}</option>)}
        </select>
        <label htmlFor="question">Decision question</label>
        <textarea id="question" rows="3" value={question} onChange={e => setQuestion(e.target.value)} placeholder="What decision should the agents analyze?"/>
        <button type="submit" className="primary" disabled={loading}>{loading ? <><LoaderCircle className="spin" size={17}/> Analyzing agents…</> : <><Sparkles size={16}/> Analyze decision <ArrowRight size={17}/></>}</button>
      </form>

      {error && <div className="error"><AlertCircle size={18}/><span>{error}</span></div>}

      {loading && <div className="loading-card"><LoaderCircle className="spin" size={20}/><div><b>Agents are analyzing your question</b><p>Retrieving evidence, checking risks and comparing options. This may take a little while.</p></div></div>}

      {report && <section className="results">
        <div className="result-heading"><div><div className="result-eyebrow">FINAL DECISION</div><h2>Your recommendation</h2></div><button className="download" onClick={downloadReport}><Download size={15}/> JSON</button></div>
        <article className="decision-card">
          <div className="decision-top"><div className="decision-mark"><Sparkles size={19}/></div><div className="decision-choice">{textOf(recommendation)}</div>{confidence && <span className="confidence">{textOf(confidence)} confidence</span>}</div>
          {explanation && <p className="explanation">{textOf(explanation)}</p>}
          {decision?.evidence_gaps && <div className="gap"><b>Evidence gaps</b><p>{textOf(decision.evidence_gaps)}</p></div>}
          {decision?.conditions_before_expansion && <div className="gap"><b>Before acting</b><p>{textOf(decision.conditions_before_expansion)}</p></div>}
        </article>

        <section className="agent-findings">
          <h3>Agent findings</h3>
          <p className="helper">Open only the details you need.</p>
          <MiniDetails title="Research evidence" items={pick(research, ["results", "evidence", "records", "items"])} emptyText={textOf(pick(research, ["summary", "conclusion"])) || "No separate evidence list was returned."}/>
          <MiniDetails title="Key risks" items={pick(risk, ["risks", "identified_risks", "risk_items", "findings"])} emptyText={textOf(pick(risk, ["summary", "overall_risk", "conclusion"])) || "No separate risk list was returned."}/>
          <MiniDetails title="Critic findings" items={pick(critic, ["findings", "critic_findings", "issues", "evidence_gaps"])} emptyText={textOf(pick(critic, ["summary", "overall_assessment", "conclusion"])) || "No separate critic findings were returned."}/>
          <MiniDetails title="Alternative plans" items={pick(planner, ["plans", "options", "alternatives"])} emptyText={textOf(pick(planner, ["summary", "planning_summary", "conclusion"])) || "No separate options were returned."}/>
        </section>
        <p className="disclaimer">DecisionRoom supports decision-making; verify important facts before acting.</p>
      </section>}

      {!report && !loading && <div className="empty-state"><BrainCircuit size={20}/><div><b>Your decision brief will appear here</b><p>Enter your question and click Analyze decision.</p></div></div>}
    </main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App/>);
