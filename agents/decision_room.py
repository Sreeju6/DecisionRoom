"""Business Decision Agent and Controlled Branching Engine for DecisionRoom.

Enforces target workflow:
- BusinessDecisionAgent: Reconciles specialist evidence via LLM. Returns PROCEED,
  DO_NOT_PROCEED, or HOLD_FOR_EVIDENCE. LLM errors and malformed outputs NEVER default to PROCEED.
- PlanningAgent: Generates case-specific execution phases ONLY when outcome is PROCEED.
  Uses LLM with proposal context; does not invent precision.
- CriticAgent: Generates rejection rationale ONLY when outcome is DO_NOT_PROCEED.
  Uses LLM grounded in actual specialist findings.

Guardrails (deterministic):
- Critical blockers found → DO_NOT_PROCEED (LLM cannot override this)
- No citations and ≥3 missing info items → HOLD_FOR_EVIDENCE (LLM cannot override)
- LLM error/malformed output on decision → HOLD_FOR_EVIDENCE (never PROCEED silently)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from config.config import settings
from schemas.decision import (
    AgentFinding,
    BusinessCase,
    ConfidenceLevel,
    CostType,
    DecisionResult,
    EvidenceCitation,
    ExecutionPhase,
    OutcomeType,
)
from tools.llm_client import LLMClient, LLMError, ProviderNotConfiguredError

logger = logging.getLogger("decisionroom.decision_room")


# ── Structured output schemas ────────────────────────────────────────────────

class DecisionAssessment(BaseModel):
    """LLM-generated multi-criteria decision assessment."""
    outcome: str = Field(..., description="One of: PROCEED, DO_NOT_PROCEED, HOLD_FOR_EVIDENCE")
    confidence: str = Field(default="LOW", description="LOW, MEDIUM, or HIGH")
    confidence_reason: str = Field(..., description="Evidence-backed justification for confidence.")
    justification: str = Field(..., description="Comprehensive rationale citing specialist findings.")
    evidence_gaps: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list, description="Prerequisites before execution.")
    decision_note: str = Field(default="", description="Limitations and disclaimers.")


class PlanPhase(BaseModel):
    """LLM-generated execution phase."""
    phase_number: int = Field(..., ge=1)
    title: str
    objective: str
    tasks: List[str] = Field(default_factory=list)
    owner_role: str
    dependencies: List[int] = Field(default_factory=list)
    duration_estimate: str
    cost_estimate: Optional[float] = None
    cost_type: str = Field(default="inferred", description="sourced, calculated, inferred, or illustrative")
    deliverables: List[str] = Field(default_factory=list)
    kpis: List[str] = Field(default_factory=list)
    acceptance_gate: str


class PlanOutput(BaseModel):
    phases: List[PlanPhase] = Field(default_factory=list)


class CritiqueOutput(BaseModel):
    rejection_summary: str
    fatal_blockers: List[str] = Field(default_factory=list)
    remediable_weaknesses: List[str] = Field(default_factory=list)
    opportunity_costs: str = ""
    strategic_alternatives: List[str] = Field(default_factory=list)
    conditions_for_reconsideration: List[str] = Field(default_factory=list)


# ── PlanningAgent ─────────────────────────────────────────────────────────────

class PlanningAgent:
    """Generates a phased, case-specific execution plan on PROCEED via LLM."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def generate_plan(
        self,
        case: BusinessCase,
        findings: Dict[str, AgentFinding],
    ) -> List[ExecutionPhase]:
        """Generate phased execution plan. Falls back to template if LLM unavailable."""
        findings_summary = "\n".join(
            f"[{name.upper()}]: {f.summary}" for name, f in findings.items()
        )
        budget_str = f"Budget limit: {case.budget_limit}" if case.budget_limit else "Budget: not specified (use null for estimates)"

        system_prompt = (
            "You are the Planning Agent in DecisionRoom. The decision is PROCEED. "
            "Generate a case-specific phased execution plan based on the proposal and specialist findings. "
            "Each phase MUST be specific to this case — do not use generic placeholder phases. "
            "Use null for cost_estimate when no figure is supported by evidence. "
            "Use 'inferred' or 'illustrative' for cost_type when figures are estimated, not sourced. "
            "duration_estimate should be realistic (e.g. 'Weeks 1-6') not precise days without basis."
        )
        user_prompt = (
            f"PROPOSAL: {case.proposal}\n"
            f"OBJECTIVE: {case.objective or 'Not specified'}\n"
            f"TARGET MARKET: {case.target_market_or_state or 'Not specified'}\n"
            f"CONSTRAINTS: {'; '.join(case.constraints) if case.constraints else 'None'}\n"
            f"{budget_str}\n\n"
            f"SPECIALIST FINDINGS:\n{findings_summary}\n\n"
            "Generate 3-4 sequential execution phases for this specific proposal."
        )

        try:
            plan_out: PlanOutput = self.llm_client.generate_structured(
                prompt=user_prompt,
                response_model=PlanOutput,
                system_prompt=system_prompt,
                model=settings.model_planner,
                temperature=0.15,
            )
            phases = []
            for p in plan_out.phases[:4]:
                cost_type_map = {
                    "sourced": CostType.SOURCED,
                    "calculated": CostType.CALCULATED,
                    "inferred": CostType.INFERRED,
                    "illustrative": CostType.ILLUSTRATIVE,
                }
                ct = cost_type_map.get(p.cost_type.lower(), CostType.INFERRED)
                phases.append(ExecutionPhase(
                    phase_number=p.phase_number,
                    title=p.title,
                    objective=p.objective,
                    tasks=p.tasks or ["Define specific tasks during phase planning."],
                    owner_role=p.owner_role,
                    dependencies=p.dependencies,
                    duration_estimate=p.duration_estimate,
                    cost_estimate=p.cost_estimate,  # null when not evidence-backed
                    cost_type=ct,
                    deliverables=p.deliverables or ["Phase deliverables to be defined."],
                    kpis=p.kpis or ["KPIs to be defined per phase."],
                    acceptance_gate=p.acceptance_gate,
                ))
            if phases:
                logger.info("PlanningAgent generated %d LLM-based phases", len(phases))
                return phases
        except (ProviderNotConfiguredError, LLMError) as exc:
            logger.warning("PlanningAgent LLM call failed, using template fallback: %s", exc)

        # Template fallback — clearly labelled as such, no invented figures
        budget = case.budget_limit
        return self._template_phases(case, budget)

    def _template_phases(
        self,
        case: BusinessCase,
        budget: Optional[float],
    ) -> List[ExecutionPhase]:
        """Conservative template with null costs when budget is unknown."""
        b = budget  # may be None
        p1_cost = round(b * 0.25, 2) if b else None
        p2_cost = round(b * 0.45, 2) if b else None
        p3_cost = round(b * 0.30, 2) if b else None

        return [
            ExecutionPhase(
                phase_number=1,
                title="Phase 1: Validation & Regulatory Clearance",
                objective=f"Validate customer demand and complete regulatory review for: {case.proposal[:80]}",
                tasks=[
                    "Secure initial customer pilot agreements",
                    "Complete statutory regulatory review",
                    "Define technical architecture and budget",
                ],
                owner_role="VP Business Development & Legal Counsel",
                dependencies=[],
                duration_estimate="Weeks 1-6",
                cost_estimate=p1_cost,
                cost_type=CostType.ILLUSTRATIVE if p1_cost else CostType.INFERRED,
                deliverables=["Pilot agreements", "Compliance review", "Architecture doc"],
                kpis=["Regulatory blockers resolved", "Pilot customer commitments secured"],
                acceptance_gate="Gate 1: All regulatory filings approved and pilot commitments received.",
            ),
            ExecutionPhase(
                phase_number=2,
                title="Phase 2: MVP Build & Integration Testing",
                objective="Deploy core solution and test with initial customers.",
                tasks=[
                    "Build core workflow and integrations",
                    "Execute security and stress testing",
                    "Onboard first pilot users and measure feedback",
                ],
                owner_role="Engineering Lead & Product Manager",
                dependencies=[1],
                duration_estimate="Weeks 7-16",
                cost_estimate=p2_cost,
                cost_type=CostType.ILLUSTRATIVE if p2_cost else CostType.INFERRED,
                deliverables=["Production MVP", "Security audit", "Pilot metrics report"],
                kpis=["Pilot retention ≥ 80%", "Zero critical security findings"],
                acceptance_gate="Gate 2: Security test passed and pilot retention confirmed.",
            ),
            ExecutionPhase(
                phase_number=3,
                title="Phase 3: Commercial Launch",
                objective="Transition pilots to paid tiers and scale acquisition.",
                tasks=[
                    "Convert pilot customers to paid contracts",
                    "Launch commercial sales campaign",
                    "Scale infrastructure per verified unit economics",
                ],
                owner_role="Head of Sales & CRO",
                dependencies=[1, 2],
                duration_estimate="Weeks 17-26",
                cost_estimate=p3_cost,
                cost_type=CostType.ILLUSTRATIVE if p3_cost else CostType.INFERRED,
                deliverables=["Commercial contracts", "GTM metrics dashboard"],
                kpis=["Positive cash contribution margin", "LTV:CAC ≥ 3.0"],
                acceptance_gate="Gate 3: Unit economics verified healthy and positive contribution margin.",
            ),
        ]


