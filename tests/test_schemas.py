"""Tests for typed Pydantic schemas and workflow branch constraints."""
import pytest
from pydantic import ValidationError

from schemas import (
    OutcomeType,
    ConfidenceLevel,
    CostType,
    BusinessCase,
    EvidenceCitation,
    Risk,
    AgentFinding,
    ExecutionPhase,
    DecisionResult,
)


def test_outcome_types():
    assert OutcomeType.PROCEED.value == "PROCEED"
    assert OutcomeType.DO_NOT_PROCEED.value == "DO_NOT_PROCEED"
    assert OutcomeType.HOLD_FOR_EVIDENCE.value == "HOLD_FOR_EVIDENCE"


def test_business_case_creation():
    case = BusinessCase.from_raw("Should we expand into Germany?", target_state="EU")
    assert case.proposal == "Should we expand into Germany?"
    assert case.target_market_or_state == "EU"
    assert case.raw_question == "Should we expand into Germany?"


def test_evidence_citation():
    cite = EvidenceCitation(
        source_id="chunk_42",
        title="Tamil Nadu Startup Policy 2023",
        page_or_section="Page 20",
        snippet="TANSEED grant provides up to Rs 15 lakh.",
        verified=True,
    )
    assert cite.source_id == "chunk_42"
    assert cite.verified is True
    assert cite.retrieval_timestamp is not None


def test_agent_finding():
    finding = AgentFinding(
        agent_name="Sales",
        summary="High early demand detected.",
        confidence=ConfidenceLevel.MEDIUM,
        confidence_rationale="3 pilot LOIs received.",
    )
    assert finding.agent_name == "Sales"
    assert finding.confidence == ConfidenceLevel.MEDIUM
    assert finding.assumptions == []


def test_workflow_rule_phases_only_on_proceed():
    phase = ExecutionPhase(
        phase_number=1,
        title="Pilot Phase",
        objective="Run customer validation",
        tasks=["Sign 5 beta users"],
        owner_role="Product Lead",
        duration_estimate="4 weeks",
        acceptance_gate="5 active users",
        cost_type=CostType.CALCULATED,
    )

    # PROCEED allows execution phases
    proceed_res = DecisionResult(
        outcome=OutcomeType.PROCEED,
        confidence=ConfidenceLevel.HIGH,
        confidence_reason="Validated customer demand.",
        justification="Unit economics and market demand are favorable.",
        decision_note="Proceed subject to milestone gates.",
        execution_phases=[phase],
    )
    assert proceed_res.execution_phases is not None
    assert len(proceed_res.execution_phases) == 1

    # DO_NOT_PROCEED rejects execution phases
    with pytest.raises(ValidationError) as exc:
        DecisionResult(
            outcome=OutcomeType.DO_NOT_PROCEED,
            confidence=ConfidenceLevel.HIGH,
            confidence_reason="Severe legal blocker.",
            justification="Proposal violates local regulatory licensing.",
            decision_note="Rejection rationale documented.",
            execution_phases=[phase],
        )
    assert "Execution phases cannot be attached when outcome is DO_NOT_PROCEED" in str(exc.value)

    # HOLD_FOR_EVIDENCE rejects execution phases
    with pytest.raises(ValidationError) as exc:
        DecisionResult(
            outcome=OutcomeType.HOLD_FOR_EVIDENCE,
            confidence=ConfidenceLevel.LOW,
            confidence_reason="Missing financial statements.",
            justification="Cannot evaluate unit economics without cost structure.",
            decision_note="Hold until evidence is supplied.",
            execution_phases=[phase],
        )
    assert "Execution phases cannot be attached when outcome is HOLD_FOR_EVIDENCE" in str(exc.value)
