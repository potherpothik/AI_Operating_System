from pathlib import Path

from knowledge_pipelines.code_analysis_engine import parsers, classifier


def _module_name(repo_root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(repo_root).with_suffix("")
    return ".".join(rel.parts)


def discover_files(repo_path: str) -> list[str]:
    """
    All analyzable files under repo_path, relative to it — the default
    file set for a full_scan. `.git` is skipped since it's never source,
    just repository metadata.
    """
    root = Path(repo_path)
    files = []
    for path in sorted(root.rglob("*.py")):
        if ".git" in path.parts:
            continue
        files.append(str(path.relative_to(root)))
    return files


def extract_from_repo(repo_path: str, files: list[str]) -> dict:
    """
    Parses each given file (relative to repo_path) via the pluggable
    parsers dispatch, producing one dict per structural symbol found —
    not yet persisted; store.py turns these into real CodeSymbol rows so
    call_graph.py can resolve edges against real symbol ids. A parse
    failure on one file is caught here and recorded, never allowed to
    abort the whole run (Phase 11 doc, failure handling) — the rest of
    the repo still gets analyzed.
    """
    root = Path(repo_path)
    symbols = []
    failures = []

    for rel_path in files:
        abs_path = root / rel_path
        try:
            parsed = parsers.parse(str(abs_path))
        except parsers.UnsupportedFormat:
            continue  # not a failure — just nothing this phase knows how to parse
        except parsers.ParseFailed as e:
            failures.append({"file_path": rel_path, "reason": str(e)})
            continue

        module = _module_name(root, abs_path)
        for sym in parsed["symbols"]:
            qualified_name = f"{module}.{sym['qualified_name']}"
            symbols.append({
                "file_path": rel_path,
                "symbol_type": sym["symbol_type"],
                "name": sym["name"],
                "qualified_name": qualified_name,
                "signature": sym["signature"],
                "docstring": sym["docstring"],
                "line_number": sym["line_number"],
                "classification": classifier.STRUCTURAL_CLASSIFICATION,
                "_calls": sym["calls"],  # consumed by call_graph.py, not persisted on CodeSymbol itself
            })

    return {"symbols": symbols, "failures": failures}
