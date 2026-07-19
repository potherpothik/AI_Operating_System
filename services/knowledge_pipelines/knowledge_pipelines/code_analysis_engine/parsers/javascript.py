def parse(path: str) -> dict:
    """
    Not implemented in this phase. JS/TS needs a real JS-aware parser
    (no equivalent of Python's built-in `ast` module ships with the
    interpreter) — extensibility point named explicitly in the Phase 11
    doc ("extensible to JS/TS and Odoo XML views"), not built here so
    this phase's attention stays on getting the structural/raw-source
    split right for the one language actually needed (Python).
    """
    raise NotImplementedError("JavaScript/TypeScript parsing is not implemented — see services/knowledge_pipelines/README.md")
