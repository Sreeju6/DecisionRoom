"""Unified DecisionRoom execution pipeline and business decision orchestrator.

Extracts multi-agent orchestration into a single, robust, and tested orchestrator.
Supports both:
- run_business_decision: Modern multi-agent business decision support system with
  specialist agents, Qdrant evidence retrieval, Firecrawl web search,
  controlled branching (PROCEED / DO_NOT_PROCEED / HOLD_FOR_EVIDENCE),
  and SQLite-backed persistent memory and auditability.
- run_pipeline: Backward-compatible legacy pipeline ensuring existing frontend
  and reports remain functional.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.config import settings
from schemas.decision import (
    AgentFinding,
    BusinessCase,
    ConfidenceLevel,
    DecisionResult,
    EvidenceCitation,
    ExecutionPhase,
    OutcomeType,
)
from tools.memory import (
    AgentMemoryItem,
    MemoryStore,
    ProvenanceType,
    RunRecord,
)

logger = logging.getLogger("decisionroom.pipeline")


def _is_funding_question(question: str) -> bool:
    """Detect whether a question pertains to seed/grant funding programs."""
    q = question.casefold()
    funding_terms = (
        "tanseed",
        "funding application",
        "apply for funding",
        "grant application",
        "seed funding",
        "should we apply",
    )
    return any(term in q for term in funding_terms)


def json_safe(value: Any) -> Any:
    """Recursively convert nested agent outputs into JSON-serializable primitives."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "model_dump"):
        try:
            return json_safe(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "to_dict"):
        try:
            return json_safe(value.to_dict())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def run_business_decision(
    case: BusinessCase,
    company_id: str = "default",
    project_id: str = "default",
    save_report: bool = True,
    memory_store: Optional[MemoryStore] = None,
) -> Dict[str, Any]:
    """Execute the multi-agent business decision support workflow.

    Enforces:
    - Evidence retrieval via Qdrant and WebResearchService.
    - Specialist domain analysis (Sales, Finance, Legal, Technical, Risk).
    - Memory persistence and granular audit tracing in SQLite.
    - Deterministic 3-way decision branching:
      * PROCEED -> PlanningAgent produces ExecutionPhases.
      * DO_NOT_PROCEED -> CriticAgent produces RejectionRationale & Alternatives.
      * HOLD_FOR_EVIDENCE -> Returns Missing Evidence Checklist.
    """
    memory = memory_store or MemoryStore()
    run_id = str(uuid.uuid4())
    run_record = RunRecord(
        run_id=run_id,
        company_id=company_id,
        project_id=project_id,
        proposal=case.proposal,
        status="IN_PROGRESS",
        models_invoked=[],  # populated from actual calls at completion
    )
    memory.save_run(run_record)

    memory.log_audit_event(
        run_id=run_id,
        company_id=company_id,
        event_type="RUN_START",
        details={"case": case.model_dump(), "company_id": company_id, "project_id": project_id},
    )

    try:
        return _execute_business_decision(
            case=case,
            company_id=company_id,
            project_id=project_id,
            save_report=save_report,
            memory=memory,
            run_id=run_id,
            run_record=run_record,
        )
    except Exception as exc:
        # Persist the failure so run history never shows a phantom IN_PROGRESS run
        logger.exception("Run %s failed", run_id)
        run_record.status = "FAILED"
        run_record.completed_at = datetime.now(timezone.utc).isoformat()
        run_record.errors = [f"{type(exc).__name__}: {str(exc)[:300]}"]
        memory.save_run(run_record)
        memory.log_audit_event(
            run_id=run_id,
            company_id=company_id,
            event_type="RUN_FAILED",
            details={"error_type": type(exc).__name__, "message": str(exc)[:500]},
        )
        raise