# ── CriticAgent ───────────────────────────────────────────────────────────────

class CriticAgent:
    """Analyzes failure modes, assumption breakdowns, and alternatives on DO_NOT_PROCEED."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()

    def generate_critique(
        self,
        case: BusinessCase,
        findings: Dict[str, AgentFinding],
    ) -> Dict[str, Any]:
        """Generate case-specific rejection rationale grounded in specialist findings."""
        findings_summary = "\n".join(
            f"[{name.upper()}]: {f.summary}\nRisks: {[r.description for r in f.risks]}"
            for name, f in findings.items()
        )
        system_prompt = (
            "You are the Critic Agent in DecisionRoom. The decision is DO_NOT_PROCEED. "
            "Your task is to provide a case-specific, evidence-grounded rejection rationale. "
            "Each fatal blocker must cite the specialist finding that supports it. "
            "Strategic alternatives must be specific to this proposal — not generic."
        )
        user_prompt = (
            f"PROPOSAL: {case.proposal}\n"
            f"TARGET MARKET: {case.target_market_or_state or 'Not specified'}\n\n"
            f"SPECIALIST FINDINGS:\n{findings_summary}\n\n"
            "Generate a structured rejection rationale with fatal blockers, remediable weaknesses, "
            "strategic alternatives, and conditions for reconsideration."
        )

        try:
            critique: CritiqueOutput = self.llm_client.generate_structured(
                prompt=user_prompt,
                response_model=CritiqueOutput,
                system_prompt=system_prompt,
                model=settings.model_critic,
                temperature=0.10,
            )
            return critique.model_dump()
        except (ProviderNotConfiguredError, LLMError) as exc:
            logger.warning("CriticAgent LLM call failed, using rule-based fallback: %s", exc)

        # Rule-based fallback
        fatal_blockers: List[str] = []
        remediable_issues: List[str] = []
        for agent_name, finding in findings.items():
            for risk in finding.risks:
                if risk.severity.lower() == "critical":
                    fatal_blockers.append(f"{agent_name}: {risk.description}")
                elif risk.severity.lower() == "high":
                    remediable_issues.append(f"{agent_name}: {risk.description}")

        return {
            "rejection_summary": "Proposal does not meet minimum risk and viability thresholds. (LLM unavailable; rule-based fallback.)",
            "fatal_blockers": fatal_blockers or ["Severe regulatory or financial non-viability identified."],
            "remediable_weaknesses": remediable_issues,
            "opportunity_costs": "Capital allocation risks stranding resources without verified return.",
            "strategic_alternatives": [
                f"Run a restricted local pilot for '{case.proposal[:60]}' before full launch.",
                "Pivot to a less regulated customer segment to reduce compliance burden.",
                "Re-negotiate unit cost terms to achieve positive margins prior to launch.",
            ],
            "conditions_for_reconsideration": [
                "Resolve all critical statutory compliance obligations with formal counsel.",
                "Demonstrate verifiable customer pre-commitments with positive unit margins.",
            ],
        }


# ── BusinessDecisionAgent ─────────────────────────────────────────────────────

class BusinessDecisionAgent:
    """Multi-criteria decision agent synthesizing evidence via LLM and enforcing branch outcomes.

    Guardrail invariants (deterministic, not overridable by LLM):
    - Critical blockers detected → DO_NOT_PROCEED
    - No evidence + ≥3 missing items → HOLD_FOR_EVIDENCE
    - LLM error or malformed output → HOLD_FOR_EVIDENCE (never PROCEED)
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
        self.planner = PlanningAgent(llm_client=self.llm_client)
        self.critic = CriticAgent(llm_client=self.llm_client)

    def evaluate(
        self,
        case: BusinessCase,
        specialist_findings: Dict[str, AgentFinding],
    ) -> DecisionResult:
        """Evaluate specialist evidence via LLM and return validated DecisionResult."""
        all_citations: List[EvidenceCitation] = []
        all_missing_info: List[str] = []
        all_risks = []
        critical_risks = []

        for agent_name, finding in specialist_findings.items():
            all_citations.extend(finding.evidence_citations)
            all_missing_info.extend(finding.missing_information)
            for r in finding.risks:
                all_risks.append(r)
                if r.severity.lower() == "critical":
                    critical_risks.append((agent_name, r))

        # ── Guardrail 1: Critical blockers → DO_NOT_PROCEED (deterministic) ──
        if len(critical_risks) >= 1:
            outcome = OutcomeType.DO_NOT_PROCEED
            conf = ConfidenceLevel.HIGH
            conf_reason = f"Identified {len(critical_risks)} critical blocker(s) across specialist domains."
            justification = (
                "The business proposal cannot proceed due to critical blockers: "
                + "; ".join([f"{a}: {r.description}" for a, r in critical_risks])
            )
            rejection_data = self.critic.generate_critique(case, specialist_findings)
            # Ensure deterministic critical blockers are always explicitly included in fatal_blockers
            det_blockers = [f"{a}: {r.description}" for a, r in critical_risks]
            existing_fb = rejection_data.get("fatal_blockers", [])
            for db in det_blockers:
                if not any(db.lower() in b.lower() for b in existing_fb):
                    existing_fb.insert(0, db)
            rejection_data["fatal_blockers"] = existing_fb

            return DecisionResult(
                outcome=outcome,
                confidence=conf,
                confidence_reason=conf_reason,
                justification=justification,
                evidence_gaps=list(set(all_missing_info)),
                conditions=["Address fatal blockers before requesting re-evaluation."],
                decision_note="Rejection rationale generated per DO_NOT_PROCEED guardrail.",
                agent_findings=specialist_findings,
                execution_phases=None,
                critic_rejection_rationale=rejection_data,
                missing_evidence_checklist=None,
                guardrails_applied=["Critical Blocker Protection Guardrail"],
            )

        # ── Guardrail 2: Insufficient evidence → HOLD (deterministic) ──
        if len(all_citations) == 0 or len(all_missing_info) >= 3:
            outcome = OutcomeType.HOLD_FOR_EVIDENCE
            conf = ConfidenceLevel.LOW
            conf_reason = f"Crucial evidence is missing ({len(all_missing_info)} item(s) unverified)."
            justification = (
                "The proposal cannot be responsibly approved or rejected without empirical evidence. "
                "Decision is held pending required documentation."
            )
            checklist = list(set(all_missing_info))[:8]
            return DecisionResult(
                outcome=outcome,
                confidence=conf,
                confidence_reason=conf_reason,
                justification=justification,
                evidence_gaps=checklist,
                conditions=["Supply requested documentation to re-activate decision evaluation."],
                decision_note="Hold for evidence. Neither execution plan nor rejection report is created.",
                agent_findings=specialist_findings,
                execution_phases=None,
                critic_rejection_rationale=None,
                missing_evidence_checklist=checklist,
                guardrails_applied=["Evidence Sufficiency Guardrail"],
            )

        # ── LLM-driven decision synthesis ─────────────────────────────────────
        findings_summary = "\n".join(
            f"[{name.upper()}] ({f.confidence.value} confidence): {f.summary}"
            for name, f in specialist_findings.items()
        )
        system_prompt = (
            "You are the Business Decision Agent in DecisionRoom. "
            "Evaluate whether the proposal should PROCEED, be rejected (DO_NOT_PROCEED), "
            "or be held for more evidence (HOLD_FOR_EVIDENCE). "
            "Criteria to weigh: strategic fit, evidence quality, demand validation, "
            "financial viability, legal feasibility, technical feasibility, risks, alternatives, and uncertainties. "
            "GUARDRAIL: Missing critical evidence MUST result in HOLD_FOR_EVIDENCE. "
            "Model errors or ambiguous evidence must NOT default to PROCEED. "
            "Only output PROCEED when evidence genuinely supports it."
        )
        user_prompt = (
            f"PROPOSAL: {case.proposal}\n"
            f"OBJECTIVE: {case.objective or 'Not specified'}\n"
            f"TARGET MARKET: {case.target_market_or_state or 'Not specified'}\n"
            f"CONSTRAINTS: {'; '.join(case.constraints) if case.constraints else 'None'}\n\n"
            f"SPECIALIST FINDINGS ({len(all_citations)} total citations, "
            f"{len(all_risks)} risks, {len(all_missing_info)} open items):\n"
            f"{findings_summary}\n\n"
            "Provide a multi-criteria decision assessment."
        )

        assessment: Optional[DecisionAssessment] = None
        try:
            assessment = self.llm_client.generate_structured(
                prompt=user_prompt,
                response_model=DecisionAssessment,
                system_prompt=system_prompt,
                model=settings.model_decision,
                temperature=0.10,
            )
        except (ProviderNotConfiguredError, LLMError) as exc:
            logger.warning(
                "BusinessDecisionAgent LLM call failed; defaulting to HOLD_FOR_EVIDENCE: %s", exc
            )
            # Guardrail: LLM failure NEVER produces PROCEED
            return DecisionResult(
                outcome=OutcomeType.HOLD_FOR_EVIDENCE,
                confidence=ConfidenceLevel.LOW,
                confidence_reason="LLM decision synthesis failed; holding for evidence to avoid unsupported outcome.",
                justification=f"Decision synthesis error: {type(exc).__name__}. Cannot generate a reliable recommendation without LLM evaluation.",
                evidence_gaps=list(set(all_missing_info)),
                conditions=["Restore LLM provider access and re-run analysis."],
                decision_note="HOLD_FOR_EVIDENCE triggered by LLM failure guardrail.",
                agent_findings=specialist_findings,
                execution_phases=None,
                critic_rejection_rationale=None,
                missing_evidence_checklist=list(set(all_missing_info))[:8],
                guardrails_applied=["LLM Failure Safety Guardrail"],
            )

        # Validate and normalize LLM outcome
        outcome_str = str(assessment.outcome).upper().strip()
        valid_outcomes = {"PROCEED", "DO_NOT_PROCEED", "HOLD_FOR_EVIDENCE"}
        if outcome_str not in valid_outcomes:
            logger.warning("LLM produced invalid outcome '%s'; defaulting to HOLD_FOR_EVIDENCE", outcome_str)
            outcome_str = "HOLD_FOR_EVIDENCE"
        outcome = OutcomeType(outcome_str)

        conf_str = str(assessment.confidence).upper().strip()
        conf_map = {"LOW": ConfidenceLevel.LOW, "MEDIUM": ConfidenceLevel.MEDIUM, "HIGH": ConfidenceLevel.HIGH}
        conf = conf_map.get(conf_str, ConfidenceLevel.LOW)

        # ── Branch: PROCEED ───────────────────────────────────────────────────
        if outcome == OutcomeType.PROCEED:
            phases = self.planner.generate_plan(case, specialist_findings)
            return DecisionResult(
                outcome=outcome,
                confidence=conf,
                confidence_reason=assessment.confidence_reason,
                justification=assessment.justification,
                evidence_gaps=assessment.evidence_gaps or list(set(all_missing_info)),
                conditions=assessment.conditions or ["Adhere to Phase acceptance gates."],
                decision_note=assessment.decision_note or "Proceed subject to Phase 1 gate.",
                agent_findings=specialist_findings,
                execution_phases=phases,
                critic_rejection_rationale=None,
                missing_evidence_checklist=None,
                guardrails_applied=["Phase Gate Governance Guardrail"],
                llm_used=True,
                model_used=settings.model_decision,
            )

        # ── Branch: DO_NOT_PROCEED ────────────────────────────────────────────
        if outcome == OutcomeType.DO_NOT_PROCEED:
            rejection_data = self.critic.generate_critique(case, specialist_findings)
            return DecisionResult(
                outcome=outcome,
                confidence=conf,
                confidence_reason=assessment.confidence_reason,
                justification=assessment.justification,
                evidence_gaps=assessment.evidence_gaps or list(set(all_missing_info)),
                conditions=assessment.conditions or ["Address fatal blockers before re-evaluation."],
                decision_note=assessment.decision_note or "Rejection rationale generated.",
                agent_findings=specialist_findings,
                execution_phases=None,
                critic_rejection_rationale=rejection_data,
                missing_evidence_checklist=None,
                guardrails_applied=["DO_NOT_PROCEED Branch Invariant"],
                llm_used=True,
                model_used=settings.model_decision,
            )

        # ── Branch: HOLD_FOR_EVIDENCE ─────────────────────────────────────────
        checklist = assessment.evidence_gaps or list(set(all_missing_info))[:8]
        return DecisionResult(
            outcome=OutcomeType.HOLD_FOR_EVIDENCE,
            confidence=conf,
            confidence_reason=assessment.confidence_reason,
            justification=assessment.justification,
            evidence_gaps=checklist,
            conditions=assessment.conditions or ["Supply requested evidence to resume evaluation."],
            decision_note=assessment.decision_note or "Hold pending evidence collection.",
            agent_findings=specialist_findings,
            execution_phases=None,
            critic_rejection_rationale=None,
            missing_evidence_checklist=checklist,
            guardrails_applied=["HOLD_FOR_EVIDENCE Branch Invariant"],
            llm_used=True,
            model_used=settings.model_decision,
        )
