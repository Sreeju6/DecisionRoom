"""Persistent Global and Agent Memory with SQLite and Auditability for DecisionRoom.

Enforces:
- Structured state & audit trails via SQLite (WAL mode for concurrency).
- Strict multi-tenant isolation by company_id and project_id.
- Explicit memory provenance: USER_CONFIRMED, SOURCE_DERIVED, AI_INFERENCE.
- Invariant: Never silently promote an AI inference to a user-confirmed fact.
- Audit tracing of agent status, models used, tool calls, latencies, and errors.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from config.config import settings

logger = logging.getLogger("decisionroom.memory")


class ProvenanceType(str, Enum):
    """Memory provenance classification."""
    USER_CONFIRMED = "user_confirmed"
    SOURCE_DERIVED = "source_derived"
    AI_INFERENCE = "ai_inference"


class ProjectMemoryItem(BaseModel):
    """Confirmed context, constraints, goals, or unresolved questions for a project."""
    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    project_id: str = "default"
    category: str  # "constraint", "goal", "confirmed_fact", "unresolved_question"
    content: str
    provenance: ProvenanceType = ProvenanceType.USER_CONFIRMED
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentMemoryItem(BaseModel):
    """Specialist agent finding, assumption, or follow-up issue."""
    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    project_id: str = "default"
    run_id: str
    agent_name: str
    content: str
    provenance: ProvenanceType = ProvenanceType.AI_INFERENCE
    evidence_source_ids: List[str] = Field(default_factory=list)
    confidence: str = "MEDIUM"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RunRecord(BaseModel):
    """Audit log and metadata for an analysis run."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    project_id: str = "default"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    status: str = "IN_PROGRESS"  # "IN_PROGRESS", "SUCCESS", "FAILED"
    proposal: str
    outcome: Optional[str] = None
    confidence: Optional[str] = None
    models_invoked: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    decision_result: Optional[Dict[str, Any]] = None


class AuditTraceItem(BaseModel):
    """Granular execution trace event for observability."""
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    company_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str  # e.g., "AGENT_START", "TOOL_CALL", "DECISION_BRANCH", "AGENT_ERROR"
    details: Dict[str, Any] = Field(default_factory=dict)