def _execute_business_decision(
    case: BusinessCase,
    company_id: str,
    project_id: str,
    save_report: bool,
    memory: MemoryStore,
    run_id: str,
    run_record: RunRecord,
) -> Dict[str, Any]:
    """Agent stages of the business decision workflow; caller owns run-record lifecycle."""
    from agents.decision_room import BusinessDecisionAgent
    from agents.specialists import (
        FinanceAgent,
        LegalAgent,
        RiskAgent,
        SalesAgent,
        TechnicalAgent,
    )
    from tools.vector_store import QdrantVectorStore, get_vector_store
    from tools.web_research import WebResearchService

    # Reuse the shared production store; degrade to in-memory hash evidence for this run on failure
    try:
        vector_store = get_vector_store()
    except Exception as exc:
        logger.warning("QdrantVectorStore init failed (%s), using in-memory fallback for this run", exc)
        vector_store = QdrantVectorStore(_force_hash_embedder=True, in_memory=True)
    web_service = WebResearchService()

    # Retrieve prior USER_CONFIRMED project context for this agent session
    prior_memory = []
    try:
        prior_memory = memory.get_project_memory(
            company_id=company_id, project_id=project_id, category="confirmed_fact"
        )
    except Exception as mem_exc:
        logger.debug("Prior memory retrieval skipped: %s", mem_exc)
    prior_context = (
        "\n".join([f"[{m.category}] {m.content}" for m in prior_memory[:5]])
        if prior_memory else "No prior confirmed context for this project."
    )
    logger.info("Retrieved %d prior memory items for run %s", len(prior_memory), run_id[:8])

    # 1. Evidence Retrieval
    start_rag = time.perf_counter()
    try:
        company_evidence = vector_store.search(
            query=case.proposal,
            company_id=company_id,
            project_id=project_id,
            top_k=5,
        )
    except Exception as exc:
        logger.warning("Vector store search failed: %s", exc)
        company_evidence = []
    try:
        web_evidence = web_service.get_citations(query=case.proposal, limit=3)
    except Exception as exc:
        logger.warning("Web research failed: %s", exc)
        web_evidence = []
    rag_latency = round((time.perf_counter() - start_rag) * 1000, 2)

    memory.log_audit_event(
        run_id=run_id,
        company_id=company_id,
        event_type="EVIDENCE_RETRIEVED",
        details={
            "company_citations": len(company_evidence),
            "web_citations": len(web_evidence),
            "latency_ms": rag_latency,
            "prior_memory_items": len(prior_memory),
        },
    )

    # 2. Specialist Domain Analysis
    specialists = [
        ("sales", SalesAgent()),
        ("finance", FinanceAgent()),
        ("legal", LegalAgent()),
        ("technical", TechnicalAgent()),
    ]
    findings: Dict[str, AgentFinding] = {}

    models_invoked: list = []

    for name, agent in specialists:
        memory.log_audit_event(
            run_id=run_id,
            company_id=company_id,
            event_type="AGENT_START",
            details={"agent": name, "model": settings.model_specialist},
        )
        start_t = time.perf_counter()
        try:
            f = agent.analyze(case, company_evidence, web_evidence)
        except Exception as exc:
            logger.error("Specialist agent '%s' failed: %s", name, exc)
            memory.log_audit_event(
                run_id=run_id, company_id=company_id,
                event_type="AGENT_ERROR",
                details={"agent": name, "error": type(exc).__name__, "message": str(exc)[:500]},
            )
            # Degrade to a placeholder finding instead of failing the whole run;
            # the decision agent already treats low-confidence/no-evidence findings as gaps.
            findings[name] = AgentFinding(
                agent_name=name.capitalize(),
                summary=f"{name.capitalize()} analysis unavailable due to an agent error ({type(exc).__name__}).",
                confidence=ConfidenceLevel.LOW,
                confidence_rationale="Specialist agent failed; treat this domain as unverified.",
                missing_information=[f"{name.capitalize()} analysis could not be produced (agent error)."],
            )
            continue
        lat = round((time.perf_counter() - start_t) * 1000, 2)
        findings[name] = f
        # Track the model only when the LLM was actually invoked (rule-based fallbacks don't count)
        if getattr(agent, "last_llm_used", False):
            models_invoked.append(settings.model_specialist)

        memory.save_agent_memory(
            AgentMemoryItem(
                company_id=company_id,
                project_id=project_id,
                run_id=run_id,
                agent_name=name,
                content=f.summary,
                provenance=ProvenanceType.AI_INFERENCE,
                evidence_source_ids=[c.source_id for c in f.evidence_citations],
                confidence=f.confidence.value,
            )
        )
        memory.log_audit_event(
            run_id=run_id,
            company_id=company_id,
            event_type="AGENT_COMPLETE",
            details={
                "agent": name,
                "confidence": f.confidence.value,
                "risks_count": len(f.risks),
                "citations_count": len(f.evidence_citations),
                "latency_ms": lat,
            },
        )

    # Risk Agent synthesizes all 4
    start_r = time.perf_counter()
    risk_agent = RiskAgent()
    findings["risk"] = risk_agent.analyze(case, findings)
    if getattr(risk_agent, "last_llm_used", False):
        models_invoked.append(settings.model_specialist)
    risk_lat = round((time.perf_counter() - start_r) * 1000, 2)

    memory.save_agent_memory(
        AgentMemoryItem(
            company_id=company_id,
            project_id=project_id,
            run_id=run_id,
            agent_name="risk",
            content=findings["risk"].summary,
            provenance=ProvenanceType.AI_INFERENCE,
            evidence_source_ids=[c.source_id for c in findings["risk"].evidence_citations],
            confidence=findings["risk"].confidence.value,
        )
    )
    memory.log_audit_event(
        run_id=run_id,
        company_id=company_id,
        event_type="AGENT_EVALUATED",
        details={
            "agent": "risk",
            "confidence": findings["risk"].confidence.value,
            "risks_count": len(findings["risk"].risks),
            "latency_ms": risk_lat,
        },
    )

    # 3. Final Decision Synthesis & Controlled Branching
    memory.log_audit_event(
        run_id=run_id, company_id=company_id,
        event_type="AGENT_START",
        details={"agent": "decision", "model": settings.model_decision},
    )
    decision_agent = BusinessDecisionAgent()
    decision_result = decision_agent.evaluate(case, findings)

    # Track actual model used (from LLM call result or known fallback)
    if decision_result.model_used:
        models_invoked.append(decision_result.model_used)

    # 4. Finalize Run Record
    now_iso = datetime.now(timezone.utc).isoformat()
    run_record.status = "SUCCESS"
    run_record.completed_at = now_iso
    run_record.outcome = decision_result.outcome.value
    run_record.confidence = decision_result.confidence.value
    run_record.models_invoked = list(set(models_invoked))
    run_record.decision_result = json_safe(decision_result.model_dump())
    memory.save_run(run_record)

    memory.log_audit_event(
        run_id=run_id,
        company_id=company_id,
        event_type="DECISION_BRANCH",
        details={
            "outcome": decision_result.outcome.value,
            "confidence": decision_result.confidence.value,
            "model_used": decision_result.model_used,
            "llm_used": decision_result.llm_used,
            "phases_count": len(decision_result.execution_phases) if decision_result.execution_phases else 0,
            "critic_present": decision_result.critic_rejection_rationale is not None,
            "missing_evidence_count": len(decision_result.missing_evidence_checklist) if decision_result.missing_evidence_checklist else 0,
        },
    )

    # 5. Build Comprehensive Output
    all_evidence = company_evidence + web_evidence
    payload: Dict[str, Any] = {
        "run_id": run_id,
        "company_id": company_id,
        "project_id": project_id,
        "generated_at": now_iso,
        "decision_result": decision_result.model_dump(),
        "outcome": decision_result.outcome.value,
        "confidence": decision_result.confidence.value,
        "justification": decision_result.justification,
        "conditions": decision_result.conditions,
        "evidence_gaps": decision_result.evidence_gaps,
        "execution_phases": [p.model_dump() for p in decision_result.execution_phases] if decision_result.execution_phases else None,
        "critic_rejection_rationale": decision_result.critic_rejection_rationale,
        "missing_evidence_checklist": decision_result.missing_evidence_checklist,
        "agent_findings": {k: v.model_dump() for k, v in findings.items()},
        "all_evidence": [c.model_dump() for c in all_evidence],
        # Backward compatibility aliases for existing frontend components:
        "target_state": case.target_market_or_state or "General Market",
        "decision_question": case.proposal,
        "data_agent": {
            "success": True,
            "market_summary": findings["sales"].summary,
            "budget_limit": case.budget_limit or 0.0,
            "currency": case.currency,
            "financial_summary": findings["finance"].summary,
        },
        "research_agent": {
            "query": case.proposal,
            "result_count": len(all_evidence),
            "results": [c.model_dump() for c in all_evidence],
        },
        "risk_agent": {
            "risks": [r.model_dump() for r in findings["risk"].risks],
            "risk_count": len(findings["risk"].risks),
        },
        "critic_agent": {
            "findings": decision_result.critic_rejection_rationale.get("fatal_blockers", []) if decision_result.critic_rejection_rationale else [],
            "rejection_summary": decision_result.critic_rejection_rationale.get("rejection_summary", "") if decision_result.critic_rejection_rationale else "No fatal blockers identified.",
        },
        "planner_agent": {
            "plans": [p.model_dump() for p in decision_result.execution_phases] if decision_result.execution_phases else [],
        },
        "final_decision_agent": {
            "recommendation": decision_result.outcome.value,
            "confidence": decision_result.confidence.value,
            "confidence_reason": decision_result.confidence_reason,
            "justification": decision_result.justification,
            "evidence_gaps": decision_result.evidence_gaps,
            "conditions_before_expansion": decision_result.conditions,
            "decision_note": decision_result.decision_note,
        },
    }

    if save_report:
        try:
            settings.reports_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = settings.reports_dir / f"decisionroom_run_{run_id[:8]}_{stamp}.json"
            report_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            payload["_report_path"] = str(report_file)
        except OSError as exc:
            logger.error("Failed to save report: %s", exc)

    return json_safe(payload)


