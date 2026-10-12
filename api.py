"""FastAPI adapter for the existing DecisionRoom agents.

Place api.py in the DecisionRoom project root, beside main.py.
This adapter calls the existing agents directly; it does not duplicate them.
"""
from __future__ import annotations

import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.data_agent import analyze_market_entry
from agents.research_agent import search_policy_evidence
from agents.tanseed_verification_agent import verify_tanseed_sources
from agents.risk_agent import analyze_market_entry_risks
from agents.critic_agent import critique_decision_evidence
from agents.planner_agent import create_market_entry_plans
from agents.decision_agent import generate_final_decision

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="DecisionRoom API", version="1.0.0")

# Local development + Netlify frontend. You can restrict this to your exact
# Netlify URL later using the DECISIONROOM_CORS_ORIGINS environment variable.
origins = os.getenv(
    "DECISIONROOM_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,https://*.netlify.app",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in origins.split(",") if item.strip() and "*" not in item],
    allow_origin_regex=r"https://[a-zA-Z0-9-]+\.netlify\.app" if "*.netlify.app" in origins else None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    target_state: str = Field(min_length=2, max_length=100)
    decision_question: str = Field(min_length=10, max_length=3000)

def json_safe(value: Any) -> Any:
    """Convert nested agent results into JSON-compatible values."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(value)

@app.get("/")
def root():
    return {"name": "DecisionRoom API", "status": "ok", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "DecisionRoom API"}

@app.post("/api/analyze")
def analyze(request: AnalysisRequest):
    state = request.target_state.strip()
    question = request.decision_question.strip()
    if not state or not question:
        raise HTTPException(status_code=422, detail="Target state and decision question are required.")

    try:
        # Stage 1 — data and market context
        data_report = analyze_market_entry(state)

        # Stage 2 — retrieval-augmented policy research
        research_question = (
            f"{question} What startup policies, incentives, eligibility conditions, "
            f"and market-entry support are documented for {state}?"
        )
        research_report = search_policy_evidence(research_question, top_k=5)

        # Stage 2B — TANSEED verification only when relevant
        funding_question = any(
            term in question.casefold()
            for term in ("tanseed", "funding application", "apply for funding", "grant application")
        )
        if funding_question:
            research_report["official_verification"] = verify_tanseed_sources()

        # Stages 3–6 — existing risk, critic, planner, and decision agents
        risk_report = analyze_market_entry_risks(state, data_report, research_report)
        critique_report = critique_decision_evidence(
            state, data_report, research_report, risk_report
        )
        planner_report = create_market_entry_plans(
            state, data_report, research_report, risk_report, critique_report,
            decision_question=question,
        )
        final_report = generate_final_decision(
            state, question, data_report, research_report, risk_report,
            critique_report, planner_report,
        )

        payload = {
            "target_state": state,
            "decision_question": question,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "data_agent": data_report,
            "research_agent": research_report,
            "official_verification": research_report.get("official_verification") if funding_question else None,
            "risk_agent": risk_report,
            "critic_agent": critique_report,
            "planner_agent": planner_report,
            "final_decision_agent": final_report,
        }

        # Save a copy just like the CLI workflow, without printing large reports.
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (reports_dir / f"decisionroom_web_report_{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return json_safe(payload)

    except HTTPException:
        raise
    except Exception as exc:
        # Log full details to the API terminal; send a safe message to the browser.
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"DecisionRoom analysis failed: {type(exc).__name__}: {exc}",
        ) from exc
