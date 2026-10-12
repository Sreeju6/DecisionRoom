import json

import os

from pathlib import Path

from dotenv import load_dotenv

# Load .env from the main DecisionRoom project folder.

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

try:

    from groq import Groq

except ImportError:

    Groq = None

DEFAULT_MODEL = "openai/gpt-oss-20b"

OPTION_MAP = {

    "Option 1: Full Market Entry":

        "CONSIDER FULL MARKET ENTRY",

    "Option 2: Limited Pilot":

        "CONSIDER A LIMITED MARKET-VALIDATION PILOT",

    "Option 3: Delay Entry":

        "DELAY MAJOR INVESTMENT; VALIDATE KEY ASSUMPTIONS FIRST",

}

FUNDING_OPTION_MAP = {
    "Option 1: Prepare a TANSEED Application":
        "PREPARE A TANSEED APPLICATION, SUBJECT TO ELIGIBILITY VERIFICATION",
    "Option 2: Verify Eligibility Before Applying":
        "VERIFY CURRENT ELIGIBILITY AND SCHEME STATUS BEFORE APPLYING",
    "Option 3: Defer TANSEED and Explore Alternatives":
        "DEFER TANSEED UNTIL REQUIREMENTS ARE VERIFIED; EXPLORE ALTERNATIVES",
}

def _is_funding_decision(planner_report, decision_question=""):
    """Identify funding-application decisions from the Planner Agent."""
    if isinstance(planner_report, dict):
        decision_type = str(planner_report.get("decision_type", "")).strip().lower()
        if decision_type in {"funding_application", "funding", "grant_application"}:
            return True
    question = str(decision_question).lower()
    return any(term in question for term in (
        "tanseed", "apply for funding", "funding application",
        "grant application", "apply for a grant",
    ))


# ============================================================

# HELPER FUNCTIONS

# ============================================================

def _normalize_key(key):

    """Normalize dictionary keys for matching."""

    return "".join(

        character.lower()

        for character in str(key)

        if character.isalnum()

    )

def _find_values(data, possible_keys):

    """Find matching values recursively in dictionaries and lists."""

    normalized_keys = {

        _normalize_key(key)

        for key in possible_keys

    }

    results = []

    if isinstance(data, dict):

        for key, value in data.items():

            if _normalize_key(key) in normalized_keys:

                results.append(value)

            results.extend(

                _find_values(value, possible_keys)

            )

    elif isinstance(data, list):

        for item in data:

            results.extend(

                _find_values(item, possible_keys)

            )

    return results

def _has_funding_records(data_analysis):

    """Check data availability separately from data reliability."""

    availability = _find_values(

        data_analysis,

        ["funding_data_available"],

    )

    if any(value is True for value in availability):

        return True

    records = _find_values(

        data_analysis,

        ["funding_records", "unique_funded_startups"],

    )

    for value in records:

        try:

            if float(value) > 0:

                return True

        except (TypeError, ValueError):

            continue

    return False

def _extract_risks(risk_report):

    """Extract risks, severity levels, and mitigation steps."""

    risks = risk_report.get("risks", [])

    result = []

    if not isinstance(risks, list):

        return result

    for item in risks:

        if not isinstance(item, dict):

            continue

        risk_name = (

            item.get("category")

            or item.get("risk_name")

            or item.get("risk")

            or "Unspecified risk"

        )

        description = (

            item.get("description")

            or item.get("risk_description")

            or (

                item.get("risk", "")

                if item.get("category")

                or item.get("risk_name")

                else ""

            )

        )

        result.append({

            "risk": risk_name,

            "severity": item.get("severity", "Unspecified"),

            "description": description,

            "mitigation": (

                item.get("mitigation")

                or item.get("suggested_mitigation")

                or item.get("recommendation")

                or ""

            ),

        })

    return result

def _extract_findings(critique_report):

    """Extract findings and suggested actions."""

    findings = critique_report.get("findings", [])

    result = []

    if not isinstance(findings, list):

        return result

    for item in findings:

        if not isinstance(item, dict):

            continue

        finding_name = (

            item.get("category")

            or item.get("finding_name")

            or item.get("finding")

            or "Evidence limitation"

        )

        details = (

            item.get("description")

            or item.get("details")

            or (

                item.get("finding", "")

                if item.get("category")

                or item.get("finding_name")

                else ""

            )

        )

        result.append({

            "finding": finding_name,

            "details": details,

            "suggested_action": (

                item.get("suggested_action")

                or item.get("action")

                or item.get("recommendation")

                or item.get("recommended_action")

                or "Investigate this limitation before deciding."

            ),

        })

    return result

