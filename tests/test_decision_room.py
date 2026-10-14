"""Unit tests for Phase 5 & 6: BusinessDecisionAgent, PlanningAgent, CriticAgent, and Controlled Branching."""
import pytest

from agents.decision_room import BusinessDecisionAgent, PlanningAgent, CriticAgent
from schemas.decision import (
    AgentFinding,
    BusinessCase,
    ConfidenceLevel,
    CostType,
    DecisionResult,
    EvidenceCitation,
    ExecutionPhase,
    OutcomeType,
    Risk,
)


def create_mock_finding(
    agent_name: str,
    summary: str = "Analysis passed",
    citations_count: int = 2,
    critical_risks: int = 0,
    missing_info_count: int = 0,
) -> AgentFinding:
    citations = [
        EvidenceCitation(
            source_id=f"{agent_name}_doc_{i}",
            title=f"{agent_name.capitalize()} Report {i}",
            document="report.pdf",
            snippet=f"Factual empirical finding {i} from {agent_name}.",
            verified=True,
        )
        for i in range(citations_count)
    ]
    risks = []
    if critical_risks > 0:
        for i in range(critical_risks):
            risks.append(
                Risk(
                    category="statutory",
                    description=f"Critical compliance defect {i}",
                    severity="critical",
                    mitigation="Must be resolved prior to launch.",
                )
            )
    else:
        risks.append(
            Risk(
                category="operational",
                description="Manageable latency risk",
                severity="low",
                mitigation="Use Redis caching",
            )
        )

    missing_info = [f"{agent_name} missing specification {i}" for i in range(missing_info_count)]

    return AgentFinding(
        agent_name=agent_name,
        summary=summary,
        confidence=ConfidenceLevel.HIGH if citations_count >= 2 else ConfidenceLevel.LOW,
        confidence_rationale="Empirical documentation verified",
        evidence_citations=citations,
        risks=risks,
        missing_information=missing_info,
    )


def test_outcome_proceed_generates_phases_and_no_rejection():
    agent = BusinessDecisionAgent()
    case = BusinessCase(
        proposal="Enterprise Expansion into European Union and DACH region",
        company_name="Acme Corp",
        target_market_or_state="European Union",
        budget_limit=200000.0,
    )

    findings = {
        "sales": create_mock_finding("sales", citations_count=2),
        "finance": create_mock_finding("finance", citations_count=2),
        "legal": create_mock_finding("legal", citations_count=2),
        "technical": create_mock_finding("technical", citations_count=2),
    }

    result = agent.evaluate(case, findings)

    assert result.outcome == OutcomeType.PROCEED
    assert result.execution_phases is not None
    assert len(result.execution_phases) in {3, 4}
    # Schema and workflow rule: critic rejection rationale must be None on PROCEED
    assert result.critic_rejection_rationale is None
    assert result.missing_evidence_checklist is None

    # Check phase structure
    phase1 = result.execution_phases[0]
    assert phase1.phase_number == 1
    assert phase1.cost_estimate is None or phase1.cost_estimate >= 0
    assert len(phase1.tasks) >= 2
    assert phase1.acceptance_gate != ""


def test_outcome_do_not_proceed_on_critical_risks():
    agent = BusinessDecisionAgent()
    case = BusinessCase(
        proposal="Launch Unlicensed Fintech Lending Service",
        company_name="Acme Corp",
        budget_limit=50000.0,
    )

    findings = {
        "sales": create_mock_finding("sales", citations_count=2),
        "finance": create_mock_finding("finance", citations_count=2),
        "legal": create_mock_finding("legal", citations_count=2, critical_risks=1),
        "technical": create_mock_finding("technical", citations_count=2),
    }

    result = agent.evaluate(case, findings)

    assert result.outcome == OutcomeType.DO_NOT_PROCEED
    assert result.execution_phases is None  # Rule: No execution plan on DO_NOT_PROCEED
    assert result.critic_rejection_rationale is not None
    assert result.missing_evidence_checklist is None

    rationale = result.critic_rejection_rationale
    assert "fatal_blockers" in rationale
    assert any("legal" in b.lower() for b in rationale["fatal_blockers"])
    assert "strategic_alternatives" in rationale
    assert len(rationale["strategic_alternatives"]) >= 1


def test_outcome_hold_for_evidence_when_citations_missing():
    agent = BusinessDecisionAgent()
    case = BusinessCase(
        proposal="Unverified Market Entry into new geography",
        company_name="Acme Corp",
    )

    # 0 citations provided
    findings = {
        "sales": create_mock_finding("sales", citations_count=0),
        "finance": create_mock_finding("finance", citations_count=0),
    }

    result = agent.evaluate(case, findings)

    assert result.outcome == OutcomeType.HOLD_FOR_EVIDENCE
    assert result.confidence == ConfidenceLevel.LOW
    assert result.execution_phases is None  # Rule: No plan on HOLD
    assert result.critic_rejection_rationale is None  # Rule: No rejection critique on HOLD
    assert result.missing_evidence_checklist is not None


def test_outcome_hold_for_evidence_when_missing_info_high():
    agent = BusinessDecisionAgent()
    case = BusinessCase(
        proposal="Partially Grounded Expansion with insufficient data",
        company_name="Acme Corp",
    )

    # Citations exist but high data gaps (>= 3 items missing)
    findings = {
        "sales": create_mock_finding("sales", citations_count=1, missing_info_count=2),
        "legal": create_mock_finding("legal", citations_count=1, missing_info_count=2),
    }

    result = agent.evaluate(case, findings)

    assert result.outcome == OutcomeType.HOLD_FOR_EVIDENCE
    assert result.execution_phases is None
    assert result.critic_rejection_rationale is None
    assert len(result.missing_evidence_checklist) >= 3


def test_schema_level_rejection_of_invalid_branch_state():
    """Verify that Pydantic validator rejects PROCEED outcome if execution_phases is missing or critic is present."""
    findings = {"sales": create_mock_finding("sales")}

    # Attempting PROCEED without execution_phases must raise ValueError
    with pytest.raises(ValueError, match="PROCEED outcome must include execution_phases"):
        DecisionResult(
            outcome=OutcomeType.PROCEED,
            confidence=ConfidenceLevel.HIGH,
            confidence_reason="Valid",
            justification="Approved",
            decision_note="Valid note",
            agent_findings=findings,
            execution_phases=None,  # Invalid for PROCEED!
        )

    # Attempting DO_NOT_PROCEED with execution_phases must raise ValueError
    with pytest.raises(ValueError, match="Execution phases cannot be attached when outcome is DO_NOT_PROCEED"):
        DecisionResult(
            outcome=OutcomeType.DO_NOT_PROCEED,
            confidence=ConfidenceLevel.HIGH,
            confidence_reason="Blocked",
            justification="Blocked",
            decision_note="Valid note",
            agent_findings=findings,
            critic_rejection_rationale={"fatal_blockers": ["Severe failure"]},
            execution_phases=[
                ExecutionPhase(
                    phase_number=1,
                    title="Phase 1",
                    objective="Obj",
                    tasks=["Task 1"],
                    owner_role="Lead",
                    duration_estimate="1w",
                    cost_estimate=100.0,
                    cost_type=CostType.INFERRED,
                    deliverables=["Doc"],
                    kpis=["KPI"],
                    acceptance_gate="Gate 1",
                )
            ],
        )
