import json
from pathlib import Path
import yaml


def parse(path: str) -> dict:
    """
    Real OpenAPI spec parsing (YAML or JSON) — extracts each path/method
    as a natural section boundary, with the operation's summary/
    description as the readable prose Vector Search actually indexes,
    rather than raw JSON/YAML which embeds poorly as chunked text.
    """
    raw = Path(path).read_text(encoding="utf-8")
    if path.endswith(".json"):
        spec = json.loads(raw)
    else:
        spec = yaml.safe_load(raw)

    title = (spec.get("info", {}) or {}).get("title", "API")
    version = (spec.get("info", {}) or {}).get("version", "")
    lines = [f"{title} (version {version})".strip()]
    headings = [{"level": 1, "text": title, "position": 0}]

    for route, methods in (spec.get("paths", {}) or {}).items():
        for method, operation in (methods or {}).items():
            if not isinstance(operation, dict):
                continue
            summary = operation.get("summary", "")
            description = operation.get("description", "")
            heading_text = f"{method.upper()} {route}"
            headings.append({"level": 2, "text": heading_text, "position": len("\n".join(lines)) + 1})
            lines.append(f"{heading_text}: {summary}".strip(": "))
            if description:
                lines.append(description)

    return {
        "clean_text": "\n".join(lines).strip(),
        "structure_metadata": {"format": "openapi", "headings": headings, "title": title, "version": version},
    }
