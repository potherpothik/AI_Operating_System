from pathlib import Path

from knowledge_pipelines.documentation_engine.parsers import markdown, plaintext, pdf, docx, openapi


class UnsupportedFormat(Exception):
    pass


class ParseFailed(Exception):
    pass


_BY_EXTENSION = {
    ".md": markdown, ".markdown": markdown,
    ".txt": plaintext,
    ".pdf": pdf,
    ".docx": docx,
    ".yaml": openapi, ".yml": openapi, ".json": openapi,
}


def parser_for(path_or_url: str, doc_type: str = None):
    """
    Format-aware dispatch by extension — doc_type can override when a
    source's real format doesn't match its extension (Phase 9 doc:
    "each with its own extraction path to clean text").
    """
    if doc_type == "openapi":
        return openapi
    ext = Path(path_or_url).suffix.lower()
    module = _BY_EXTENSION.get(ext)
    if not module:
        raise UnsupportedFormat(f"no parser registered for extension {ext!r}")
    return module


def parse(path_or_url: str, doc_type: str = None) -> dict:
    """
    Unparseable documents surface as an explicit ParseFailed, never a
    silent skip (Phase 9 doc, Documentation Engine failure handling —
    same philosophy Vector Search already applies in Phase 3).
    """
    module = parser_for(path_or_url, doc_type)
    try:
        return module.parse(path_or_url)
    except UnsupportedFormat:
        raise
    except Exception as e:  # noqa: BLE001 — any parser-internal failure becomes an explicit, attributable failure
        raise ParseFailed(f"{path_or_url}: {e}")
