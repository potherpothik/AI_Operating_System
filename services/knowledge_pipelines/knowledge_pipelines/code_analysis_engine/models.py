import uuid
import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON

from knowledge_pipelines.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class CodeSymbol(Base):
    """
    Structural tier only — signature, docstring, location. The actual
    function/class body is never stored here; raw_source_gate.py reads it
    live from the repo file, on an approved request, so there is never a
    second confidential copy sitting in a queryable table (Phase 11 doc:
    "NOT auto-ingested anywhere").
    """

    __tablename__ = "code_symbol"

    id = Column(String, primary_key=True, default=_uuid)
    repo = Column(String, nullable=False)
    file_path = Column(String, nullable=False)  # relative to repo root
    symbol_type = Column(String, nullable=False)  # function | class | module
    name = Column(String, nullable=False)
    qualified_name = Column(String, nullable=False)  # module.Class.method — unique enough for intra-repo call resolution
    signature = Column(Text, nullable=True)
    docstring = Column(Text, nullable=True)
    line_number = Column(Integer, nullable=True)
    classification = Column(String, default="internal")
    last_analyzed_commit = Column(String, nullable=True)


class CallEdge(Base):
    """
    Intra-file call resolution only in this first version (Phase 11 doc,
    Section 0: "call-graph accuracy across a real codebase is genuinely
    hard to get fully right... keeps it tractable") — a call from one
    file to a symbol defined in another file is not currently recorded.
    Honestly scoped, not silently approximated.
    """

    __tablename__ = "call_edge"

    id = Column(String, primary_key=True, default=_uuid)
    caller_symbol_id = Column(String, nullable=False)
    callee_symbol_id = Column(String, nullable=False)
    repo = Column(String, nullable=False)
    last_seen_commit = Column(String, nullable=True)


class RawSourceRequest(Base):
    __tablename__ = "raw_source_request"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=False)
    requesting_capability = Column(String, nullable=False)
    repo = Column(String, nullable=False)
    files = Column(JSON, nullable=False)  # list[str], relative paths
    reason = Column(Text, nullable=False)
    target_model = Column(String, nullable=False)  # re-verified against Context Builder's ceiling at fetch time, not just at request time
    approval_id = Column(String, nullable=True)  # governance's own approval request id
    status = Column(String, default="pending")  # pending | approved | rejected | fulfilled | expired | denied
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)


class AnalysisRun(Base):
    __tablename__ = "analysis_run"

    id = Column(String, primary_key=True, default=_uuid)
    repo = Column(String, nullable=False)
    mode = Column(String, nullable=False)  # full_scan | incremental
    trigger = Column(String, default="manual")  # manual | git_manager_commit
    files_analyzed = Column(Integer, default=0)
    files_failed = Column(Integer, default=0)
    failures = Column(JSON, default=list)  # [{file_path, reason}] — a visible gap, not a silent skip
    symbols_extracted = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
