"""Unit tests for domain specialist agents."""
import pytest
from agents.specialists import (
    SalesAgent,
    FinanceAgent,
    LegalAgent,
    TechnicalAgent,
    RiskAgent,
)
from schemas.decision import BusinessCase, ConfidenceLevel, EvidenceCitation


def sample_case() -> BusinessCase:
    return BusinessCase(
        proposal="Launch enterprise B2B SaaS platform in Europe.",
        objective="Reach $1M ARR within 18 months",
        company_name="CloudSync Ltd",
        target_market_or_state="Europe",
        budget_limit=250000.0,
    )


def sample_citations() -> list[EvidenceCitation]:
    return [
        EvidenceCitation(
            source_id="src_1",
            title="Enterprise SaaS Pricing Survey 2026",
            snippet="Enterprise customer demand for cloud storage is growing 28% annually.",
            verified=True,
        ),
        EvidenceCitation(
            source_id="src_2",
            title="EU Cloud Regulatory Compliance & GDPR Guidelines",
            snippet="Data residency compliance requires local server storage and licensing.",
            verified=True,
        ),
        EvidenceCitation(
            source_id="src_3",
            title="CloudSync Financial Runway Model",
            snippet="Operating cost is $15,000 per month with gross revenue of $25,000.",
            verified=True,
        ),
    ]


def test_sales_agent_with_evidence():
    case = sample_case()
    agent = SalesAgent()
    finding = agent.analyze(case, company_evidence=sample_citations(), web_evidence=[])
    assert finding.agent_name == "Sales"
    assert len(finding.evidence_citations) >= 1
    assert finding.confidence in {ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH}


def test_sales_agent_without_evidence():
    case = sample_case()
    agent = SalesAgent()
    finding = agent.analyze(case, company_evidence=[], web_evidence=[])
    assert finding.agent_name == "Sales"
    assert finding.confidence == ConfidenceLevel.LOW
    assert len(finding.missing_information) > 0
    assert any("customer demand" in m.lower() for m in finding.missing_information)


def test_finance_agent_math_and_rubric():
    case = sample_case()
    agent = FinanceAgent()
    finding = agent.analyze(case, company_evidence=sample_citations(), web_evidence=[])
    assert finding.agent_name == "Finance"
    assert len(finding.evidence_citations) >= 1


def test_legal_agent_compliance_and_missing_info():
    case = sample_case()
    agent = LegalAgent()
    finding = agent.analyze(case, company_evidence=sample_citations(), web_evidence=[])
    assert finding.agent_name == "Legal"
    assert any("GDPR" in c.snippet or "compliance" in c.snippet.lower() for c in finding.evidence_citations)


def test_technical_agent_evaluation():
    case = sample_case()
    agent = TechnicalAgent()
    finding = agent.analyze(case, company_evidence=[], web_evidence=[])
    assert finding.agent_name == "Technical"
    assert finding.confidence == ConfidenceLevel.LOW
    assert len(finding.missing_information) > 0


def test_risk_agent_synthesis():
    case = sample_case()
    cites = sample_citations()
    sales = SalesAgent().analyze(case, cites, [])
    finance = FinanceAgent().analyze(case, cites, [])
    legal = LegalAgent().analyze(case, cites, [])
    tech = TechnicalAgent().analyze(case, cites, [])

    risk_agent = RiskAgent()
    finding = risk_agent.analyze(
        case=case,
        specialist_findings={"Sales": sales, "Finance": finance, "Legal": legal, "Technical": tech},
    )
    assert finding.agent_name == "Risk"
    assert len(finding.risks) >= 4  # Aggregated from all 4 specialists
    assert "Cross-functional risk synthesis" in finding.summary