def _has_readiness_concern(findings):

    """Check whether the Critic Agent questions decision readiness."""

    phrases = [

        "decision readiness",

        "not sufficient",

        "insufficient evidence",

        "cannot establish",

        "not enough evidence",

        "insufficient to make",

    ]

    for finding in findings:

        text = " ".join(

            str(finding.get(key, ""))

            for key in [

                "finding",

                "details",

                "suggested_action",

            ]

        ).lower()

        if any(phrase in text for phrase in phrases):

            return True

    return False

def _json_safe(value):

    """Convert common Python data objects into JSON-compatible values."""

    if isinstance(value, dict):

        return {

            str(key): _json_safe(item)

            for key, item in value.items()

        }

    if isinstance(value, (list, tuple)):

        return [_json_safe(item) for item in value]

    if value is None or isinstance(

        value, (str, int, float, bool)

    ):

        return value

    if hasattr(value, "to_dict"):

        try:

            return _json_safe(

                value.to_dict(orient="records")

            )

        except (TypeError, ValueError):

            try:

                return _json_safe(value.to_dict())

            except Exception:

                pass

    if hasattr(value, "item"):

        try:

            return value.item()

        except (TypeError, ValueError):

            pass

    return str(value)

def _compact_json(value, max_chars=5000):

    """Convert report data to JSON while limiting prompt size."""

    serialized = json.dumps(

        _json_safe(value),

        ensure_ascii=False,

        indent=2,

    )

    if len(serialized) > max_chars:

        serialized = (

            serialized[:max_chars]

            + "\n[Report shortened for the LLM prompt.]"

        )

    return serialized

def _clean_text(value, fallback):

    """Accept non-empty text or use a fallback."""

    if isinstance(value, str) and value.strip():

        return value.strip()

    return fallback

def _clean_list(value, fallback):

    """Validate a list of text values."""

    if not isinstance(value, list):

        return fallback

    cleaned = [

        str(item).strip()

        for item in value

        if isinstance(item, str) and item.strip()

    ]

    return cleaned[:8] if cleaned else fallback

# ============================================================

# RULE-BASED FALLBACK

# ============================================================

