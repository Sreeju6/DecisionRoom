def create_market_entry_plans(
    target_state,
    data_analysis,
    research_report,
    risk_report,
    critique_report,
    decision_question="",
):
    """Generate plans appropriate to the user's decision type."""

    question = str(decision_question).lower()

    funding_keywords = [
        "apply for tanseed",
        "tanseed funding",
        "apply for funding",
        "funding application",
        "should we apply",
        "should a startup apply",
        "grant application",
        "seed funding",
    ]
    is_funding_decision = any(
        keyword in question for keyword in funding_keywords
    )

    evidence_count = research_report.get("result_count", 0)
    risk_count = risk_report.get("risk_count", 0)
    critique_count = critique_report.get("finding_count", 0)

    if is_funding_decision:
        plans = [
            {
                "option": "Option 1: Prepare a TANSEED Application",
                "description": (
                    "Prepare an application for the relevant funding scheme "
                    "after verifying current availability and all eligibility "
                    "requirements."
                ),
                "advantages": [
                    "May provide early-stage financial support.",
                    "May provide access to mentoring and an accelerator.",
                    "Could help fund development and validation activities.",
                ],
                "conditions": [
                    "Confirm that TANSEED applications are currently open.",
                    "Verify the latest eligibility rules and required documents.",
                    "Confirm the startup's legal status, stage, and climate-action eligibility.",
                    "Review the support-stake terms and other funding conditions.",
                ],
                "risk_level": "Medium",
            },
            {
                "option": "Option 2: Verify Eligibility Before Applying",
                "description": (
                    "Contact StartupTN or an authorised incubator to confirm "
                    "scheme availability and applicant eligibility before "
                    "committing resources to an application."
                ),
                "advantages": [
                    "Reduces the risk of applying under an unsuitable scheme.",
                    "Clarifies eligibility and documentation requirements.",
                    "Allows comparison of suitable funding routes.",
                ],
                "conditions": [
                    "Obtain the latest official scheme guidelines.",
                    "Confirm application dates, selection criteria, and support terms.",
                    "Prepare evidence of the startup's climate impact and progress.",
                    "Compare the application effort with other funding options.",
                ],
                "risk_level": "Low",
            },
            {
                "option": "Option 3: Defer TANSEED and Explore Alternatives",
                "description": (
                    "Defer the TANSEED application if eligibility, availability, "
                    "or required documentation cannot be confirmed, while "
                    "investigating other suitable options."
                ),
                "advantages": [
                    "Avoids relying on unverified eligibility assumptions.",
                    "Allows time to strengthen business and impact evidence.",
                    "Enables comparison with incubator grants, angel investment, "
                    "and other applicable programmes.",
                ],
                "conditions": [
                    "Identify alternative schemes and independently verify their terms.",
                    "Develop a funding requirement and cash-flow estimate.",
                    "Set a date to reassess TANSEED eligibility and availability.",
                ],
                "risk_level": "Low initial commitment",
            },
        ]
        planning_note = (
            "These are preliminary funding options, not confirmation of "
            "eligibility, an open application window, or a funding award. "
            "Verify current official requirements before applying."
        )
        decision_type = "funding_application"

    else:
        plans = [
            {
                "option": "Option 1: Full Market Entry",
                "description": (
                    f"Launch operations across the target market in {target_state}."
                ),
                "advantages": [
                    "Potential to establish a presence quickly.",
                    "Access to a broader customer base from the start.",
                ],
                "conditions": [
                    "Validate customer demand and competitor positioning.",
                    "Confirm current policy eligibility and benefits.",
                    "Verify funding estimates and prepare a detailed budget.",
                ],
                "risk_level": "High",
            },
            {
                "option": "Option 2: Limited Pilot",
                "description": (
                    f"Test the business in a selected city or customer segment "
                    f"within {target_state} before scaling."
                ),
                "advantages": [
                    "Limits initial financial exposure.",
                    "Allows real customer-demand validation.",
                    "Produces evidence for a later expansion decision.",
                ],
                "conditions": [
                    "Choose a specific target customer segment.",
                    "Set a limited pilot budget and measurable success criteria.",
                    "Measure customer acquisition, conversion, and retention.",
                ],
                "risk_level": "Medium",
            },
            {
                "option": "Option 3: Delay Entry",
                "description": (
                    "Postpone major investment until the most important evidence "
                    "gaps have been addressed."
                ),
                "advantages": [
                    "Provides time to verify policy benefits and eligibility.",
                    "Allows funding data and operating costs to be checked.",
                ],
                "conditions": [
                    "Obtain current policy documents and scheme guidelines.",
                    "Validate the target market and operating-cost assumptions.",
                    "Set a date to reassess the decision.",
                ],
                "risk_level": "Low initial commitment",
            },
        ]
        planning_note = (
            "These are preliminary market-entry options based on the available "
            "analysis. They are not a validated business forecast or a final "
            "enter-or-do-not-enter recommendation."
        )
        decision_type = "market_entry"

    return {
        "target_state": target_state,
        "plans": plans,
        "decision_type": decision_type,
        "evidence_count": evidence_count,
        "risk_count": risk_count,
        "critique_count": critique_count,
        "planning_note": planning_note,
    }


def print_market_entry_plans(report):
    """Print the alternative plans."""

    print("\n" + "=" * 60)
    print("DECISIONROOM — PLANNER AGENT")
    print("=" * 60)
    print(f"Target state: {report['target_state']}")
    print(f"Decision type: {report.get('decision_type', 'market_entry')}")

    for plan in report["plans"]:
        print(f"\n{plan['option']}")
        print(f"Description: {plan['description']}")
        print(f"Risk level: {plan['risk_level']}")

        print("Advantages:")
        for advantage in plan["advantages"]:
            print(f"  - {advantage}")

        print("Conditions to address:")
        for condition in plan["conditions"]:
            print(f"  - {condition}")

    print("\nPlanning note:")
    print(report["planning_note"])
