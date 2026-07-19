import re
from pathlib import Path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_EMPHASIS_RE = re.compile(r"(\*\*\*|\*\*|\*|___|__|_)(.+?)\1")
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")


def parse(path: str) -> dict:
    """
    Real markdown structure extraction — no external dependency needed,
    since what Documentation Engine actually needs is heading hierarchy
    (for Vector Search to chunk along natural boundaries, per the Phase 9
    doc) plus clean prose, not full markdown-to-HTML rendering.
    """
    raw = Path(path).read_text(encoding="utf-8")

    headings = []
    for match in _HEADING_RE.finditer(raw):
        level = len(match.group(1))
        text = match.group(2).strip()
        headings.append({"level": level, "text": text, "position": match.start()})

    clean_text = _HEADING_RE.sub(lambda m: m.group(2).strip(), raw)
    clean_text = _LINK_RE.sub(lambda m: m.group(1) or m.group(2), clean_text)
    clean_text = _EMPHASIS_RE.sub(lambda m: m.group(2), clean_text)
    clean_text = _INLINE_CODE_RE.sub(lambda m: m.group(1), clean_text)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()

    return {
        "clean_text": clean_text,
        "structure_metadata": {"format": "markdown", "headings": headings},
    }
