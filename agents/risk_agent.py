"""DecisionRoom Risk Agent.

Supports both market-entry decisions and funding-application decisions.
The function signatures are kept compatible with main.py.
"""
from __future__ import annotations


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _report_text(report) -> str:
    """Collect relevant text from a report without assuming one schema."""
    if not isinstance(report, dict):
        return _as_text(report).lower()
    parts = []
    for key in ("question", "query", "decision_question", "summary", "policy_summary", "text"):
        if key in report:
            parts.append(_as_text(report.get(key)))
    for key in ("evidence", "results", "records", "documents", "items"):
        value = report.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    parts.extend(_as_text(v) for v in item.values())
                else:
                    parts.append(_as_text(item))
    return " ".join(parts).lower()


def _is_funding_question(research_report) -> bool:
    text = _report_text(research_report)
    terms = (
        "tanseed", "funding application", "apply for funding", "apply for tanseed",
        "grant application", "funding scheme", "eligibility before applying",
        "startup funding", "seed fund", "climate-tech startup",
    )
    return any(term in text for term in terms)


def _research_evidence_count(research_report) -> int:
    if not isinstance(research_report, dict):
        return 0
    for key in ("result_count", "evidence_count", "results_count"):
        try:
            return int(research_report.get(key, 0))
        except (TypeError, ValueError):
            pass
    for key in ("evidence", "results", "records", "documents", "items"):
        value = research_report.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def analyze_market_entry_risks(target_state, data_analysis, research_report):
    """Return structured risks, adapted to the decision type."""
    funding_mode = _is_funding_question(research_report)
    evidence_count = _research_evidence_count(research_report)

    if funding_mode:
        risks = [
            {
                "category": "Current scheme availability",
                "severity": "High",
                "description": (
                    "The retrieved policy document describes TANSEED provisions, but the supplied evidence "
                    "does not confirm whether applications are currently open, the deadline, or the latest scheme rules."
                ),
                "mitigation": "Check the latest official StartupTN/TANSEED notification and application window before submission.",
            },
            {
                "category": "Applicant eligibility and documentation",
                "severity": "High",
                "description": (
                    "Women-led and climate-action status may be relevant to the policy provisions, but the reports "
                    "do not verify every legal, registration, stage, sector, or documentation requirement for this applicant."
                ),
                "mitigation": "Obtain the current eligibility checklist from StartupTN or an authorised incubator and verify each requirement with documents.",
            },
            {
                "category": "Funding terms and obligations",
                "severity": "Medium",
                "description": (
                    "The policy text describes historical equity-linked support terms, including a 3% support stake. "
                    "The exact current terms and obligations have not been independently confirmed."
                ),
                "mitigation": "Review the current scheme agreement, support-stake terms, eligible expenses, milestones, reporting duties, and repayment or clawback clauses if any.",
            },
            {
                "category": "Evidence of climate impact and use of funds",
                "severity": "Medium",
                "description": "The available reports do not establish the startup's measured climate impact, technical validation, budget, or readiness to use grant support.",
                "mitigation": "Prepare a concise climate-impact case, product evidence, milestones, itemised budget, and measurable outcomes.",
            },
            {
                "category": "Alternative funding fit",
                "severity": "Medium",
                "description": "The current reports do not compare the applicant's needs with currently available incubator grants, other public programmes, or private investment terms.",
                "mitigation": "Compare alternatives using eligibility, application timing, dilution/equity, restrictions, amount, and reporting obligations; verify each scheme independently.",
            },
        ]
        if evidence_count == 0:
            risks.insert(0, {
                "category": "Insufficient scheme evidence",
                "severity": "High",
                "description": "No relevant policy evidence records were returned by the Research Agent, so the scheme-specific assessment is weak.",
                "mitigation": "Retrieve the current official scheme guidelines before making an application decision.",
            })
        return {
            "target_state": target_state,
            "decision_type": "funding_application",
            "risks": risks,
            "risk_count": len(risks),
            "note": "Funding risks are distinct from market-entry risks. The risk assessment does not determine eligibility or guarantee an award.",
        }

    risks = [
        {
            "category": "Data reliability",
            "severity": "High",
            "description": "The funding dataset is exploratory and may not represent total funding across the target state's startup ecosystem.",
            "mitigation": "Validate funding figures against reliable external sources before using them for investment decisions.",
        },
        {
            "category": "Market demand",
            "severity": "Medium",
            "description": "Startup counts and growth do not establish customer demand for the specific product or service.",
            "mitigation": "Conduct customer interviews, competitor analysis, and a small market-validation pilot.",
        },
        {
            "category": "Operating costs",
            "severity": "Medium",
            "description": "The current analysis does not establish local customer acquisition costs, salaries, rent, or distribution costs.",
            "mitigation": "Prepare a state-specific operating budget and validate cost assumptions before committing major capital.",
        },
    ]
    research_text = _report_text(research_report)
    if "historical" in research_text or "not confirmed as current" in research_text or "policy period" in research_text:
        risks.insert(1, {
            "category": "Policy uncertainty",
            "severity": "High",
            "description": "Some retrieved policy details may be historical and are not confirmed as currently available.",
            "mitigation": "Verify current policy documents, eligibility rules, application dates, and benefit conditions.",
        })
    return {
        "target_state": target_state,
        "decision_type": "market_entry",
        "risks": risks,
        "risk_count": len(risks),
        "note": "This is a preliminary risk assessment based on the supplied reports.",
    }


def print_risk_analysis(report):
    """Print the risk report in the existing console style."""
    print("\n" + "=" * 55)
    print("DECISIONROOM — RISK AGENT")
    print("=" * 55)
    print(f"Target state: {report.get('target_state', 'Not specified')}")
    if report.get("decision_type") == "funding_application":
        print("Decision type: funding_application")
    risks = report.get("risks", [])
    print(f"Risks identified: {len(risks)}")
    for index, item in enumerate(risks, start=1):
        print(f"\n--- Risk {index}: {item.get('category', 'Unspecified risk')} ---")
        print(f"Severity: {item.get('severity', 'Unspecified')}")
        print(f"Risk: {item.get('description', '')}")
        print(f"Mitigation: {item.get('mitigation', '')}")
    if report.get("note"):
        print("\nNote: " + report["note"])
