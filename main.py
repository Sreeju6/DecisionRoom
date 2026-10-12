from pathlib import Path
from datetime import datetime
import json

from agents.data_agent import (
    analyze_market_entry,
    print_analysis,
)

from agents.research_agent import (
    search_policy_evidence,
    print_research_results,
)

from agents.tanseed_verification_agent import (
    verify_tanseed_sources,
    print_tanseed_verification,
)

from agents.risk_agent import (
    analyze_market_entry_risks,
    print_risk_analysis,
)

from agents.critic_agent import (
    critique_decision_evidence,
    print_critique,
)

from agents.planner_agent import (
    create_market_entry_plans,
    print_market_entry_plans,
)

from agents.decision_agent import (
    generate_final_decision,
    print_final_decision,
)


def run_decisionroom():
    """Run the complete DecisionRoom multi-agent workflow."""

    print("\n" + "=" * 60)
    print("       DECISIONROOM")
    print("Multi-Agent AI Decision Support System")
    print("=" * 60)

    target_state = input(
        "\nEnter the target state (e.g., Tamil Nadu): "
    ).strip()

    if not target_state:
        print("Error: Please enter a target state.")
        return

    decision_question = input(
        "\nEnter your decision question: "
    ).strip()

    if not decision_question:
        print("Error: Please enter a decision question.")
        return

    # STAGE 1: DATA AGENT
    print("\n\nSTAGE 1: DATA AGENT")
    print("-" * 60)

    data_analysis = analyze_market_entry(target_state)
    print_analysis(data_analysis)

    # STAGE 2: RESEARCH AGENT
    print("\n\nSTAGE 2: RESEARCH AGENT")
    print("-" * 60)

    research_question = (
        f"{decision_question} "
        f"What startup policies, incentives, eligibility "
        f"conditions, and market-entry support are documented "
        f"for {target_state}?"
    )

    research_report = search_policy_evidence(
        research_question,
        top_k=5,
    )
    print_research_results(research_report)

    # STAGE 2B: LIVE TANSEED SOURCE CHECK
    # This checks reachability and page signals only; it does not certify
    # that applications are open or that the startup is eligible.
    funding_question = any(
        term in decision_question.casefold()
        for term in ("tanseed", "funding application", "apply for funding", "grant application")
    )
    if funding_question:
        print("\n\nSTAGE 2B: OFFICIAL-SOURCE VERIFICATION")
        print("-" * 60)
        official_verification = verify_tanseed_sources()
        print_tanseed_verification(official_verification)
        # Keep the report available to downstream agents and the final report.
        research_report["official_verification"] = official_verification

    # Preserve the original question for the Planner Agent.
    # The research query is expanded, so it should not be used
    # as the sole source for decision-type detection.

    # STAGE 3: RISK AGENT
    print("\n\nSTAGE 3: RISK AGENT")
    print("-" * 60)

    risk_report = analyze_market_entry_risks(
        target_state,
        data_analysis,
        research_report,
    )
    print_risk_analysis(risk_report)

    # STAGE 4: CRITIC AGENT
    print("\n\nSTAGE 4: CRITIC AGENT")
    print("-" * 60)

    critique_report = critique_decision_evidence(
        target_state,
        data_analysis,
        research_report,
        risk_report,
    )
    print_critique(critique_report)

    # STAGE 5: PLANNER AGENT
    print("\n\nSTAGE 5: PLANNER AGENT")
    print("-" * 60)

    planner_report = create_market_entry_plans(
        target_state,
        data_analysis,
        research_report,
        risk_report,
        critique_report,
        decision_question=decision_question,
    )
    print_market_entry_plans(planner_report)

    # STAGE 6: FINAL DECISION AGENT
    print("\n\nSTAGE 6: FINAL DECISION AGENT")
    print("-" * 60)

    final_report = generate_final_decision(
        target_state,
        decision_question,
        data_analysis,
        research_report,
        risk_report,
        critique_report,
        planner_report,
    )
    print_final_decision(final_report)

    # FINAL SUMMARY
    print("\n\n" + "=" * 60)
    print("DECISIONROOM — ANALYSIS SUMMARY")
    print("=" * 60)

    print(f"Target state: {target_state}")
    print(f"Decision question: {decision_question}")

    print("\nAgents executed:")
    print("1. Data Agent")
    print("2. Research Agent")
    if funding_question:
        print("3. Official-Source Verification")
        print("4. Risk Agent")
        print("5. Critic Agent")
        print("6. Planner Agent")
        print("7. Final Decision Agent")
    else:
        print("3. Risk Agent")
        print("4. Critic Agent")
        print("5. Planner Agent")
        print("6. Final Decision Agent")

    print("\nReport summary:")
    print(
        "Research evidence items:",
        research_report.get("result_count", 0),
    )
    print("Risks identified:", risk_report.get("risk_count", 0))
    print("Critic findings:", critique_report.get("finding_count", 0))
    print(
        "Alternative plans generated:",
        len(planner_report.get("plans", [])),
    )

    print("\nIMPORTANT:")
    if planner_report.get("decision_type") == "funding_application":
        print(
            "This is a preliminary funding assessment. Verify current "
            "scheme availability, official eligibility criteria, and "
            "application requirements before acting."
        )
    else:
        print(
            "The recommendation uses LLM-assisted evidence synthesis "
            "with a conservative safeguard and rule-based fallback. "
            "It is preliminary, not a validated business forecast. "
            "Verify data quality, current policy eligibility, customer "
            "demand, funding, and operating costs before making an "
            "actual market-entry decision."
        )

    # Save the full multi-agent output without losing structured evidence.
    report_dir = Path("reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "target_state": target_state,
        "decision_question": decision_question,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data_agent": data_analysis,
        "research_agent": research_report,
        "official_verification": research_report.get("official_verification") if funding_question else None,
        "risk_agent": risk_report,
        "critic_agent": critique_report,
        "planner_agent": planner_report,
        "final_decision_agent": final_report,
    }
    output_path = report_dir / f"decisionroom_report_{stamp}.json"
    try:
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print("\nComplete structured report saved:", output_path.resolve())
    except OSError as exc:
        print("\nReport could not be saved:", exc)

    print("\n" + "=" * 60)
    print("DECISIONROOM ANALYSIS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    run_decisionroom()
