"""Typed Pydantic schemas for DecisionRoom multi-agent system.

Defines schemas for BusinessCase, EvidenceCitation, AgentFinding,
Risk, DecisionResult, ExecutionPhase, and AnalysisRun.
Enforces the three target workflow outcomes:
- PROCEED
- DO_NOT_PROCEED
- HOLD_FOR_EVIDENCE
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class OutcomeType(str, Enum):
    """The three authoritative decision outcomes enforced by the workflow orchestrator."""
    PROCEED = "PROCEED"
    DO_NOT_PROCEED = "DO_NOT_PROCEED"
    HOLD_FOR_EVIDENCE = "HOLD_FOR_EVIDENCE"


class ConfidenceLevel(str, Enum):
    """Rubric-defined confidence levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CostType(str, Enum):
    """Provenance and certainty category for financial estimates."""
    SOURCED = "sourced"
    CALCULATED = "calculated"
    INFERRED = "inferred"
    ILLUSTRATIVE = "illustrative"


class BusinessCase(BaseModel):
    """Standardized intake representation of a business decision proposal."""
    proposal: str = Field(..., min_length=5, description="Core business proposal or question to evaluate.")
    objective: Optional[str] = Field(default=None, description="Primary business goal (e.g. revenue, expansion, compliance).")
    company_name: Optional[str] = Field(default=None, description="Name of company or business unit.")
    target_market_or_state: Optional[str] = Field(default=None, description="Geographic market, state, or jurisdiction.")
    constraints: List[str] = Field(default_factory=list, description="Budget, timeline, or policy constraints.")
    budget_limit: Optional[float] = Field(default=None, ge=0.0, description="Explicit monetary budget ceiling if applicable.")
    currency: Optional[str] = Field(default=None, description="Currency code for budget figures (e.g. USD, EUR, INR).")
    raw_question: str = Field(default="", description="Original verbatim user input string.")

    @classmethod
    def from_raw(cls, question: str, target_state: Optional[str] = None) -> BusinessCase:
        """Create a BusinessCase from raw text input."""
        return cls(
            proposal=question.strip(),
            target_market_or_state=target_state.strip() if target_state else None,
            raw_question=question.strip(),
        )


class EvidenceCitation(BaseModel):
    """Traceable, verifiable source grounding citation for factual claims."""
    source_id: str = Field(..., description="Unique deterministic identifier for the source chunk or document.")
    title: str = Field(..., description="Human-readable title or document name.")
    url: Optional[str] = Field(default=None, description="Origin URL if retrieved from the web or portal.")
    document: Optional[str] = Field(default=None, description="Filename or storage key.")
    page_or_section: Optional[str] = Field(default=None, description="Page number, spreadsheet sheet, or section heading.")
    snippet: str = Field(..., description="Direct verbatim excerpt or structured table snippet.")
    retrieval_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the citation was retrieved."
    )
    verified: bool = Field(default=False, description="Whether the citation provenance was validated against official sources.")


class Risk(BaseModel):
    """Identified operational, financial, legal, or market risk."""
    category: str = Field(..., description="Domain category (e.g. Market, Financial, Legal, Technical, Execution).")
    severity: str = Field(..., description="Severity rating: Critical, High, Medium, Low.")
    description: str = Field(..., description="Detailed description of the threat or failure mode.")
    mitigation: str = Field(..., description="Concrete, actionable mitigation action.")
    likelihood: Optional[str] = Field(default=None, description="Likelihood assessment: High, Medium, Low.")
    source_id: Optional[str] = Field(default=None, description="Optional supporting citation ID.")


class AgentFinding(BaseModel):
    """Validated structured output from a domain specialist agent."""
    agent_name: str = Field(..., description="Name of the specialist agent (e.g. Sales, Finance, Legal, Technical, Risk).")
    summary: str = Field(..., description="Executive summary of the agent's evaluation.")
    evidence_citations: List[EvidenceCitation] = Field(default_factory=list, description="Direct citations grounding the findings.")
    assumptions: List[str] = Field(default_factory=list, description="Explicit assumptions made in the absence of verified facts.")
    risks: List[Risk] = Field(default_factory=list, description="Domain-specific risks identified by this agent.")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.LOW, description="Confidence level based on evidence completeness.")
    confidence_rationale: str = Field(..., description="Justification for the assigned confidence level.")
    contradictions: List[str] = Field(default_factory=list, description="Contradictions between sources or claims.")
    missing_information: List[str] = Field(default_factory=list, description="Missing data needed to verify claims.")


