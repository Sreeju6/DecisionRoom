"""Unit tests for Phase 7: Persistent Global & Agent Memory with SQLite and Auditability."""
import tempfile
from pathlib import Path
import pytest

from tools.memory import (
    AgentMemoryItem,
    AuditTraceItem,
    MemoryStore,
    ProjectMemoryItem,
    ProvenanceType,
    RunRecord,
)


def test_memory_store_in_memory_crud():
    store = MemoryStore(db_path=":memory:")

    # Create project memory item
    item = ProjectMemoryItem(
        company_id="acme",
        project_id="expansion_eu",
        category="constraint",
        content="Budget ceiling is $150,000 for preliminary licensing.",
        provenance=ProvenanceType.USER_CONFIRMED,
    )
    saved = store.save_project_memory(item)
    assert saved.memory_id == item.memory_id

    # Retrieve
    items = store.get_project_memory(company_id="acme", project_id="expansion_eu")
    assert len(items) == 1
    assert items[0].content == item.content
    assert items[0].provenance == ProvenanceType.USER_CONFIRMED

    # Update
    updated = store.update_project_memory(
        memory_id=item.memory_id,
        company_id="acme",
        content="Updated budget ceiling is $175,000.",
    )
    assert updated is True

    items_after = store.get_project_memory(company_id="acme", project_id="expansion_eu")
    assert items_after[0].content == "Updated budget ceiling is $175,000."

    # Delete
    deleted = store.delete_project_memory(memory_id=item.memory_id, company_id="acme")
    assert deleted is True

    items_deleted = store.get_project_memory(company_id="acme", project_id="expansion_eu")
    assert len(items_deleted) == 0


def test_memory_strict_tenant_isolation():
    store = MemoryStore(db_path=":memory:")

    # Company A stores confidential goal
    item_a = ProjectMemoryItem(
        company_id="company_a",
        project_id="proj_alpha",
        category="goal",
        content="Confidential acquisition of Competitor X",
        provenance=ProvenanceType.USER_CONFIRMED,
    )
    store.save_project_memory(item_a)

    # Company B stores public goal
    item_b = ProjectMemoryItem(
        company_id="company_b",
        project_id="proj_beta",
        category="goal",
        content="Standard Q3 hiring targets",
        provenance=ProvenanceType.USER_CONFIRMED,
    )
    store.save_project_memory(item_b)

    # Company B cannot view Company A's memory
    b_views = store.get_project_memory(company_id="company_b")
    assert len(b_views) == 1
    assert b_views[0].content == "Standard Q3 hiring targets"
    assert "Competitor X" not in [x.content for x in b_views]

    # Company B cannot update or delete Company A's item
    cannot_update = store.update_project_memory(
        memory_id=item_a.memory_id,
        company_id="company_b",
        content="Tampered content",
    )
    assert cannot_update is False

    cannot_delete = store.delete_project_memory(
        memory_id=item_a.memory_id,
        company_id="company_b",
    )
    assert cannot_delete is False

    # Company A's item remains intact
    a_views = store.get_project_memory(company_id="company_a")
    assert len(a_views) == 1
    assert a_views[0].content == "Confidential acquisition of Competitor X"


def test_agent_memory_and_provenance():
    store = MemoryStore(db_path=":memory:")

    agent_item = AgentMemoryItem(
        company_id="acme",
        project_id="proj_1",
        run_id="run_123",
        agent_name="legal",
        content="Statutory filings require 6 weeks advance notice.",
        provenance=ProvenanceType.AI_INFERENCE,
        evidence_source_ids=["law_doc_1", "law_doc_2"],
        confidence="HIGH",
    )
    store.save_agent_memory(agent_item)

    # Query agent memory
    memories = store.get_agent_memory(company_id="acme", agent_name="legal")
    assert len(memories) == 1
    assert memories[0].provenance == ProvenanceType.AI_INFERENCE
    assert "law_doc_1" in memories[0].evidence_source_ids

    # Other agent has no entries
    finance_mems = store.get_agent_memory(company_id="acme", agent_name="finance")
    assert len(finance_mems) == 0


def test_run_records_and_audit_traces():
    store = MemoryStore(db_path=":memory:")

    run = RunRecord(
        run_id="run_abc",
        company_id="acme",
        project_id="proj_x",
        proposal="Evaluate expansion into Singapore fintech sandbox",
        status="IN_PROGRESS",
        models_invoked=["gemma-4-26b-a4b-it"],
    )
    store.save_run(run)

    # Log audit events
    store.log_audit_event(
        run_id="run_abc",
        company_id="acme",
        event_type="AGENT_START",
        details={"agent": "legal", "action": "regulatory_check"},
    )
    store.log_audit_event(
        run_id="run_abc",
        company_id="acme",
        event_type="DECISION_BRANCH",
        details={"branch": "PROCEED", "reason": "All checks passed"},
    )

    # Retrieve run and traces
    fetched_run = store.get_run(run_id="run_abc", company_id="acme")
    assert fetched_run is not None
    assert fetched_run.proposal == run.proposal

    traces = store.get_audit_traces(run_id="run_abc", company_id="acme")
    assert len(traces) == 2
    assert traces[0].event_type == "AGENT_START"
    assert traces[1].event_type == "DECISION_BRANCH"
    assert traces[1].details["branch"] == "PROCEED"


def test_sqlite_persistence_across_restart(tmp_path: Path):
    db_file = tmp_path / "test_persistence.db"

    # Session 1: Create store and write item
    store1 = MemoryStore(db_path=db_file)
    store1.save_project_memory(
        ProjectMemoryItem(
            memory_id="persistent_1",
            company_id="acme",
            category="confirmed_fact",
            content="Company incorporated in Delaware in 2021.",
            provenance=ProvenanceType.USER_CONFIRMED,
        )
    )

    # Session 2: Instantiate new store on the same file
    store2 = MemoryStore(db_path=db_file)
    items = store2.get_project_memory(company_id="acme")
    assert len(items) == 1
    assert items[0].memory_id == "persistent_1"
    assert items[0].content == "Company incorporated in Delaware in 2021."