def run_pipeline(
    target_state: str,
    decision_question: str,
    save_report: bool = True,
    report_prefix: str = "decisionroom_report",
) -> Dict[str, Any]:
    """Execute the complete multi-agent workflow (legacy adapter).

    Preserves 100% backward compatibility with the frontend report schema.
    Also records the run in the MemoryStore for auditability.
    """
    state = target_state.strip()
    question = decision_question.strip()

    if not state or not question:
        raise ValueError("Both target_state and decision_question are required.")

    # Lazy imports of agents to ensure fast and resilient module startup
    from agents.critic_agent import critique_decision_evidence
    from agents.data_agent import analyze_market_entry
    from agents.decision_agent import generate_final_decision
    from agents.planner_agent import create_market_entry_plans
    from agents.research_agent import search_policy_evidence
    from agents.risk_agent import analyze_market_entry_risks
    from agents.tanseed_verification_agent import verify_tanseed_sources

    # Stage 1: Data & Quantitative Context
    try:
        data_report = analyze_market_entry(state)
    except Exception as exc:
        logger.warning("Data agent failed for state %s: %s", state, exc)
        data_report = {"success": False, "error": str(exc), "target_state": state}

    # Stage 2: Qualitative Research & Policy RAG
    research_query = (
        f"{question} What startup policies, incentives, eligibility conditions, "
        f"and market-entry support are documented for {state}?"
    )
    try:
        research_report = search_policy_evidence(research_query, top_k=5)
    except Exception as exc:
        logger.warning("Research agent failed: %s", exc)
        research_report = {
            "query": research_query,
            "target_state": state,
            "result_count": 0,
            "results": [],
            "error": str(exc),
            "note": "RAG search unavailable; falling back to heuristic evaluation.",
        }

    # Stage 2B: Official Source Verification (Conditional)
    funding_mode = _is_funding_question(question)
    official_verification = None
    if funding_mode:
        try:
            official_verification = verify_tanseed_sources()
            research_report["official_verification"] = official_verification
        except Exception as exc:
            logger.warning("Official verification failed: %s", exc)
            official_verification = {
                "status": "UNAVAILABLE",
                "error": str(exc),
                "sources_reachable": 0,
                "sources_total": 0,
            }

    # Stage 3: Risk Analysis
    try:
        risk_report = analyze_market_entry_risks(state, data_report, research_report)
    except Exception as exc:
        logger.warning("Risk agent failed: %s", exc)
        risk_report = {"target_state": state, "risks": [], "risk_count": 0, "error": str(exc)}

    # Stage 4: Evidence Critique
    try:
        critique_report = critique_decision_evidence(state, data_report, research_report, risk_report)
    except Exception as exc:
        logger.warning("Critic agent failed: %s", exc)
        critique_report = {"target_state": state, "findings": [], "finding_count": 0, "error": str(exc)}

    # Stage 5: Scenario Planning
    try:
        planner_report = create_market_entry_plans(
            state, data_report, research_report, risk_report, critique_report, decision_question=question
        )
    except Exception as exc:
        logger.warning("Planner agent failed: %s", exc)
        planner_report = {"target_state": state, "plans": [], "error": str(exc)}

    # Stage 6: Final Decision Synthesis
    try:
        final_report = generate_final_decision(
            state, question, data_report, research_report, risk_report, critique_report, planner_report
        )
    except Exception as exc:
        logger.warning("Decision agent failed: %s", exc)
        final_report = {
            "target_state": state,
            "decision_question": question,
            "recommendation": "DECISION ENGINE ERROR",
            "preferred_option": "Option 3: Delay Entry",
            "confidence": "Low",
            "confidence_reason": f"Decision synthesis error: {exc}",
            "justification": "Analysis could not be safely finalized.",
            "evidence_gaps": ["Rerun analysis when services are restored."],
            "conditions_before_expansion": ["Resolve system error."],
            "decision_note": "Preliminary error response.",
            "llm_used": False,
        }

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_id = str(uuid.uuid4())
    payload = {
        "run_id": run_id,
        "target_state": state,
        "decision_question": question,
        "generated_at": generated_at,
        "data_agent": data_report,
        "research_agent": research_report,
        "official_verification": official_verification,
        "risk_agent": risk_report,
        "critic_agent": critique_report,
        "planner_agent": planner_report,
        "final_decision_agent": final_report,
        # Normalized branch outcome:
        "outcome": final_report.get("recommendation", "HOLD_FOR_EVIDENCE"),
        "confidence": final_report.get("confidence", "Medium"),
    }

    # Record in MemoryStore for auditability
    try:
        mem = MemoryStore()
        mem.save_run(
            RunRecord(
                run_id=run_id,
                company_id="legacy",
                proposal=question,
                status="SUCCESS",
                outcome=final_report.get("recommendation"),
                confidence=final_report.get("confidence"),
                decision_result=json_safe(final_report),
            )
        )
    except Exception as exc:
        logger.debug("Memory record skipped for legacy pipeline: %s", exc)

    # Persist report if requested
    if save_report:
        try:
            settings.reports_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = settings.reports_dir / f"{report_prefix}_{stamp}.json"
            report_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            payload["_report_path"] = str(report_file)
        except OSError as exc:
            logger.error("Failed to save report: %s", exc)

    return json_safe(payload)
