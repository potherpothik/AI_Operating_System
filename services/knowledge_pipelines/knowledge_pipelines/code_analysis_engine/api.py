from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from knowledge_pipelines.db import get_db
from knowledge_pipelines import clients
from knowledge_pipelines.code_analysis_engine import store, symbol_extractor, call_graph, classifier, raw_source_gate

router = APIRouter(prefix="/code-analysis", tags=["code-analysis"])


def _symbol_prose(sym: dict) -> str:
    """Chunked prose for Vector Search's semantic retrieval — same
    reasoning as erp_knowledge_engine's _table_prose: a plain-language
    description a similarity search can actually match against, never
    the function/class BODY itself (that's the confidential tier)."""
    doc = f" — {sym['docstring']}" if sym.get("docstring") else ""
    return f"{sym['symbol_type'].capitalize()} `{sym['qualified_name']}` in {sym['file_path']}: {sym['signature']}{doc}"


def _run_out(run) -> dict:
    return {
        "run_id": run.id, "repo": run.repo, "mode": run.mode, "trigger": run.trigger,
        "files_analyzed": run.files_analyzed, "files_failed": run.files_failed, "failures": run.failures,
        "symbols_extracted": run.symbols_extracted,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _symbol_out(sym) -> dict:
    return {
        "id": sym.id, "repo": sym.repo, "file_path": sym.file_path, "symbol_type": sym.symbol_type,
        "name": sym.name, "qualified_name": sym.qualified_name, "signature": sym.signature,
        "docstring": sym.docstring, "line_number": sym.line_number, "classification": sym.classification,
        "last_analyzed_commit": sym.last_analyzed_commit,
    }


class ScanRequest(BaseModel):
    repo: str  # local path — same "real working_dir on disk" convention as Phase 6/7's PROPOSAL_REPO_PATH
    mode: str = "full_scan"  # full_scan | incremental
    files: Optional[list[str]] = None  # required for incremental — the caller (e.g. Git Manager) already knows what changed
    commit_ref: Optional[str] = None
    trigger: str = "manual"
    project_id: Optional[str] = None


@router.post("/scan")
def scan(req: ScanRequest, db: Session = Depends(get_db)):
    if req.mode == "incremental" and not req.files:
        raise HTTPException(status_code=400, detail="mode=incremental requires a non-empty files list")

    decision = clients.authorize(req.trigger, "code_analysis.scan", req.repo)
    if decision["decision"] == "deny":
        clients.audit_log(req.trigger, "code_analysis.scan", req.repo, decision="deny", reason=decision.get("reason", ""))
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied"))

    files = req.files if req.mode == "incremental" else symbol_extractor.discover_files(req.repo)
    run = store.create_analysis_run(db, req.repo, req.mode, req.trigger)

    extracted = symbol_extractor.extract_from_repo(req.repo, files)
    raw_symbols = extracted["symbols"]
    failures = extracted["failures"]

    stored_symbols = store.replace_symbols_for_files(db, req.repo, files, raw_symbols, req.commit_ref)

    # Map each stored (now id-bearing) symbol back to its raw _calls list,
    # grouped by file, so call_graph.py can resolve intra-file edges
    # against real symbol ids rather than the transient dicts extraction produced.
    symbols_by_file: dict[str, list[dict]] = {}
    calls_by_symbol_id: dict[str, list[str]] = {}
    for stored, raw in zip(stored_symbols, raw_symbols):
        symbols_by_file.setdefault(stored.file_path, []).append({"id": stored.id, "name": stored.name})
        calls_by_symbol_id[stored.id] = raw["_calls"]

    edges = call_graph.resolve_edges(symbols_by_file, calls_by_symbol_id)
    store.replace_call_edges_for_files(db, req.repo, files, edges, req.commit_ref)

    project_id = req.project_id or req.repo
    for sym in stored_symbols:
        clients.vector_ingest(
            source=f"code_symbol:{req.repo}:{sym.qualified_name}", content=_symbol_prose(_symbol_out(sym)),
            project_id=project_id, doc_type="code_symbol", classification=sym.classification,
        )

    run = store.finalize_analysis_run(db, run, files_analyzed=len(files) - len(failures), files_failed=len(failures), failures=failures, symbols_extracted=len(stored_symbols))
    clients.audit_log(
        req.trigger, "code_analysis.scan", req.repo, decision="completed",
        reason=f"mode={req.mode}, files={len(files)}, failed={len(failures)}, symbols={len(stored_symbols)}",
    )
    return _run_out(run)


@router.get("/symbol/{ref}")
def get_symbol(ref: str, repo: str, db: Session = Depends(get_db)):
    """The safe, non-confidential default tier (Phase 11 doc): signature,
    docstring, callers/callees — never the function/class body."""
    sym = store.get_symbol_by_ref(db, repo, ref)
    if not sym:
        raise HTTPException(status_code=404, detail=f"no symbol {ref!r} found for repo {repo!r}")

    edges = store.get_edges_for_repo(db, repo)
    out = _symbol_out(sym)
    out["callers"] = call_graph.callers_of(sym.id, [{"caller_symbol_id": e.caller_symbol_id, "callee_symbol_id": e.callee_symbol_id} for e in edges])
    out["callees"] = call_graph.callees_of(sym.id, [{"caller_symbol_id": e.caller_symbol_id, "callee_symbol_id": e.callee_symbol_id} for e in edges])
    return out


@router.get("/graph")
def get_graph(repo: str, db: Session = Depends(get_db)):
    symbols = [_symbol_out(s) for s in store.get_symbols_for_repo(db, repo)]
    edges = [{"caller_symbol_id": e.caller_symbol_id, "callee_symbol_id": e.callee_symbol_id} for e in store.get_edges_for_repo(db, repo)]
    return call_graph.full_graph(symbols, edges)


class RawSourceRequestBody(BaseModel):
    task_id: str
    requesting_capability: str
    repo: str
    files: list[str]
    reason: str
    target_model: str


@router.post("/raw-source-request")
def raw_source_request(req: RawSourceRequestBody, db: Session = Depends(get_db)):
    try:
        result = raw_source_gate.request_raw_source(db, req.task_id, req.requesting_capability, req.repo, req.files, req.reason, req.target_model)
    except raw_source_gate.RequestDenied as e:
        raise HTTPException(status_code=403, detail=str(e))
    return result


@router.post("/raw-source-request/{request_id}/fetch")
def fetch_raw_source(request_id: str, db: Session = Depends(get_db)):
    """
    The actual release step — only reachable once governance's approval
    is genuinely `approved`, re-checked live here, and only if
    target_model still resolves to a local model at THIS moment, not
    whatever was true when the request was filed.
    """
    try:
        result = raw_source_gate.fetch_raw_source(db, request_id)
    except store.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except raw_source_gate.ModelNotLocal as e:
        raise HTTPException(status_code=403, detail=str(e))
    return result
