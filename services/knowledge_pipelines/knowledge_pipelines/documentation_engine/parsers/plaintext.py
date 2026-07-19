from pathlib import Path


def parse(path: str) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    return {
        "clean_text": raw.strip(),
        "structure_metadata": {"format": "plaintext", "headings": []},
    }