def _build_fallback_report(
    target_state,
    decision_question,
    data_analysis,
    research_report,
    risk_report,
    critique_report,
    planner_report=None,
):
    """Create a preliminary recommendation without an LLM."""
    try:
        evidence_count = int(research_report.get("result_count", 0))
    except (TypeError, ValueError, AttributeError):
        evidence_count = 0

    funding_mode = _is_funding_decision(planner_report or {}, decision_question)
    funding_available = _has_funding_records(data_analysis)
    risks = _extract_risks(risk_report)
    findings = _extract_findings(critique_report)
    high_risk_count = sum(
        1 for risk in risks
        if str(risk.get("severity", "")).strip().lower()
        in {"high", "critical", "very high"}
    )
    readiness_concern = _has_readiness_concern(findings)

    if funding_mode:
        option = "Option 2: Verify Eligibility Before Applying"
        reason = (
            "Current TANSEED availability, detailed eligibility criteria, "
            "deadlines, and required documents are not verified in the supplied evidence."
        )
        justification = (
            "Verify the latest official TANSEED call, applicant eligibility, "
            "application requirements, and equity-linked terms before submitting. "
            "The policy evidence may justify preparing materials in parallel, "
            "but it does not establish that this startup qualifies or that applications are open."
        )
        evidence_gaps = [
            "Confirm current TANSEED availability, deadlines, eligibility criteria, and application requirements from official sources.",
            "Verify the startup's legal status, stage, location, and sector eligibility.",
            "Document measurable climate impact and the proposed use of funds.",
            "Review equity-linked terms and obligations before accepting support.",
            "Compare other current incubator, government, and climate-tech funding options.",
        ]
        conditions = [
            "Check the latest official TANSEED notification and application window.",
            "Verify every eligibility condition and required supporting document.",
            "Prepare a business plan, budget, and evidence of climate impact.",
            "Review equity-linked terms and obligations before accepting support.",
            "Identify alternative funding routes if TANSEED is unavailable or unsuitable.",
        ]
    else:
        if evidence_count == 0 or (high_risk_count >= 2 and readiness_concern):
            option = "Option 3: Delay Entry"
            reason = (
                "Relevant research evidence is missing or multiple high-severity risks "
                "coincide with a decision-readiness concern."
            )
            justification = (
                f"The available analysis for {target_state} contains unresolved evidence gaps. "
                "Delay major investment while validating customer demand, current policy "
                "conditions, and financial assumptions."
            )
        else:
            option = "Option 2: Limited Pilot"
            reason = (
                "Important assumptions about customer demand, funding-data representativeness, "
                "policy eligibility, and operating costs remain unverified."
            )
            justification = (
                f"The analysis for {target_state} provides some startup ecosystem context, "
                "but does not establish customer demand or profitability. A limited pilot "
                "can test demand while reducing initial financial exposure."
            )
        funding_gap = (
            "Funding records are available, but their coverage and representativeness require validation."
            if funding_available else
            "Funding records were not confirmed in the data report."
        )
        evidence_gaps = [
            funding_gap,
            "Validate customer demand and competitor positioning.",
            "Verify current policy benefits and eligibility.",
            "Assess operating costs and expected profitability.",
        ]
        conditions = [
            "Conduct customer interviews and pilot sales.",
            "Compare competitors, pricing, and customer acquisition costs.",
            "Verify current policy benefits and eligibility.",
            "Validate funding records using independent sources.",
            "Prepare a realistic operating budget and financial forecast.",
        ]

    option_map = FUNDING_OPTION_MAP if funding_mode else OPTION_MAP
    return {
        "target_state": target_state,
        "decision_question": decision_question,
        "decision_type": "funding_application" if funding_mode else "market_entry",
        "recommendation": option_map[option],
        "preferred_option": option,
        "confidence": "Low",
        "confidence_reason": reason,
        "funding_records_available": funding_available,
        "evidence_count": evidence_count,
        "high_risk_count": high_risk_count,
        "decision_readiness_concern": readiness_concern,
        "risk_summary": risks,
        "critique_summary": findings,
        "justification": justification,
        "evidence_gaps": evidence_gaps,
        "conditions_before_expansion": conditions,
        "decision_note": (
            "This is a preliminary recommendation, not a verified eligibility determination "
            "or a validated business forecast."
        ),
        "llm_used": False,
        "llm_model": None,
        "llm_status": "Rule-based fallback used.",
        "llm_guardrail_applied": False,
    }

# ============================================================

# LLM DECISION SYNTHESIS

# ============================================================