class MemoryStore:
    """Production memory manager backed by SQLite with strict tenant isolation."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            settings.storage_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(settings.sqlite_path)
            self.is_memory = False
        elif str(db_path) == ":memory:":
            self.db_path = ":memory:"
            self.is_memory = True
            # For in-memory, retain an active connection so tables persist across operations
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
        else:
            p = Path(db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(p)
            self.is_memory = False

        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        if self.is_memory:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        """Create structured tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_memory (
                    memory_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_proj_mem_company ON project_memory(company_id, project_id);

                CREATE TABLE IF NOT EXISTS agent_memory (
                    memory_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    evidence_source_ids TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_mem_company ON agent_memory(company_id, project_id, agent_name);

                CREATE TABLE IF NOT EXISTS analysis_runs (
                    run_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    proposal TEXT NOT NULL,
                    outcome TEXT,
                    confidence TEXT,
                    models_invoked TEXT NOT NULL,
                    errors TEXT NOT NULL,
                    decision_result TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_runs_company ON analysis_runs(company_id, project_id);

                CREATE TABLE IF NOT EXISTS audit_traces (
                    trace_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_traces_run ON audit_traces(company_id, run_id);

                CREATE TABLE IF NOT EXISTS document_registry (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    document_name TEXT NOT NULL,
                    doc_hash TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    ingested_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_doc_reg_company ON document_registry(company_id, project_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_reg_hash ON document_registry(company_id, project_id, doc_hash);
                """
            )

    # ---------------------------------------------------------
    # Project Memory CRUD
    # ---------------------------------------------------------
    def save_project_memory(self, item: ProjectMemoryItem) -> ProjectMemoryItem:
        """Insert or replace project memory item with tenant scope."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO project_memory (
                    memory_id, company_id, project_id, category, content, provenance, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.memory_id,
                    item.company_id,
                    item.project_id,
                    item.category,
                    item.content,
                    item.provenance.value,
                    item.created_at,
                    item.updated_at,
                ),
            )
        return item

    def get_project_memory(
        self,
        company_id: str,
        project_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[ProjectMemoryItem]:
        """Retrieve project memory items enforcing strict tenant isolation."""
        query = "SELECT * FROM project_memory WHERE company_id = ?"
        params: List[Any] = [company_id]
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            ProjectMemoryItem(
                memory_id=r["memory_id"],
                company_id=r["company_id"],
                project_id=r["project_id"],
                category=r["category"],
                content=r["content"],
                provenance=ProvenanceType(r["provenance"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def update_project_memory(
        self,
        memory_id: str,
        company_id: str,
        content: str,
        provenance: Optional[ProvenanceType] = None,
    ) -> bool:
        """Update existing memory content and timestamp, preventing unauthorized provenance promotion."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT provenance FROM project_memory WHERE memory_id = ? AND company_id = ?",
                (memory_id, company_id),
            ).fetchone()
            if not existing:
                return False

            if provenance:
                # Invariant: Never silently promote AI inference to user confirmed without explicit intent
                new_prov = provenance.value
            else:
                new_prov = existing["provenance"]

            cursor = conn.execute(
                """
                UPDATE project_memory
                SET content = ?, provenance = ?, updated_at = ?
                WHERE memory_id = ? AND company_id = ?
                """,
                (content, new_prov, now, memory_id, company_id),
            )
            return cursor.rowcount > 0

    def delete_project_memory(self, memory_id: str, company_id: str) -> bool:
        """Delete project memory item enforcing tenant ownership."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM project_memory WHERE memory_id = ? AND company_id = ?",
                (memory_id, company_id),
            )
            return cursor.rowcount > 0

    # ---------------------------------------------------------
    # Agent Memory CRUD
    # ---------------------------------------------------------
    def save_agent_memory(self, item: AgentMemoryItem) -> AgentMemoryItem:
        """Store specialist agent finding or assumption."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_memory (
                    memory_id, company_id, project_id, run_id, agent_name, content, provenance, evidence_source_ids, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.memory_id,
                    item.company_id,
                    item.project_id,
                    item.run_id,
                    item.agent_name,
                    item.content,
                    item.provenance.value,
                    json.dumps(item.evidence_source_ids),
                    item.confidence,
                    item.created_at,
                ),
            )
        return item

    def get_agent_memory(
        self,
        company_id: str,
        agent_name: Optional[str] = None,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> List[AgentMemoryItem]:
        """Query agent findings with tenant isolation."""
        query = "SELECT * FROM agent_memory WHERE company_id = ?"
        params: List[Any] = [company_id]
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            AgentMemoryItem(
                memory_id=r["memory_id"],
                company_id=r["company_id"],
                project_id=r["project_id"],
                run_id=r["run_id"],
                agent_name=r["agent_name"],
                content=r["content"],
                provenance=ProvenanceType(r["provenance"]),
                evidence_source_ids=json.loads(r["evidence_source_ids"]),
                confidence=r["confidence"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def delete_agent_memory(self, memory_id: str, company_id: str) -> bool:
        """Delete agent memory entry."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM agent_memory WHERE memory_id = ? AND company_id = ?",
                (memory_id, company_id),
            )
            return cursor.rowcount > 0

    # ---------------------------------------------------------
    # Run Records & Audit Logs
    # ---------------------------------------------------------
    def save_run(self, run: RunRecord) -> RunRecord:
        """Create or update an analysis run record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO analysis_runs (
                    run_id, company_id, project_id, created_at, completed_at, status,
                    proposal, outcome, confidence, models_invoked, errors, decision_result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.company_id,
                    run.project_id,
                    run.created_at,
                    run.completed_at,
                    run.status,
                    run.proposal,
                    run.outcome,
                    run.confidence,
                    json.dumps(run.models_invoked),
                    json.dumps(run.errors),
                    json.dumps(run.decision_result) if run.decision_result else None,
                ),
            )
        return run

    def get_run(self, run_id: str, company_id: str) -> Optional[RunRecord]:
        """Fetch run record ensuring company isolation."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_runs WHERE run_id = ? AND company_id = ?",
                (run_id, company_id),
            ).fetchone()
            if not row:
                return None
            return RunRecord(
                run_id=row["run_id"],
                company_id=row["company_id"],
                project_id=row["project_id"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
                status=row["status"],
                proposal=row["proposal"],
                outcome=row["outcome"],
                confidence=row["confidence"],
                models_invoked=json.loads(row["models_invoked"]),
                errors=json.loads(row["errors"]),
                decision_result=json.loads(row["decision_result"]) if row["decision_result"] else None,
            )

    def list_runs(
        self,
        company_id: str,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[RunRecord]:
        """List historical runs for a company/project."""
        query = "SELECT * FROM analysis_runs WHERE company_id = ?"
        params: List[Any] = [company_id]
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            RunRecord(
                run_id=r["run_id"],
                company_id=r["company_id"],
                project_id=r["project_id"],
                created_at=r["created_at"],
                completed_at=r["completed_at"],
                status=r["status"],
                proposal=r["proposal"],
                outcome=r["outcome"],
                confidence=r["confidence"],
                models_invoked=json.loads(r["models_invoked"]),
                errors=json.loads(r["errors"]),
                decision_result=json.loads(r["decision_result"]) if r["decision_result"] else None,
            )
            for r in rows
        ]

    def log_audit_event(
        self,
        run_id: str,
        company_id: str,
        event_type: str,
        details: Dict[str, Any],
    ) -> AuditTraceItem:
        """Record granular audit event for trace observability."""
        item = AuditTraceItem(
            run_id=run_id,
            company_id=company_id,
            event_type=event_type,
            details=details,
        )
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_traces (trace_id, run_id, company_id, timestamp, event_type, details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.trace_id,
                    item.run_id,
                    item.company_id,
                    item.timestamp,
                    item.event_type,
                    json.dumps(item.details),
                ),
            )
        return item

    def get_audit_traces(self, run_id: str, company_id: str) -> List[AuditTraceItem]:
        """Fetch audit trace events for a specific run."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM audit_traces
                WHERE run_id = ? AND company_id = ?
                ORDER BY timestamp ASC
                """,
                (run_id, company_id),
            ).fetchall()

        return [
            AuditTraceItem(
                trace_id=r["trace_id"],
                run_id=r["run_id"],
                company_id=r["company_id"],
                timestamp=r["timestamp"],
                event_type=r["event_type"],
                details=json.loads(r["details"]),
            )
            for r in rows
        ]

    # ---------------------------------------------------------
    # Document Registry
    # ---------------------------------------------------------

    def register_document(
        self,
        company_id: str,
        project_id: str,
        document_name: str,
        doc_hash: str,
        doc_type: str,
        file_size: int,
        chunk_count: int,
        status: str = "indexed",
    ) -> None:
        """Upsert document registry entry scoped to company + project."""
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO document_registry
                    (id, company_id, project_id, document_name, doc_hash, doc_type, file_size, chunk_count, status, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id, project_id, doc_hash) DO UPDATE SET
                    document_name=excluded.document_name,
                    chunk_count=excluded.chunk_count,
                    status=excluded.status,
                    ingested_at=excluded.ingested_at
                """,
                (doc_id, company_id, project_id, document_name, doc_hash, doc_type, file_size, chunk_count, status, now),
            )

    def list_documents(
        self,
        company_id: str,
        project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List documents in the registry scoped to company and optional project."""
        query = "SELECT * FROM document_registry WHERE company_id = ?"
        params: List[Any] = [company_id]
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        query += " ORDER BY ingested_at DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [dict(r) for r in rows]

    def delete_document_registry(
        self,
        company_id: str,
        project_id: str,
        doc_hash: str,
    ) -> bool:
        """Remove document registry entry enforcing company + project scope."""
        with self._get_connection() as conn:
            result = conn.execute(
                "DELETE FROM document_registry WHERE company_id = ? AND project_id = ? AND doc_hash = ?",
                (company_id, project_id, doc_hash),
            )
        return result.rowcount > 0

    # ---------------------------------------------------------
    # Agent Memory Query
    # ---------------------------------------------------------

    def get_agent_memories(
        self,
        company_id: str,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> List[AgentMemoryItem]:
        """Retrieve per-agent memory records for observability, scoped by tenant."""
        query = "SELECT * FROM agent_memory WHERE company_id = ?"
        params: List[Any] = [company_id]
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        query += " ORDER BY created_at DESC LIMIT 200"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            AgentMemoryItem(
                memory_id=r["memory_id"],
                company_id=r["company_id"],
                project_id=r["project_id"],
                run_id=r["run_id"],
                agent_name=r["agent_name"],
                content=r["content"],
                provenance=ProvenanceType(r["provenance"]),
                evidence_source_ids=json.loads(r["evidence_source_ids"]),
                confidence=r["confidence"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
