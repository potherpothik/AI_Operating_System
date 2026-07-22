import httpx
import pytest

from knowledge_pipelines.db import SessionLocal
from knowledge_pipelines.code_analysis_engine import api, raw_source_gate, store


@pytest.fixture
def sample_repo(tmp_path):
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
        '    """A widget for the confidential source test."""\n'
        "\n"
        "    def render(self, x):\n"
        '        """Render the widget."""\n'
        "        y = helper(x)\n"
        "        return self.finalize(y)\n"
        "\n"
        "    def finalize(self, y):\n"
        "        return y\n"
    )
    return tmp_path


def test_full_scan_persists_real_symbols_and_edges(sample_repo, governance_url, knowledge_url):
    db = SessionLocal()
    result = api.scan(api.ScanRequest(repo=str(sample_repo), mode="full_scan", trigger="human_admin"), db)
    db.close()

    assert result["files_analyzed"] == 1
    assert result["files_failed"] == 0
    assert result["symbols_extracted"] == 4  # Widget (class), render, finalize, helper


def test_full_scan_content_is_genuinely_queryable_in_vector_search(sample_repo, governance_url, knowledge_url):
    db = SessionLocal()
    api.scan(api.ScanRequest(repo=str(sample_repo), mode="full_scan", trigger="human_admin", project_id="proj-cae-1"), db)
    db.close()

    hits = httpx.post(
        f"{knowledge_url}/vector/query",
        json={"text": "widget render finalize helper", "namespace": "proj-cae-1", "classification_ceiling": "confidential", "top_k": 5},
    ).json()["hits"]
    assert any("Widget" in h["chunk"] or "helper" in h["chunk"] for h in hits)


def test_scan_incremental_only_touches_the_given_files(sample_repo, governance_url, knowledge_url):
    (sample_repo / "other.py").write_text("def other_func():\n    return 42\n")
    db = SessionLocal()
    api.scan(api.ScanRequest(repo=str(sample_repo), mode="full_scan", trigger="human_admin"), db)

    # re-analyze only widgets.py incrementally
    result = api.scan(api.ScanRequest(repo=str(sample_repo), mode="incremental", files=["widgets.py"], trigger="git_manager"), db)
    symbols = store.get_symbols_for_repo(db, str(sample_repo))
    db.close()

    assert result["files_analyzed"] == 1
    names = {s.name for s in symbols}
    assert "other_func" in names  # untouched by the incremental run, still present from the earlier full_scan
    assert "helper" in names


def test_scan_incremental_without_files_is_rejected():
    db = SessionLocal()
    with pytest.raises(Exception):
        api.scan(api.ScanRequest(repo="/tmp/whatever", mode="incremental", files=None, trigger="human_admin"), db)
    db.close()


def test_get_symbol_returns_structural_tier_never_the_body(sample_repo, governance_url, knowledge_url):
    db = SessionLocal()
    api.scan(api.ScanRequest(repo=str(sample_repo), mode="full_scan", trigger="human_admin"), db)
    symbols = store.get_symbols_for_repo(db, str(sample_repo))
    render_symbol = next(s for s in symbols if s.name == "render")

    result = api.get_symbol(render_symbol.qualified_name, str(sample_repo), db)
    db.close()

    assert result["signature"] == "def render(self, x)"
    assert result["docstring"] == "Render the widget."
    assert result["classification"] == "internal"
    assert "return self.finalize(y)" not in str(result)  # the real function BODY, never present in the structural tier
    assert result["callees"]  # render() calls helper() and finalize()


def test_get_graph_shows_real_intra_file_call_edges(sample_repo, governance_url, knowledge_url):
    db = SessionLocal()
    api.scan(api.ScanRequest(repo=str(sample_repo), mode="full_scan", trigger="human_admin"), db)
    result = api.get_graph(str(sample_repo), db)
    db.close()

    assert "widgets.Widget.render" in result["nodes"]
    assert {"from": "widgets.Widget.render", "to": "widgets.helper"} in result["edges"]
    assert {"from": "widgets.Widget.render", "to": "widgets.Widget.finalize"} in result["edges"]


