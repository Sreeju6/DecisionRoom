"""DecisionRoom Critic Agent.

Critiques evidence quality and missing assumptions for both market-entry
and funding-application decisions. Function signatures match main.py.
"""
from __future__ import annotations


def _as_text(value) -> str:
    return "" if value is None else str(value)


def _report_text(report) -> str:
    if not isinstance(report, dict):
        return _as_text(report).lower()
    parts = []
    for key in ("question", "query", "decision_question", "summary", "policy_summary", "text", "note"):
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
    return any(term in text for term in (
        "tanseed", "funding application", "apply for funding", "apply for tanseed",
        "grant application", "funding scheme", "eligibility before applying",
        "startup funding", "seed fund", "climate-tech startup",
    ))


def _evidence_count(research_report) -> int:
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


def critique_decision_evidence(target_state, data_analysis, research_report, risk_report):
    """Identify unsupported claims, evidence gaps, and actions to resolve them."""
    funding_mode = _is_funding_question(research_report)
    evidence_count = _evidence_count(research_report)
    risks = risk_report.get("risks", []) if isinstance(risk_report, dict) else []
    findings = []

    if funding_mode:
        findings.extend([
            {
                "category": "Current scheme status not verified",
                "finding": "The policy excerpts describe TANSEED provisions but do not confirm the current application window, deadline, budget availability, or latest scheme notification.",
                "description": "Historical policy text cannot establish that applications are open today or that the same terms still apply.",
                "suggested_action": "Check the latest official StartupTN/TANSEED notification and record the date and URL of the current guidelines.",
            },
            {
                "category": "Eligibility not established",
                "finding": "The startup is described as women-led, early-stage, and climate-tech, but the supplied evidence does not confirm that it meets every current legal, registration, stage, sector, ownership, or documentation condition.",
                "description": "A policy category that appears relevant is not the same as confirmed applicant eligibility or a funding award.",
                "suggested_action": "Compare the applicant's documents against the current official eligibility checklist and confirm unresolved points with StartupTN or an authorised incubator.",
            },
            {
                "category": "Funding terms require review",
                "finding": "The policy text mentions equity-linked support and a 3% support stake, but the supplied reports do not independently confirm current contractual terms or obligations.",
                "description": "The startup should not assume the quoted amount, support stake, accelerator, or other benefits are available on identical terms today.",
                "suggested_action": "Obtain the current scheme agreement and review the support stake, permitted uses, milestones, reporting duties, and any other conditions before accepting support.",
            },
            {
                "category": "Application readiness and alternatives",
                "finding": "The reports do not show the applicant's climate-impact measurements, complete application documents, funding requirement, cash-flow plan, or a verified comparison of current alternatives.",
                "description": "These gaps affect application quality and funding fit; they do not by themselves establish that the startup is ineligible.",
                "suggested_action": "Prepare an evidence-backed climate-impact summary, milestones, budget, and document checklist while comparing verified incubator, public, and private funding routes.",
            },
        ])
        if evidence_count == 0:
            findings.insert(0, {
                "category": "No retrieved policy evidence",
                "finding": "The Research Agent did not return relevant policy evidence for this funding decision.",
                "description": "The current assessment cannot be treated as a scheme-specific evaluation without relevant source material.",
                "suggested_action": "Retrieve the official current TANSEED guidelines before drawing a conclusion.",
            })
    else:
        findings.extend([
            {
                "category": "Data limitation",
                "finding": "Funding figures come from an exploratory dataset and may not represent the entire startup ecosystem.",
                "description": "The data can provide context but may not represent all funding activity in the target state.",
                "suggested_action": "Validate funding totals and coverage before using them to justify a market-entry decision.",
            },
            {
                "category": "Missing market evidence",
                "finding": "Startup counts and government policy evidence alone cannot establish whether the proposed business will attract customers or become profitable.",
                "description": "No product-specific demand, competitor, pricing, or validated cost evidence is established by these reports.",
                "suggested_action": "Collect target-customer demand, competitor, pricing, and operating-cost evidence.",
            },
            {
                "category": "Decision readiness",
                "finding": "The current evidence is not sufficient to make a definitive enter-or-do-not-enter recommendation.",
                "description": "The analysis is preliminary and does not establish demand or profitability.",
                "suggested_action": "Address the evidence gaps before making a major market-entry commitment.",
            },
        ])
        research_text = _report_text(research_report)
        if "historical" in research_text or "not confirmed as current" in research_text:
            findings.insert(1, {
                "category": "Policy evidence gap",
                "finding": "Some retrieved policy benefits may be historical and are not confirmed as currently available.",
                "description": "A historical policy passage is not proof of a current scheme or open application window.",
                "suggested_action": "Obtain and verify the current policy document and applicable scheme guidelines.",
            })

    # Add a neutral evidence-count observation only if no other finding exists.
    if not findings:
        findings.append({
            "category": "Limited critique evidence",
            "finding": "The reports do not provide enough structured detail for a complete critique.",
            "description": "The Critic Agent can only assess the supplied report content.",
            "suggested_action": "Provide complete Data, Research, and Risk Agent reports and rerun the analysis.",
        })

    return {
        "target_state": target_state,
        "decision_type": "funding_application" if funding_mode else "market_entry",
        "findings": findings,
        "finding_count": len(findings),
        "decision_readiness_concern": True if funding_mode else any(
            item.get("category") == "Decision readiness" for item in findings
        ),
        "note": (
            "Funding critique focuses on current scheme status, eligibility evidence, terms, and application readiness; it does not determine eligibility."
            if funding_mode else
            "This is a preliminary critique of the supplied evidence and assumptions."
        ),
    }


def print_critique(report):
    """Print the critic report in the existing console style."""
    print("\n" + "=" * 55)
    print("DECISIONROOM — CRITIC AGENT")
    print("=" * 55)
    print(f"Target state: {report.get('target_state', 'Not specified')}")
    if report.get("decision_type") == "funding_application":
        print("Decision type: funding_application")
    findings = report.get("findings", [])
    print(f"Findings: {len(findings)}")
    for index, item in enumerate(findings, start=1):
        print(f"\n--- Finding {index}: {item.get('category', 'Evidence limitation')} ---")
        print(f"Finding: {item.get('finding', item.get('description', ''))}")
        if item.get("description") and item.get("description") != item.get("finding"):
            print(f"Details: {item['description']}")
        print(f"Suggested action: {item.get('suggested_action', 'Investigate this limitation before deciding.')}")
    if report.get("note"):
        print("\nNote: " + report["note"])