def _request_llm_decision(

    target_state,

    decision_question,

    data_analysis,

    research_report,

    risk_report,

    critique_report,

    planner_report,

    fallback_report,

):

    """Ask Groq's LLM to evaluate the five agent reports."""

    api_key = os.getenv("GROQ_API_KEY", "").strip()

    if not api_key:

        raise RuntimeError(

            "GROQ_API_KEY is missing. Check the project's .env file."

        )

    if Groq is None:

        raise RuntimeError(

            "Groq is not installed. Run: pip install groq"

        )

    model = os.getenv(

        "GROQ_MODEL",

        DEFAULT_MODEL,

    ).strip()

    client = Groq(api_key=api_key)

    reports = {

        "data_agent": data_analysis,

        "research_agent": research_report,

        "risk_agent": risk_report,

        "critic_agent": critique_report,

        "planner_agent": planner_report,

        "rule_based_baseline": fallback_report,
        "official_source_verification": research_report.get("official_verification", {}),

    }

    context = {

        name: _compact_json(report)

        for name, report in reports.items()

    }

    funding_mode = _is_funding_decision(planner_report, decision_question)
    if funding_mode:
        system_prompt = """
You are the Final Decision Agent in DecisionRoom, a multi-agent decision-support system.
This is a FUNDING-APPLICATION decision, not a market-entry decision.
Choose exactly one of these options:
- Option 1: Prepare a TANSEED Application
- Option 2: Verify Eligibility Before Applying
- Option 3: Defer TANSEED and Explore Alternatives

Evidence rules:
1. Use only facts supported by the supplied reports.
2. Never invent statistics, funding terms, sources, or applicant facts.
3. A historical policy statement does not prove that the scheme is currently open.
4. Policy provisions do not prove that this applicant qualifies.
5. If current availability, deadlines, or detailed eligibility are not verified, prefer Option 2.
6. Preparing application materials in parallel is acceptable, but do not claim eligibility is confirmed.
7. Focus on scheme status, eligibility, climate-impact evidence, documents, equity-linked terms, application effort, and alternatives.
8. Do not use market-entry readiness concerns to force a market-entry option for this funding decision.
9. Keep confidence conservative and do not provide private internal chain-of-thought.

Return only one valid JSON object with keys:
{"preferred_option":"one exact option from the list","confidence":"Low, Low to Moderate, or Moderate","confidence_reason":"brief explanation","justification":"evidence-based explanation","evidence_gaps":["gap 1"],"conditions_before_expansion":["action 1"],"decision_note":"limitations"}
Do not include Markdown fences or text outside the JSON.
"""
        user_task = (
            "Evaluate whether to prepare a TANSEED application, verify eligibility first, "
            "or defer and explore alternatives. Select the most defensible option from the evidence."
        )
    else:
        system_prompt = """

You are the Final Decision Agent in DecisionRoom,

a multi-agent decision-support system.

Your task is to evaluate whether a startup should enter

a target market, run a limited pilot, or delay entry.

Use the supplied reports from the Data, Research, Risk,

Critic, and Planner Agents.

EVIDENCE RULES:

1. Use only facts supported by the supplied reports.

2. Never invent statistics, sources, policy benefits, or financial data.

3. Distinguish available data from reliable or representative data.

4. Historical policy benefits must not be presented as current unless

   the supplied evidence verifies them.

5. Policy provisions do not prove that a specific applicant qualifies.

   Never claim eligibility is confirmed unless the supplied evidence

   contains the applicable eligibility criteria and confirms that the

   applicant meets them. Otherwise, state that eligibility must be verified.

6. Startup counts and funding records do not establish demand or profit.

7. Compare all three plans before selecting the preferred option.

8. Do not recommend full market entry without adequate evidence of

   customer demand, policy eligibility, and financial viability.

9. If no relevant research evidence was retrieved, choose Option 3.

10. If the Critic Agent identifies a decision-readiness concern,

    do not recommend a major commitment; choose Option 3.

11. Keep confidence conservative.

12. Explain your conclusion concisely; do not provide private

    internal chain-of-thought.

Choose exactly one preferred_option:

- Option 1: Full Market Entry

- Option 2: Limited Pilot

- Option 3: Delay Entry

Return only one valid JSON object with these keys:

{

  "preferred_option": "one exact option from the list",

  "confidence": "Low, Low to Moderate, or Moderate",

  "confidence_reason": "brief explanation",

  "justification": "evidence-based explanation",

  "evidence_gaps": ["gap 1", "gap 2"],

  "conditions_before_expansion": ["condition 1", "condition 2"],

  "decision_note": "limitations of the recommendation"

}

Do not include Markdown fences or text outside the JSON.

"""

        user_task = (
            "Evaluate the evidence and compare all three market-entry plans. "
            "Select the option most defensible from the evidence."
        )
    user_prompt = (
        f"Target state: {target_state}\\n"
        f"Decision question: {decision_question}\\n\\n"
        + user_task + "\\n\\n"
        "AGENT REPORTS:\\n"
        + json.dumps(context, ensure_ascii=False)
    )

    response = client.chat.completions.create(

        model=model,

        messages=[

            {

                "role": "system",

                "content": system_prompt,

            },

            {

                "role": "user",

                "content": user_prompt,

            },

        ],

        response_format={"type": "json_object"},

        temperature=0.2,

        max_completion_tokens=1400,

    )

    content = response.choices[0].message.content

    if not content:

        raise ValueError("The LLM returned an empty response.")

    result = json.loads(content)

    if not isinstance(result, dict):

        raise ValueError(

            "The LLM response is not a JSON object."

        )

    raw_option = str(result.get("preferred_option", "")).strip()
    normalized_option = " ".join(raw_option.lower().split())

    if funding_mode:
        option_map = FUNDING_OPTION_MAP
        aliases = {
            "option 1": "Option 1: Prepare a TANSEED Application",
            "prepare a tanseed application": "Option 1: Prepare a TANSEED Application",
            "option 1: prepare a tanseed application": "Option 1: Prepare a TANSEED Application",
            "option 2": "Option 2: Verify Eligibility Before Applying",
            "verify eligibility before applying": "Option 2: Verify Eligibility Before Applying",
            "option 2: verify eligibility before applying": "Option 2: Verify Eligibility Before Applying",
            "option 3": "Option 3: Defer TANSEED and Explore Alternatives",
            "defer tanseed and explore alternatives": "Option 3: Defer TANSEED and Explore Alternatives",
            "option 3: defer tanseed and explore alternatives": "Option 3: Defer TANSEED and Explore Alternatives",
        }
    else:
        option_map = OPTION_MAP
        aliases = {
            "option 1": "Option 1: Full Market Entry",
            "option 1: full market entry": "Option 1: Full Market Entry",
            "full market entry": "Option 1: Full Market Entry",
            "option 2": "Option 2: Limited Pilot",
            "option 2: limited pilot": "Option 2: Limited Pilot",
            "limited pilot": "Option 2: Limited Pilot",
            "option 3": "Option 3: Delay Entry",
            "option 3: delay entry": "Option 3: Delay Entry",
            "delay entry": "Option 3: Delay Entry",
        }

    if normalized_option in option_map:
        result["preferred_option"] = normalized_option
    else:
        normalized_option = aliases.get(normalized_option)
        if normalized_option is None:
            raise ValueError(
                "The LLM returned an unsupported preferred_option: " + repr(raw_option)
            )
        result["preferred_option"] = normalized_option

    return result, model

