from assembly.context_builder.budget import word_count, fit_to_budget


def test_word_count():
    assert word_count("one two three") == 3
    assert word_count("") == 0


def test_fit_to_budget_includes_everything_when_under_budget():
    candidates = [{"text": "five word chunk of text"}, {"text": "another chunk"}]
    included, used, truncated = fit_to_budget(candidates, budget_words=100)
    assert len(included) == 2
    assert truncated is False
    assert used == 7


def test_fit_to_budget_stops_and_marks_partial_when_over():
    candidates = [{"text": " ".join(["word"] * 60)}, {"text": " ".join(["word"] * 60)}]
    included, used, truncated = fit_to_budget(candidates, budget_words=100)
    assert len(included) == 1
    assert used == 60
    assert truncated is True


def test_fit_to_budget_respects_priority_order():
    """Caller is expected to pre-sort highest priority first — verify that order is honored, not re-sorted."""
    candidates = [{"text": "high priority item"}, {"text": " ".join(["filler"] * 100)}, {"text": "low priority item"}]
    included, used, truncated = fit_to_budget(candidates, budget_words=10)
    included_texts = [c["text"] for c in included]
    assert "high priority item" in included_texts
    assert truncated is True