def test_raw_source_request_denied_for_capability_without_a_role(sample_repo, governance_url):
    db = SessionLocal()
    with pytest.raises(raw_source_gate.RequestDenied):
        raw_source_gate.request_raw_source(
            db, task_id="task-1", requesting_capability="nonexistent_capability_with_no_policy_role",
            repo=str(sample_repo), files=["widgets.py"], reason="testing", target_model="qwen-coder",
        )
    db.close()


def test_raw_source_full_round_trip_returns_real_file_content(sample_repo, governance_url, assembly_url):
    """
    The whole point of Phase 11's structural/raw-source split, proven
    end to end: request -> real governance approval -> fetch -> the
    EXACT bytes on disk come back, verified against the real file
    content directly, not a canned string.
    """
    db = SessionLocal()
    real_content = (sample_repo / "widgets.py").read_text()

    result = raw_source_gate.request_raw_source(
        db, task_id="task-raw-1", requesting_capability="django_agent",
        repo=str(sample_repo), files=["widgets.py"], reason="need real implementation detail", target_model="qwen3.5:4b",
    )
    assert result["status"] == "pending_approval"

    # Not yet approved — fetch must refuse to release anything.
    pending = raw_source_gate.fetch_raw_source(db, result["request_id"])
    assert pending["status"] == "pending"

    httpx.post(f"{governance_url}/approval/{result['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})

    fetched = raw_source_gate.fetch_raw_source(db, result["request_id"])
    db.close()

    assert fetched["status"] == "fulfilled"
    assert fetched["files"]["widgets.py"] == real_content
    assert fetched["classification"] == "confidential"


def test_raw_source_fetch_refuses_a_non_local_target_model_even_when_approved(sample_repo, governance_url, assembly_url):
    """
    The genuinely new safety property (Phase 11 doc, Section 1: Security)
    — a human approving the REQUEST is not the same as clearing release
    to an external model. Re-verified fresh at fetch time regardless of
    what target_model claimed when the request was filed.
    """
    db = SessionLocal()
    result = raw_source_gate.request_raw_source(
        db, task_id="task-raw-2", requesting_capability="django_agent",
        repo=str(sample_repo), files=["widgets.py"], reason="testing external model refusal",
        target_model="gpt-4-some-external-api",
    )
    httpx.post(f"{governance_url}/approval/{result['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})

    with pytest.raises(raw_source_gate.ModelNotLocal):
        raw_source_gate.fetch_raw_source(db, result["request_id"])
    db.close()


def test_raw_source_fetch_of_unknown_request_id_raises_not_found(governance_url):
    db = SessionLocal()
    with pytest.raises(store.NotFound):
        raw_source_gate.fetch_raw_source(db, "nonexistent-request-id")
    db.close()


def test_raw_source_request_never_logs_the_actual_file_content(sample_repo, governance_url, assembly_url):
    """Every request is logged in full (files, agent, reason) per the
    Phase 11 doc's Logging section — but 'in full' means the REQUEST
    metadata, never the confidential body itself, same discipline
    secrets.resolve applies to credential values."""
    db = SessionLocal()
    result = raw_source_gate.request_raw_source(
        db, task_id="task-raw-3", requesting_capability="django_agent",
        repo=str(sample_repo), files=["widgets.py"], reason="audit content check", target_model="qwen3.5:4b",
    )
    httpx.post(f"{governance_url}/approval/{result['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})
    raw_source_gate.fetch_raw_source(db, result["request_id"])
    db.close()

    events = httpx.get(f"{governance_url}/audit/query?action=code_analysis.raw_source_request.fetch").json()
    assert len(events) >= 1
    for event in events:
        assert "A widget for the confidential source test" not in str(event)
