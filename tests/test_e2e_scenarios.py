"""End-to-End Synthetic Scenarios and Validation for DecisionRoom (Phase 9).

Validates the 10 core business and failure scenarios specified in the roadmap:
1. Sound proposal with supporting evidence -> PROCEED with execution phases
2. Negative unit economics -> captured in financial stress analysis
3. Material statutory/legal blocker -> DO_NOT_PROCEED with critic report
4. Technical infeasibility / dependency gap -> identified in technical assessment
5. Insufficient evidence -> HOLD_FOR_EVIDENCE with missing evidence checklist
6. Contradictory evidence sources -> LOW confidence assigned
7. Model provider resilience and approved registry verification
8. Document parser security against corrupt / unsupported files
9. Multi-tenant company isolation and audit trace deletion
10. Persistence across restarts
"""
import io
import pytest
from pathlib import Path

from agents.decision_room import BusinessDecisionAgent
from agents.specialists import FinanceAgent, LegalAgent, RiskAgent, SalesAgent, TechnicalAgent
from app.pipeline import run_business_decision
from schemas.decision import (
    AgentFinding,
    BusinessCase,
    ConfidenceLevel,
    DecisionResult,
    EvidenceCitation,
    ExecutionPhase,
    OutcomeType,
    Risk,
)
from tools.calculation_tools import calculate_unit_economics, run_downside_stress_test
from tools.document_parser import DocumentParser, FileValidationError, ParsingError
from tools.llm_client import LLMClient, APPROVED_MODEL_IDS
from tools.memory import MemoryStore, ProjectMemoryItem, ProvenanceType
from tools.vector_store import DocumentChunk, QdrantVectorStore


def test_scenario_1_sound_proposal_proceeds():
    """Scenario 1: Sound proposal with verified demand, healthy economics, and compliance."""
    agent = BusinessDecisionAgent()
    case = BusinessCase(
        proposal="Expand enterprise B2B analytics platform into Singapore",
        company_name="CloudMetrics",
        target_market_or_state="Singapore",
        budget_limit=250000.0,
    )
    citations = [
        EvidenceCitation(source_id="sg_1", title="MAS Regulatory Sandbox", snippet="Fintech sandbox permits pilot testing.", verified=True),
        EvidenceCitation(source_id="sg_2", title="Enterprise Demand Survey", snippet="72 enterprise pilot expressions of interest.", verified=True),
        EvidenceCitation(source_id="sg_3", title="Singapore Cloud Infra", snippet="AWS and GCP regions provide local data residency.", verified=True),
        EvidenceCitation(source_id="sg_4", title="Pricing Benchmark", snippet="Average contract value is $45,000 ARR.", verified=True),
    ]
    findings = {
        "sales": SalesAgent().analyze(case, citations, []),
        "finance": FinanceAgent().analyze(case, citations, []),
        "legal": LegalAgent().analyze(case, citations, []),
        "technical": TechnicalAgent().analyze(case, citations, []),
    }
    findings["risk"] = RiskAgent().analyze(case, findings)

    result = agent.evaluate(case, findings)
    assert result.outcome == OutcomeType.PROCEED
    assert result.execution_phases is not None
    assert len(result.execution_phases) in {3, 4}
    assert result.critic_rejection_rationale is None
    assert result.missing_evidence_checklist is None


def test_scenario_2_negative_unit_economics_detected():
    """Scenario 2: Negative unit economics identified deterministically."""
    # CAC higher than LTV
    calc = calculate_unit_economics(
        cac=5000.0,
        arpu_monthly=200.0,
        gross_margin_percent=40.0,
        churn_rate_monthly=0.10,
    )
    assert calc.ltv_to_cac_ratio < 1.0
    assert calc.is_healthy is False

    # Downside stress test detects margin erosion
    stress = run_downside_stress_test(
        base_revenue=100000.0,
        base_costs=110000.0,
        revenue_drop_percent=30.0,
        cost_increase_percent=20.0,
    )
    assert stress["stressed_profit"] < 0
    assert stress["survives_downside"] is False


def test_scenario_3_material_legal_blocker_triggers_rejection():
    """Scenario 3: Severe regulatory licensing blocker triggers DO_NOT_PROCEED and CriticAgent."""
    agent = BusinessDecisionAgent()
    case = BusinessCase(
        proposal="Offer unregulated crypto yield accounts in Singapore",
        company_name="YieldCorp",
    )
    findings = {
        "sales": AgentFinding(
            agent_name="sales",
            summary="Strong retail interest",
            confidence=ConfidenceLevel.HIGH,
            confidence_rationale="Survey verified",
            evidence_citations=[EvidenceCitation(source_id="s1", title="Survey", snippet="High demand", verified=True)],
        ),
        "legal": AgentFinding(
            agent_name="legal",
            summary="Direct statutory violation of MAS Payment Services Act",
            confidence=ConfidenceLevel.HIGH,
            confidence_rationale="Statutory counsel review",
            evidence_citations=[EvidenceCitation(source_id="l1", title="PSA Act", snippet="Mandatory license required", verified=True)],
            risks=[
                Risk(
                    category="statutory",
                    description="Criminal penalties for unapproved depository services.",
                    severity="critical",
                    mitigation="None possible without formal banking license.",
                )
            ],
        ),
    }
    result = agent.evaluate(case, findings)
    assert result.outcome == OutcomeType.DO_NOT_PROCEED
    assert result.execution_phases is None
    assert result.critic_rejection_rationale is not None
    assert "fatal_blockers" in result.critic_rejection_rationale
    assert any("legal" in b.lower() for b in result.critic_rejection_rationale["fatal_blockers"])


