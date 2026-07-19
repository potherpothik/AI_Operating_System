import datetime
from sqlalchemy.orm import Session

from knowledge_pipelines.code_analysis_engine.models import CodeSymbol, CallEdge, RawSourceRequest, AnalysisRun


class NotFound(Exception):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def create_analysis_run(db: Session, repo: str, mode: str, trigger: str = "manual") -> AnalysisRun:
    run = AnalysisRun(repo=repo, mode=mode, trigger=trigger)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finalize_analysis_run(db: Session, run: AnalysisRun, files_analyzed: int, files_failed: int, failures: list, symbols_extracted: int) -> AnalysisRun:
    run.files_analyzed = files_analyzed
    run.files_failed = files_failed
    run.failures = failures
    run.symbols_extracted = symbols_extracted
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run


def replace_symbols_for_files(db: Session, repo: str, file_paths: list[str], symbol_dicts: list[dict], commit_ref: str = None) -> list[CodeSymbol]:
    """
    Re-analysis of a file supersedes its prior symbols entirely — a
    deleted function shouldn't linger as a stale row forever. Scoped to
    exactly the files being (re-)analyzed, so an incremental scan never
    touches symbols from files it didn't look at.
    """
    if file_paths:
        db.query(CodeSymbol).filter(CodeSymbol.repo == repo, CodeSymbol.file_path.in_(file_paths)).delete(synchronize_session=False)

    rows = []
    for sym in symbol_dicts:
        row = CodeSymbol(
            repo=repo, file_path=sym["file_path"], symbol_type=sym["symbol_type"], name=sym["name"],
            qualified_name=sym["qualified_name"], signature=sym["signature"], docstring=sym["docstring"],
            line_number=sym["line_number"], classification=sym["classification"], last_analyzed_commit=commit_ref,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def replace_call_edges_for_files(db: Session, repo: str, file_paths: list[str], edges: list[dict], commit_ref: str = None) -> list[CallEdge]:
    """
    Edges are intra-file only (call_graph.py), so deleting and
    recreating edges scoped to the same file set as the symbols they
    reference is always correct here — there's no cross-file edge that
    could be orphaned by this.
    """
    if file_paths:
        symbol_ids_in_files = [
            r.id for r in db.query(CodeSymbol.id).filter(CodeSymbol.repo == repo, CodeSymbol.file_path.in_(file_paths)).all()
        ]
        if symbol_ids_in_files:
            db.query(CallEdge).filter(CallEdge.repo == repo, CallEdge.caller_symbol_id.in_(symbol_ids_in_files)).delete(synchronize_session=False)

    rows = []
    for edge in edges:
        row = CallEdge(repo=repo, caller_symbol_id=edge["caller_symbol_id"], callee_symbol_id=edge["callee_symbol_id"], last_seen_commit=commit_ref)
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


def get_symbols_for_repo(db: Session, repo: str) -> list[CodeSymbol]:
    return db.query(CodeSymbol).filter(CodeSymbol.repo == repo).order_by(CodeSymbol.file_path.asc(), CodeSymbol.line_number.asc()).all()


def get_symbol(db: Session, symbol_id: str) -> CodeSymbol | None:
    return db.query(CodeSymbol).filter(CodeSymbol.id == symbol_id).first()


def get_symbol_by_ref(db: Session, repo: str, ref: str) -> CodeSymbol | None:
    """`ref` matches either the id or the qualified_name — the API's
    GET /code-analysis/symbol/{ref} accepts either, since a human caller
    knows the name but a graph query result only has ids."""
    return (
        db.query(CodeSymbol)
        .filter(CodeSymbol.repo == repo, (CodeSymbol.id == ref) | (CodeSymbol.qualified_name == ref))
        .first()
    )


def get_edges_for_repo(db: Session, repo: str) -> list[CallEdge]:
    return db.query(CallEdge).filter(CallEdge.repo == repo).all()


def create_raw_source_request(db: Session, task_id: str, requesting_capability: str, repo: str, files: list[str], reason: str, target_model: str, approval_id: str) -> RawSourceRequest:
    req = RawSourceRequest(
        task_id=task_id, requesting_capability=requesting_capability, repo=repo, files=files,
        reason=reason, target_model=target_model, approval_id=approval_id, status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def get_raw_source_request(db: Session, request_id: str) -> RawSourceRequest | None:
    return db.query(RawSourceRequest).filter(RawSourceRequest.id == request_id).first()


def mark_fulfilled(db: Session, req: RawSourceRequest) -> RawSourceRequest:
    req.status = "fulfilled"
    req.fulfilled_at = _now()
    db.commit()
    db.refresh(req)
    return req


def mark_denied(db: Session, req: RawSourceRequest) -> RawSourceRequest:
    req.status = "denied"
    db.commit()
    db.refresh(req)
    return req