# ============================================================

# FINAL DECISION AGENT

# ============================================================

def generate_final_decision(
    target_state,
    decision_question,
    data_analysis,
    research_report,
    risk_report,
    critique_report,
    planner_report,
):
    """Generate an LLM-assisted recommendation with decision-type safeguards."""
    report = _build_fallback_report(
        target_state, decision_question, data_analysis, research_report,
        risk_report, critique_report, planner_report,
    )
    funding_mode = report.get("decision_type") == "funding_application"
    verification = research_report.get("official_verification", {}) if isinstance(research_report, dict) else {}
    report["official_verification"] = verification
    if funding_mode and verification:
        report["verification_status"] = verification.get("status", "UNKNOWN")
        report["verification_checked_at"] = verification.get("checked_at")
        report["verification_sources_reachable"] = verification.get("sources_reachable", 0)
        report["verification_sources_total"] = verification.get("sources_total", 0)
        report["verified_current_deadline"] = verification.get("current_application_deadline")
    else:
        report["verification_status"] = "NOT APPLICABLE" if not funding_mode else "NOT CHECKED"
    guardrail_applies = True if funding_mode else (
        report["evidence_count"] == 0 or report["decision_readiness_concern"]
    )

    try:
        result, model = _request_llm_decision(
            target_state, decision_question, data_analysis, research_report,
            risk_report, critique_report, planner_report, report,
        )
    except Exception as error:
        report["llm_status"] = (
            "LLM unavailable; rule-based fallback used. "
            f"Error type: {type(error).__name__}: {error}"
        )
        print("\\nNOTICE: LLM synthesis failed.")
        print("The rule-based fallback will be used.")
        print(f"Error type: {type(error).__name__}")
        return report

    report["llm_used"] = True
    report["llm_model"] = model
    report["llm_guardrail_applied"] = guardrail_applies
    report["evidence_gaps"] = _clean_list(
        result.get("evidence_gaps"), report["evidence_gaps"]
    )
    report["conditions_before_expansion"] = _clean_list(
        result.get("conditions_before_expansion"), report["conditions_before_expansion"]
    )

    if guardrail_applies:
        final_option = (
            "Option 2: Verify Eligibility Before Applying"
            if funding_mode else "Option 3: Delay Entry"
        )
        report["confidence"] = "Low"
        if funding_mode:
            report["confidence_reason"] = (
                "Current TANSEED availability, application deadlines, and this applicant's "
                "detailed eligibility are not verified. Verify them before submitting; "
                "this does not mean the startup is ineligible."
            )
            report["justification"] = (
                _clean_text(result.get("justification"), report["justification"])
                + " Verify current scheme status and eligibility before submitting. "
                "Application materials can be prepared in parallel; policy evidence alone "
                "does not confirm eligibility."
            )
            report["llm_status"] = (
                "LLM synthesis completed; funding-verification safeguard applied."
            )
        else:
            report["confidence_reason"] = (
                "The conservative safeguard retains Delay Entry because the evidence gaps "
                "and decision-readiness concerns remain unresolved."
            )
            report["justification"] = (
                _clean_text(result.get("justification"), report["justification"])
                + " The conservative safeguard retains Delay Entry until critical evidence gaps are addressed."
            )
            report["llm_status"] = "LLM synthesis completed; conservative safeguard applied."
    else:
        final_option = result["preferred_option"]
        confidence = _clean_text(result.get("confidence"), "Low")
        if confidence not in {"Low", "Low to Moderate", "Moderate"}:
            confidence = "Low"
        report["confidence"] = confidence
        report["confidence_reason"] = _clean_text(
            result.get("confidence_reason"), report["confidence_reason"]
        )
        report["justification"] = _clean_text(
            result.get("justification"), report["justification"]
        )
        report["llm_status"] = "LLM synthesis completed successfully."

    report["preferred_option"] = final_option
    option_map = FUNDING_OPTION_MAP if funding_mode else OPTION_MAP
    report["recommendation"] = option_map[final_option]
    report["decision_note"] = _clean_text(
        result.get("decision_note"),
        "This is a preliminary LLM-assisted recommendation.",
    )
    report["decision_note"] += (
        " This is not a verified eligibility determination or validated business forecast; "
        "the recommendation depends on the supplied evidence."
    )
    return report