class ExecutionPhase(BaseModel):
    """Sequential execution phase produced by the Planning Agent on PROCEED."""
    phase_number: int = Field(..., ge=1, description="Sequential phase order (1-indexed).")
    title: str = Field(..., description="Title of the phase.")
    objective: str = Field(..., description="Specific objective to achieve in this phase.")
    tasks: List[str] = Field(default_factory=list, description="Granular action items.")
    owner_role: str = Field(..., description="Responsible role (e.g. Tech Lead, Finance Director, Sales Ops).")
    dependencies: List[int] = Field(default_factory=list, description="Prior phase numbers that must complete first.")
    duration_estimate: str = Field(..., description="Estimated timeline (e.g. 'Weeks 1-4', '3 months').")
    cost_estimate: Optional[float] = Field(default=None, ge=0.0, description="Estimated monetary budget for this phase.")
    cost_type: CostType = Field(default=CostType.INFERRED, description="Provenance type of the financial estimate.")
    deliverables: List[str] = Field(default_factory=list, description="Tangible deliverable outputs.")
    kpis: List[str] = Field(default_factory=list, description="Key performance indicators or milestone gates.")
    acceptance_gate: str = Field(..., description="Go/no-go criteria required to advance to the next phase.")


class DecisionResult(BaseModel):
    """Complete, reconciled decision synthesis from the Business Decision Agent."""
    outcome: OutcomeType = Field(..., description="Authoritative workflow outcome: PROCEED, DO_NOT_PROCEED, or HOLD_FOR_EVIDENCE.")
    confidence: ConfidenceLevel = Field(..., description="Overall confidence level.")
    confidence_reason: str = Field(..., description="Evidence-backed reasoning for confidence rating.")
    justification: str = Field(..., description="Comprehensive decision rationale synthesizing all specialist evidence.")
    evidence_gaps: List[str] = Field(default_factory=list, description="Critical missing evidence items.")
    conditions: List[str] = Field(default_factory=list, description="Prerequisite conditions before executing action.")
    decision_note: str = Field(..., description="Boundary constraints, limitations, and verification disclaimers.")
    agent_findings: Dict[str, AgentFinding] = Field(default_factory=dict, description="Outputs from specialist agents keyed by agent name.")
    
    # Conditional branches:
    execution_phases: Optional[List[ExecutionPhase]] = Field(default=None, description="Populated on PROCEED outcome only.")
    critic_rejection_rationale: Optional[Dict[str, Any]] = Field(default=None, description="Populated on DO_NOT_PROCEED outcome only.")
    missing_evidence_checklist: Optional[List[str]] = Field(default=None, description="Populated on HOLD_FOR_EVIDENCE outcome.")
    
    # Traceability & Observability
    llm_used: bool = Field(default=False)
    model_used: Optional[str] = Field(default=None)
    guardrails_applied: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("execution_phases")
    @classmethod
    def validate_phases_only_on_proceed(cls, v: Optional[List[ExecutionPhase]], info: Any) -> Optional[List[ExecutionPhase]]:
        # Enforce target workflow rule: execution plan may only exist if outcome is PROCEED
        outcome = info.data.get("outcome")
        if outcome != OutcomeType.PROCEED and v:
            outcome_str = getattr(outcome, "value", str(outcome))
            raise ValueError(f"Execution phases cannot be attached when outcome is {outcome_str}. Allowed only on PROCEED.")
        if outcome == OutcomeType.PROCEED and not v:
            raise ValueError("PROCEED outcome must include execution_phases.")
        return v

    @field_validator("critic_rejection_rationale")
    @classmethod
    def validate_critic_only_on_do_not_proceed(cls, v: Optional[Dict[str, Any]], info: Any) -> Optional[Dict[str, Any]]:
        outcome = info.data.get("outcome")
        if outcome != OutcomeType.DO_NOT_PROCEED and v:
            outcome_str = getattr(outcome, "value", str(outcome))
            raise ValueError(f"Critic rejection rationale cannot be attached when outcome is {outcome_str}. Allowed only on DO_NOT_PROCEED.")
        return v


class AnalysisRun(BaseModel):
    """Audit and telemetry log entry for an analysis run."""
    run_id: str = Field(..., description="Unique UUID for this analysis execution.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)
    status: str = Field(default="IN_PROGRESS", description="IN_PROGRESS, SUCCESS, FAILED")
    business_case: BusinessCase
    decision_outcome: Optional[OutcomeType] = Field(default=None)
    models_invoked: List[str] = Field(default_factory=list)
    agent_latencies_ms: Dict[str, float] = Field(default_factory=dict)
    total_latency_ms: Optional[float] = Field(default=None)
    errors: List[str] = Field(default_factory=list)
