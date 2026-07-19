def chunk_text(text: str, max_words: int = 200, overlap_words: int = 30) -> list[str]:
    """
    Simple word-count-bounded chunking with overlap, so retrieval returns
    focused spans rather than whole documents, and no single chunk crosses
    a hard boundary mid-thought without some shared context with its neighbor.
    """
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [text.strip()]

    chunks = []
    start = 0
    step = max(max_words - overlap_words, 1)
    while start < len(words):
        chunk_words = words[start : start + max_words]
        chunks.append(" ".join(chunk_words))
        if start + max_words >= len(words):
            break
        start += step
    return chunks
