from pathlib import Path

from knowledge_pipelines.code_analysis_engine.parsers import python, javascript, xml


class UnsupportedFormat(Exception):
    pass


class ParseFailed(Exception):
    pass


_BY_EXTENSION = {
    ".py": python,
    ".js": javascript, ".ts": javascript, ".jsx": javascript, ".tsx": javascript,
    ".xml": xml,
}


def parser_for(file_path: str):
    ext = Path(file_path).suffix.lower()
    module = _BY_EXTENSION.get(ext)
    if not module:
        raise UnsupportedFormat(f"no parser registered for extension {ext!r}")
    return module


def parse(file_path: str) -> dict:
    """
    A parse failure on one file is an explicit, attributable ParseFailed
    — never a silent skip — matching Documentation Engine's own ingestion
    philosophy (Phase 9). symbol_extractor.py catches this per-file and
    keeps scanning the rest of the repo, per the Phase 11 doc's failure
    handling: one bad file degrades the run, not the whole scan.
    """
    module = parser_for(file_path)
    try:
        return module.parse(file_path)
    except UnsupportedFormat:
        raise
    except NotImplementedError as e:
        raise UnsupportedFormat(str(e))
    except Exception as e:  # noqa: BLE001
        raise ParseFailed(f"{file_path}: {e}")
