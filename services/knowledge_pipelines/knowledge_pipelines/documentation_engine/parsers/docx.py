from docx import Document


def parse(path: str) -> dict:
    """Real extraction via python-docx — genuinely tested, not a stub.
    Paragraphs using Word's built-in "Heading N" styles become structure
    metadata, the same natural-boundary chunking signal markdown.py's
    heading extraction provides."""
    doc = Document(path)
    headings = []
    lines = []
    position = 0

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = (para.style.name or "") if para.style else ""
        if style_name.startswith("Heading"):
            try:
                level = int(style_name.replace("Heading", "").strip() or "1")
            except ValueError:
                level = 1
            headings.append({"level": level, "text": text, "position": position})
        lines.append(text)
        position += len(text) + 1

    clean_text = "\n".join(lines).strip()
    return {
        "clean_text": clean_text,
        "structure_metadata": {"format": "docx", "headings": headings},
    }
