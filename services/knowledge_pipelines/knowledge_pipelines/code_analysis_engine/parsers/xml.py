def parse(path: str) -> dict:
    """
    Not implemented in this phase — Odoo XML views need domain-specific
    structural extraction (view inheritance, field references) beyond
    generic XML parsing to be genuinely useful, which is real, separate
    work. Named as an extension point in the Phase 11 doc, not built
    here so this phase's attention stays on Python.
    """
    raise NotImplementedError("Odoo XML view parsing is not implemented — see services/knowledge_pipelines/README.md")
