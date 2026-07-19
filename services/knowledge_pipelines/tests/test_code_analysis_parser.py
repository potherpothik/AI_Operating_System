import pytest

from knowledge_pipelines.code_analysis_engine import parsers, symbol_extractor, call_graph, classifier


@pytest.fixture
def sample_repo(tmp_path):
    """A real, disposable directory with genuine cross-referencing Python
    source — not a mock AST, actual files an actual parser reads."""
    (tmp_path / "widgets.py").write_text(
        '"""Widget module."""\n'
        "\n"
        "\n"
        "def helper(x):\n"
        '    """Doubles x."""\n'
        "    return x * 2\n"
        "\n"
        "\n"
        "class Widget:\n"
        '    """A widget."""\n'
        "\n"
        "    def render(self, x):\n"
        '        """Render the widget."""\n'
        "        y = helper(x)\n"
        "        return self.finalize(y)\n"
        "\n"
        "    def finalize(self, y):\n"
        "        return y\n"
    )
    (tmp_path / "broken.py").write_text("def broken(:\n    pass\n")  # genuine syntax error
    (tmp_path / "notes.md").write_text("# not python\n")  # unsupported extension, should be skipped not failed
    return tmp_path


def test_python_parser_extracts_real_signatures_and_docstrings(sample_repo):
    result = parsers.parse(str(sample_repo / "widgets.py"))
    assert result["module_docstring"] == "Widget module."
    by_name = {s["name"]: s for s in result["symbols"]}
    assert by_name["helper"]["signature"] == "def helper(x)"
    assert by_name["helper"]["docstring"] == "Doubles x."
    assert by_name["Widget"]["symbol_type"] == "class"
    assert by_name["render"]["qualified_name"] == "Widget.render"
    assert "helper" in by_name["render"]["calls"]
    assert "finalize" in by_name["render"]["calls"]


def test_python_parser_raises_parse_failed_on_real_syntax_error(sample_repo):
    with pytest.raises(parsers.ParseFailed):
        parsers.parse(str(sample_repo / "broken.py"))


def test_discover_files_finds_py_files_only(sample_repo):
    files = symbol_extractor.discover_files(str(sample_repo))
    assert "widgets.py" in files
    assert "broken.py" in files
    assert "notes.md" not in files


def test_extract_from_repo_records_failure_without_aborting_the_run(sample_repo):
    files = symbol_extractor.discover_files(str(sample_repo))
    result = symbol_extractor.extract_from_repo(str(sample_repo), files)

    assert len(result["failures"]) == 1
    assert result["failures"][0]["file_path"] == "broken.py"
    # widgets.py still got analyzed despite broken.py failing
    names = {s["name"] for s in result["symbols"]}
    assert "helper" in names
    assert "Widget" in names


def test_extract_from_repo_prefixes_qualified_names_with_module(sample_repo):
    files = ["widgets.py"]
    result = symbol_extractor.extract_from_repo(str(sample_repo), files)
    qualified = {s["qualified_name"] for s in result["symbols"]}
    assert "widgets.helper" in qualified
    assert "widgets.Widget.render" in qualified


def test_extract_from_repo_defaults_structural_classification(sample_repo):
    result = symbol_extractor.extract_from_repo(str(sample_repo), ["widgets.py"])
    assert all(s["classification"] == classifier.STRUCTURAL_CLASSIFICATION for s in result["symbols"])


def test_call_graph_resolves_intra_file_edges_by_real_name_match():
    symbols_by_file = {
        "widgets.py": [
            {"id": "sym-render", "name": "render"},
            {"id": "sym-finalize", "name": "finalize"},
            {"id": "sym-helper", "name": "helper"},
        ]
    }
    calls_by_symbol_id = {"sym-render": ["helper", "finalize"], "sym-finalize": [], "sym-helper": []}

    edges = call_graph.resolve_edges(symbols_by_file, calls_by_symbol_id)
    pairs = {(e["caller_symbol_id"], e["callee_symbol_id"]) for e in edges}
    assert ("sym-render", "sym-helper") in pairs
    assert ("sym-render", "sym-finalize") in pairs
    assert len(edges) == 2


def test_call_graph_does_not_resolve_calls_across_files():
    symbols_by_file = {
        "a.py": [{"id": "sym-a", "name": "shared_name"}],
        "b.py": [{"id": "sym-b-caller", "name": "caller"}],
    }
    calls_by_symbol_id = {"sym-a": [], "sym-b-caller": ["shared_name"]}
    edges = call_graph.resolve_edges(symbols_by_file, calls_by_symbol_id)
    assert edges == []  # shared_name is defined in a.py, called from b.py — out of scope by design


def test_call_graph_full_graph_uses_qualified_names_as_nodes():
    symbols = [{"id": "s1", "qualified_name": "widgets.helper"}, {"id": "s2", "qualified_name": "widgets.Widget.render"}]
    edges = [{"caller_symbol_id": "s2", "callee_symbol_id": "s1"}]
    graph = call_graph.full_graph(symbols, edges)
    assert set(graph["nodes"]) == {"widgets.helper", "widgets.Widget.render"}
    assert graph["edges"] == [{"from": "widgets.Widget.render", "to": "widgets.helper"}]


def test_classifier_tier_index_orders_confidential_above_internal():
    assert classifier.tier_index(classifier.RAW_SOURCE_CLASSIFICATION) > classifier.tier_index(classifier.STRUCTURAL_CLASSIFICATION)
    assert classifier.tier_index("public") < classifier.tier_index(classifier.STRUCTURAL_CLASSIFICATION)
