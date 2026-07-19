import math
from knowledge.vector_search.embedding import HashingEmbedding
from knowledge.vector_search.index import _cosine_similarity


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
