"""Tests for FastAPI endpoints, pipeline serialization, and contract compatibility."""
import io
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from api import app
from app.pipeline import json_safe, _is_funding_question


@pytest.fixture
def client():
    return TestClient(app)


def test_api_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["name"] == "DecisionRoom API"


def test_api_health_endpoint_no_external_calls(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "DecisionRoom API"}


def test_api_config_status_does_not_leak_secrets(client):
    res = client.get("/api/config/status")
    assert res.status_code == 200
    data = res.json()
    # Check that secrets are redacted
    for key, val in data.items():
        if "api_key" in key:
            assert "AIza" not in str(val) or "..." in str(val)
            assert "nvap" not in str(val) or "..." in str(val)


def test_funding_question_detection():
    assert _is_funding_question("Should we apply for TANSEED grant funding?") is True
    assert _is_funding_question("What is our funding application strategy?") is True
    assert _is_funding_question("What is the competitor pricing in Karnataka?") is False


def test_json_safe_helper():
    now = datetime.now(timezone.utc)
    raw = {
        "time": now,
        "tuple_val": (1, 2, "3"),
        "nested": {"bool_val": True, "none_val": None},
    }
    safe = json_safe(raw)
    assert isinstance(safe["time"], str)
    assert safe["tuple_val"] == [1, 2, "3"]
    assert safe["nested"]["bool_val"] is True
    assert safe["nested"]["none_val"] is None


def test_api_validation_error_on_empty_payload(client):
    res = client.post("/api/analyze", json={"target_state": "", "decision_question": ""})
    assert res.status_code == 422


def test_api_decision_room_endpoint(client):
    """Test POST /api/decision executes business decision evaluation."""
    payload = {
        "proposal": "Should we expand cloud operations into Germany?",
        "objective": "Market Expansion",
        "company_name": "Acme Global",
        "target_market_or_state": "Germany",
        "budget_limit": 150000.0,
        "constraints": ["Must comply with GDPR statutory guidelines"],
    }
    res = client.post("/api/decision?company_id=test_corp", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "outcome" in data
    assert data["outcome"] in ["PROCEED", "DO_NOT_PROCEED", "HOLD_FOR_EVIDENCE"]
    assert "run_id" in data
    assert "agent_findings" in data
    assert "decision_result" in data


def test_api_runs_and_traces_endpoints(client):
    """Test GET /api/runs and GET /api/runs/{run_id}."""
    # List runs for company
    res = client.get("/api/runs?company_id=test_corp")
    assert res.status_code == 200
    runs = res.json()
    assert isinstance(runs, list)
    if runs:
        run_id = runs[0]["run_id"]
        res_trace = client.get(f"/api/runs/{run_id}?company_id=test_corp")
        assert res_trace.status_code == 200
        trace_data = res_trace.json()
        assert "run" in trace_data
        assert "traces" in trace_data


def test_api_memory_crud_endpoints(client):
    """Test GET, POST, and DELETE /api/memory."""
    item_payload = {
        "company_id": "api_test_co",
        "project_id": "p1",
        "category": "constraint",
        "content": "Strict regulatory audit completed with 0 non-conformances.",
        "provenance": "user_confirmed",
    }
    # Save memory
    post_res = client.post("/api/memory", json=item_payload)
    assert post_res.status_code == 200
    saved = post_res.json()
    mem_id = saved["memory_id"]

    # Get memory
    get_res = client.get("/api/memory?company_id=api_test_co")
    assert get_res.status_code == 200
    items = get_res.json()
    assert len(items) >= 1
    assert any(i["memory_id"] == mem_id for i in items)

    # Delete memory
    del_res = client.delete(f"/api/memory/{mem_id}?company_id=api_test_co")
    assert del_res.status_code == 200


def test_api_document_ingest_endpoint(client):
    """Test document text ingestion into vector store."""
    payload = {
        "company_id": "api_test_co",
        "project_id": "p1",
        "document_name": "pricing_sheet.txt",
        "text": "Enterprise plan pricing is $50,000 annually with 99.9% uptime SLA.",
        "page_or_section": "Pricing Table",
    }
    res = client.post("/api/documents/ingest", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "indexed"
    assert data["chunks_indexed"] == 1


def test_api_document_upload_list_and_delete(client):
    """Test multipart file upload, listing, and scoped deletion."""
    content = b"Financial projections: Year 1 revenue $1.2M, operating expenses $800k, EBITDA margin 33%."
    files = {"file": ("projections.txt", io.BytesIO(content), "text/plain")}
    upload_res = client.post(
        "/api/documents/upload?company_id=upload_co&project_id=upload_proj",
        files=files,
    )
    assert upload_res.status_code == 200
    up_data = upload_res.json()
    assert up_data["status"] == "indexed"
    assert up_data["document_name"] == "projections.txt"
    assert up_data["chunks_indexed"] >= 1
    doc_hash = up_data["doc_hash"]

    # List documents
    list_res = client.get("/api/documents?company_id=upload_co&project_id=upload_proj")
    assert list_res.status_code == 200
    docs = list_res.json()
    assert any(d["doc_hash"] == doc_hash for d in docs)

    # Delete document
    del_res = client.delete(f"/api/documents/{doc_hash}?company_id=upload_co&project_id=upload_proj")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["status"] == "deleted"

    # Verify document removed from list
    list_after = client.get("/api/documents?company_id=upload_co&project_id=upload_proj").json()
    assert not any(d["doc_hash"] == doc_hash for d in list_after)