def print_final_decision(report):

    """Display the final decision report."""

    print("\n" + "=" * 60)

    print("DECISIONROOM — FINAL DECISION AGENT")

    print("=" * 60)

    print(f"Target state: {report['target_state']}")

    print(f"Decision question: {report['decision_question']}")

    print("\nDECISION METHOD")

    if report["llm_used"]:

        print("LLM-assisted evidence synthesis")

        print(f"Model: {report['llm_model']}")

    else:

        print("Rule-based fallback")

    print(f"Status: {report['llm_status']}")

    print("\nRECOMMENDATION")

    print(report["recommendation"])

    print(f"Preferred plan: {report['preferred_option']}")

    print(f"Confidence: {report['confidence']}")

    print(f"Reason: {report['confidence_reason']}")

    if report.get("decision_type") == "funding_application":
        print("\nOFFICIAL-SOURCE VERIFICATION")
        print("Status:", report.get("verification_status", "NOT CHECKED"))
        print("Checked at:", report.get("verification_checked_at", "Not checked"))
        print("Reachable sources:", f"{report.get('verification_sources_reachable', 0)}/{report.get('verification_sources_total', 0)}")
        print("Verified current deadline:", report.get("verified_current_deadline") or "NOT VERIFIED")
        print("Applicant eligibility: NOT VERIFIED")

    print("\nDECISION FACTORS")

    print(

        f"Retrieved evidence records: {report['evidence_count']}"

    )

    print(

        "Funding records available: "

        f"{report['funding_records_available']}"

    )

    print(f"High-severity risks: {report['high_risk_count']}")

    print(

        "Decision-readiness concern: "

        f"{report['decision_readiness_concern']}"

    )

    print(

        "Conservative safeguard applied: "

        f"{report['llm_guardrail_applied']}"

    )

    print("\nJUSTIFICATION")

    print(report["justification"])

    print("\nKEY RISKS")

    if report["risk_summary"]:

        for item in report["risk_summary"]:

            print(

                f"- {item['risk']} "

                f"(Severity: {item['severity']})"

            )

            if item["description"]:

                print(f"  Details: {item['description']}")

            if item["mitigation"]:

                print(f"  Mitigation: {item['mitigation']}")

    else:

        print("No structured risk details were available.")

    print("\nCRITIC AGENT FINDINGS")

    if report["critique_summary"]:

        for item in report["critique_summary"]:

            print(f"- {item['finding']}")

            if item["details"]:

                print(f"  Details: {item['details']}")

            print(

                f"  Suggested action: {item['suggested_action']}"

            )

    else:

        print("No structured Critic Agent findings were available.")

    print("\nEVIDENCE GAPS TO ADDRESS")

    for gap in report["evidence_gaps"]:

        print(f"- {gap}")

    print("\nCONDITIONS BEFORE EXPANSION")

    for condition in report["conditions_before_expansion"]:

        print(f"- {condition}")

    print("\nDECISION NOTE")

    print(report["decision_note"])

    print("\n" + "=" * 60)

    print("END OF FINAL DECISION REPORT")

    print("=" * 60)