import math
import pytest
from knowledge.vector_search.embedding import HashingEmbedding
from knowledge.vector_search.index import _cosine_similarity, EmbeddingDimensionMismatch


def test_embedding_is_deterministic():
    model = HashingEmbedding(dim=128)
    v1 = model.embed("the sale order model tracks order state")
    v2 = model.embed("the sale order model tracks order state")
    assert v1 == v2


def test_embedding_is_unit_normalized():
    model = HashingEmbedding(dim=128)
    v = model.embed("some reasonably long piece of text with several words in it")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-9


def test_empty_text_produces_zero_vector_not_an_error():
    model = HashingEmbedding(dim=64)
    v = model.embed("")
    assert v == [0.0] * 64


def test_overlapping_text_scores_higher_than_unrelated_text():
    model = HashingEmbedding(dim=256)
    query = model.embed("explain the sale order state field")
    related = model.embed("the sale order state field tracks order lifecycle")
    unrelated = model.embed("cutlist optimization uses bin packing for panel widths")

    score_related = _cosine_similarity(query, related)
    score_unrelated = _cosine_similarity(query, unrelated)
    assert score_related > score_unrelated


def test_different_dims_are_independent_models():
    m1 = HashingEmbedding(dim=64)
    m2 = HashingEmbedding(dim=256)
    assert len(m1.embed("x")) == 64
    assert len(m2.embed("x")) == 256


def test_mismatched_dims_raise_instead_of_silently_truncating():
    """
    Phase 25: a real bug found by live-testing an EMBEDDING_BACKEND
    switch (hashing, dim=512) against a corpus indexed with the OTHER
    backend (Ollama nomic-embed-text, dim=768). Python's own zip()
    silently truncates to the shorter vector rather than erroring —
    before this fix, that produced a real number that looked like a
    valid cosine similarity but was meaningless, and live-confirmed it
    even inverted a real ranking (the irrelevant document scored above
    the relevant one). Locks in the fix: a dimension mismatch must raise,
    never silently degrade.
    """
    m64 = HashingEmbedding(dim=64)
    m128 = HashingEmbedding(dim=128)
    with pytest.raises(EmbeddingDimensionMismatch):
        _cosine_similarity(m64.embed("some text"), m128.embed("some other text"))
