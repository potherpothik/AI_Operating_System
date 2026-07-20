import json
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "execution" / "shell_executor" / "scripts"


def _run(script: str, *args: str) -> tuple[dict, int]:
    proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / script), *args], capture_output=True, text=True)
    return json.loads(proc.stdout), proc.returncode


# ---------------------------------------------------------------------------
# eval_formula.py — restricted AST arithmetic evaluator
# ---------------------------------------------------------------------------

def test_eval_formula_computes_a_real_arithmetic_result():
    out, code = _run("eval_formula.py", "base_cost * 1.05", '{"base_cost": 420}')
    assert code == 0
    assert out["result"] == 441.0


def test_eval_formula_supports_multiple_variables_and_operators():
    out, code = _run("eval_formula.py", "(length * width) + fixed_fee", '{"length": 4, "width": 3, "fixed_fee": 10}')
    assert code == 0
    assert out["result"] == 22


def test_eval_formula_rejects_function_calls_not_just_by_convention():
    """The real security surface — a model-controlled expression string
    reaching real code execution would be a genuine vulnerability. This
    must be a structural rejection, not a policy the model is asked to
    follow."""
    out, code = _run("eval_formula.py", "__import__('os').system('echo pwned')", "{}")
    assert code == 1
    assert "error" in out
    assert "Call" in out["error"]


def test_eval_formula_rejects_attribute_access():
    out, code = _run("eval_formula.py", "().__class__", "{}")
    assert code == 1
    assert "error" in out


def test_eval_formula_reports_unresolved_variable_cleanly():
    out, code = _run("eval_formula.py", "a + b", '{"a": 5}')
    assert code == 1
    assert "b" in out["error"]


def test_eval_formula_reports_division_by_zero_cleanly():
    out, code = _run("eval_formula.py", "a / b", '{"a": 5, "b": 0}')
    assert code == 1
    assert "division" in out["error"].lower()


def test_eval_formula_rejects_non_numeric_input():
    out, code = _run("eval_formula.py", "a + 1", '{"a": "not a number"}')
    assert code == 1
    assert "error" in out


# ---------------------------------------------------------------------------
# cutlist_solver.py — real first-fit-decreasing bin-packing heuristic
# ---------------------------------------------------------------------------

def test_cutlist_solver_packs_a_real_known_case_correctly():
    out, code = _run("cutlist_solver.py", "96", "[42,42,30,24,18]", "0.125")
    assert code == 0
    assert out["algorithm"] == "first_fit_decreasing"
    assert out["bins_used"] == 2
    assert sorted(sum(b) for b in out["bins"]) == sorted([sum([42, 42]), sum([30, 24, 18])])
    # Every real cut length actually appears in exactly one bin — the
    # solver never drops or duplicates a requested cut.
    all_placed = sorted(length for b in out["bins"] for length in b)
    assert all_placed == sorted([42, 42, 30, 24, 18])


def test_cutlist_solver_refuses_a_cut_longer_than_stock():
    out, code = _run("cutlist_solver.py", "96", "[150]")
    assert code == 1
    assert "exceeds" in out["error"]


def test_cutlist_solver_refuses_non_positive_stock_length():
    out, code = _run("cutlist_solver.py", "-5", "[10]")
    assert code == 1
    assert "positive" in out["error"]


def test_cutlist_solver_single_bin_when_everything_fits():
    out, code = _run("cutlist_solver.py", "100", "[10,10,10]")
    assert code == 0
    assert out["bins_used"] == 1


# ---------------------------------------------------------------------------
# dxf_parse.py — real ezdxf-based DXF structure extraction
# ---------------------------------------------------------------------------

import pytest

ezdxf = pytest.importorskip("ezdxf")


@pytest.fixture
def sample_dxf(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_line((100, 0), (100, 50))
    msp.add_text("Panel A").set_placement((10, 10))
    doc.layers.add("DIMENSIONS")
    path = tmp_path / "sample.dxf"
    doc.saveas(str(path))
    return path


def test_dxf_parse_extracts_real_structure(sample_dxf):
    out, code = _run("dxf_parse.py", str(sample_dxf))
    assert code == 0
    assert "0" in out["layers"] and "DIMENSIONS" in out["layers"]
    assert out["entity_counts"]["LINE"] == 2
    assert out["entity_counts"]["TEXT"] == 1
    assert out["total_entities"] == 3
    assert "Panel A" in out["text_content"]


def test_dxf_parse_computes_real_geometric_extents_not_stale_header(sample_dxf):
    """The real bug this script avoids: DXF header $EXTMIN/$EXTMAX are
    only as accurate as whatever last maintained them, and are unset on
    a freshly-authored file like this fixture — computing from real
    entity geometry (ezdxf.bbox) is correct regardless of header state."""
    out, code = _run("dxf_parse.py", str(sample_dxf))
    assert code == 0
    assert out["extents"] == {"min": [0.0, 0.0], "max": [100.0, 50.0]}


def test_dxf_parse_fails_cleanly_on_a_corrupted_file(tmp_path):
    bad = tmp_path / "bad.dxf"
    bad.write_text("not a real dxf file")
    out, code = _run("dxf_parse.py", str(bad))
    assert code == 1
    assert "error" in out


def test_dxf_parse_fails_cleanly_on_a_missing_file():
    out, code = _run("dxf_parse.py", "/tmp/definitely_does_not_exist_12345.dxf")
    assert code == 1
    assert "error" in out
