"""
Word-count-based budgeting, not exact token counting. A real tokenizer
(tiktoken, a model's own SentencePiece vocab, etc.) needs vocabulary/merge
files that would have to be downloaded — the same network constraint that
shaped the embedding model choice in Phase 3. Word count is a reasonable,
honest approximation (roughly 0.75 tokens per word for English is a common
rule of thumb) — swap in a real tokenizer here once one is reachable in
your actual environment; nothing else in Context Builder's contract
changes if you do.
"""


def word_count(text: str) -> int:
    return len(text.split())


def fit_to_budget(candidates: list[dict], budget_words: int) -> tuple[list[dict], int, bool]:
    """
    candidates: list of {"text": str, "score": float, ...} already sorted
    highest-priority first by the caller (retriever.py). Greedily includes
    items until the budget would be exceeded; anything left out makes the
    package explicitly partial rather than silently dropped.
    """
    included = []
    used = 0
    truncated = False

    for item in candidates:
        cost = word_count(item["text"])
        if used + cost > budget_words:
            truncated = True
            continue
        included.append(item)
        used += cost

    return included, used, truncated