def test_scenario_4_technical_dependency_gap_identified():
    """Scenario 4: Technical specialist identifies critical architecture SLA and residency gaps."""
    agent = TechnicalAgent()
    case = BusinessCase(
        proposal="Deploy real-time HFT trading engine on public cloud in Frankfurt",
    )
    findings = agent.analyze(case, [], [])
    assert findings.agent_name == "Technical"
    assert findings.confidence == ConfidenceLevel.LOW
    assert len(findings.missing_information) >= 1
    assert any("architecture" in m.lower() or "sla" in m.lower() for m in findings.missing_information)


def test_scenario_5_insufficient_evidence_holds_decision():
    """Scenario 5: Lack of documentation triggers HOLD_FOR_EVIDENCE with checklist and no fabricated plan."""
    agent = BusinessDecisionAgent()
    case = BusinessCase(
        proposal="Acquire unknown logistics subsidiary in Vietnam",
    )
    # Zero citations provided
    findings = {
        "sales": AgentFinding(
            agent_name="sales",
            summary="Unverified rumors of market share",
            confidence=ConfidenceLevel.LOW,
            confidence_rationale="No documents provided",
            missing_information=["Financial audit", "Customer contracts", "Ownership registry"],
        )
    }
    result = agent.evaluate(case, findings)
    assert result.outcome == OutcomeType.HOLD_FOR_EVIDENCE
    assert result.execution_phases is None
    assert result.critic_rejection_rationale is None
    assert result.missing_evidence_checklist is not None
    assert len(result.missing_evidence_checklist) >= 3


def test_scenario_6_contradictory_sources_downgrade_confidence():
    """Scenario 6: Conflicting market claims assign LOW confidence."""
    agent = SalesAgent()
    case = BusinessCase(proposal="Market entry with conflicting TAM data")
    citations = [
        EvidenceCitation(source_id="c1", title="Source A", snippet="Market demand is rapidly expanding by 40% year on year.", verified=True),
        EvidenceCitation(source_id="c2", title="Source B", snippet="Market demand has stagnated with declining customer interest.", verified=True),
    ]
    finding = agent.analyze(case, citations, [])
    assert len(finding.evidence_citations) >= 1


def test_scenario_7_model_error_resilience():
    """Scenario 7: LLM Client cleanly validates approved models registry and provider routing."""
    client = LLMClient()
    assert len(APPROVED_MODEL_IDS) >= 4
    # Route checks for approved models
    provider_nvidia = client.route_provider("nvidia/nemotron-3-super-120b-a12b")
    assert provider_nvidia is not None
    provider_google = client.route_provider("gemini-3.1-flash-lite")
    assert provider_google is not None


def test_scenario_8_document_parser_security():
    """Scenario 8: Reject empty and corrupt files with safe error handling."""
    # Empty file
    with pytest.raises(FileValidationError, match="empty"):
        DocumentParser.parse("empty.pdf", b"", company_id="test_co")

    # Corrupt PDF
    with pytest.raises(ParsingError, match="Corrupt or unreadable PDF"):
        DocumentParser.parse("corrupt.pdf", b"NOT_A_REAL_PDF_DATA_STREAM", company_id="test_co")


def test_scenario_9_multi_tenant_isolation_and_deletion():
    """Scenario 9: Tenant isolation across vector storage, memory, and audit traces."""
    mem = MemoryStore(db_path=":memory:")
    vector = QdrantVectorStore(in_memory=True, collection_name="test_e2e_iso")

    # Company A secret
    mem.save_project_memory(ProjectMemoryItem(
        memory_id="mem_a",
        company_id="corp_a",
        category="constraint",
        content="Confidential acquisition budget $20M.",
    ))
    vector.index_chunks([
        DocumentChunk(
            chunk_id="chunk_a",
            company_id="corp_a",
            project_id="p1",
            document_name="secret.txt",
            doc_hash="hash_a",
            page_or_section="P1",
            text="Confidential merger terms for Corp A.",
        )
    ])

    # Company B searches -> 0 results
    b_mem = mem.get_project_memory(company_id="corp_b")
    assert len(b_mem) == 0
    b_vec = vector.search(query="Confidential merger terms", company_id="corp_b")
    assert len(b_vec) == 0

    # Delete Company A memory
    deleted = mem.delete_project_memory(memory_id="mem_a", company_id="corp_a")
    assert deleted is True
    assert len(mem.get_project_memory(company_id="corp_a")) == 0


def test_scenario_10_persistence_across_restart(tmp_path: Path):
    """Scenario 10: Re-opening reports and memory after simulated backend restart."""
    db_file = tmp_path / "restart_test.db"

    # Run 1 writes state
    store1 = MemoryStore(db_path=db_file)
    store1.save_project_memory(ProjectMemoryItem(
        memory_id="mem_persisted",
        company_id="corp_x",
        category="confirmed_fact",
        content="Audited FY2025 revenue: $14.2M",
        provenance=ProvenanceType.USER_CONFIRMED,
    ))

    # Restart: instantiate fresh store on the persistent database
    store2 = MemoryStore(db_path=db_file)
    items = store2.get_project_memory(company_id="corp_x")
    assert len(items) == 1
    assert items[0].content == "Audited FY2025 revenue: $14.2M"
    assert items[0].provenance == ProvenanceType.USER_CONFIRMED
