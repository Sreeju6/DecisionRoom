"""DecisionRoom CLI runner.

Command-line entrypoint backed by the shared orchestration pipeline.
Preserves existing interactive terminal output and reporting.
"""
from __future__ import annotations

import sys
from app.pipeline import run_pipeline

from agents.data_agent import print_analysis
from agents.research_agent import print_research_results
from agents.tanseed_verification_agent import print_tanseed_verification
from agents.risk_agent import print_risk_analysis
from agents.critic_agent import print_critique
from agents.planner_agent import print_market_entry_plans
from agents.decision_agent import print_final_decision


def run_decisionroom():
    """Run the complete DecisionRoom multi-agent workflow from CLI."""

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

    print("\nExecuting multi-agent workflow...")
    payload = run_pipeline(
        target_state=target_state,
        decision_question=decision_question,
        save_report=True,
        report_prefix="decisionroom_report",
    )

    # Display stage results using existing formatted printers
    print("\n\nSTAGE 1: DATA AGENT")
    print("-" * 60)
    print_analysis(payload["data_agent"])

    print("\n\nSTAGE 2: RESEARCH AGENT")
    print("-" * 60)
    print_research_results(payload["research_agent"])

    if payload.get("official_verification"):
        print("\n\nSTAGE 2B: OFFICIAL-SOURCE VERIFICATION")
        print("-" * 60)
        print_tanseed_verification(payload["official_verification"])

    print("\n\nSTAGE 3: RISK AGENT")
    print("-" * 60)
    print_risk_analysis(payload["risk_agent"])

    print("\n\nSTAGE 4: CRITIC AGENT")
    print("-" * 60)
    print_critique(payload["critic_agent"])

    print("\n\nSTAGE 5: PLANNER AGENT")
    print("-" * 60)
    print_market_entry_plans(payload["planner_agent"])

    print("\n\nSTAGE 6: FINAL DECISION AGENT")
    print("-" * 60)
    print_final_decision(payload["final_decision_agent"])

    # Final summary
    print("\n\n" + "=" * 60)
    print("DECISIONROOM — ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Target state: {target_state}")
    print(f"Decision question: {decision_question}")
    if "_report_path" in payload:
        print("\nComplete structured report saved:", payload["_report_path"])
    print("\n" + "=" * 60)
    print("DECISIONROOM ANALYSIS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    run_decisionroom()
