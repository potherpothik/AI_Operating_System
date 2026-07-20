import json
import subprocess
import uuid
import httpx
import pytest

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry
from agents.calculation_agent import register as calculation_agent_register
from agents.cutlist_optimization_agent import register as cutlist_optimization_agent_register
from agents.autocad_agent import register as autocad_agent_register

LOCAL_MODEL = "qwen3.5:4b"
SCRIPTS_DIR = "/home/saadi/Documents/AI_Operating_System/.claude/worktrees/getting-started-3501ab/services/execution/execution/shell_executor/scripts"


def _ensure_ready(register_module, governance_url, assembly_url):
    db = SessionLocal()
    capability_registry.load_all(db)
    db.close()

    result = register_module.ensure_template_registered(created_by="test-suite")
    if result["registered"]:
        approval_id = result["result"]["approval_id"]
        httpx.post(f"{governance_url}/approval/{approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")


def _stub(action, **overrides):
    base = {
        "reasoning": "test reasoning", "answer_or_proposal": "test answer", "confidence": 0.9,
        "provenance": [], "risk_classification": "medium", "delegate_to": None, "action": action,
        "formula_name": None, "formula_inputs_json": None,
        "stock_length": None, "cut_lengths_json": None, "kerf": None,
        "dxf_path": None,
    }
    base.update(overrides)
    return json.dumps(base)


@pytest.fixture(autouse=True)
def set_calc_scripts_dir(execution_url, execution_sandbox_root):
    # Both CALC_SCRIPTS_DIR and CALC_WORKING_DIR are read at module-import
    # time (same "real local path, no default" convention as
    # PROPOSAL_REPO_PATH) — mutating the already-imported module
    # attributes directly is the robust way to set them for tests.
    # CALC_WORKING_DIR must be a real directory INSIDE whatever
    # SANDBOX_ROOT the live execution service (auto-started via
    # PHASE6_PATH, scoped to execution_sandbox_root) actually enforces —
    # a mismatched working_dir here is exactly the class of bug Phase
    # 15's own test setup hit when a manually-started execution service
    # used a different SANDBOX_ROOT than the fixture assumed.
    from agents.reasoning_engine import calc_bridge, cutlist_bridge, autocad_bridge
    for mod in (calc_bridge, cutlist_bridge, autocad_bridge):
        mod.CALC_SCRIPTS_DIR = SCRIPTS_DIR
        mod.CALC_WORKING_DIR = str(execution_sandbox_root)
    yield


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

def test_all_three_new_capabilities_discovered_with_correct_boundaries():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    for cap_name in ("calculation_agent", "cutlist_optimization_agent", "autocad_agent"):
        assert cap_name in loaded

    calc = capability_registry.get_capability(db, "calculation_agent")
    assert capability_registry.local_precheck(calc, "calc.apply_formula") == "allow"
    assert capability_registry.local_precheck(calc, "calc.explain_formula") == "allow"
    assert capability_registry.local_precheck(calc, "calc.assert_unverified_number") == "deny"

    cutlist = capability_registry.get_capability(db, "cutlist_optimization_agent")
    assert capability_registry.local_precheck(cutlist, "cutlist.gather_parameters") == "allow"
    assert capability_registry.local_precheck(cutlist, "cutlist.run_optimizer") == "require_approval"
    assert capability_registry.local_precheck(cutlist, "cutlist.generate_layout_direct") == "deny"

    autocad = capability_registry.get_capability(db, "autocad_agent")
    assert capability_registry.local_precheck(autocad, "autocad.explain_drawing") == "allow"
    assert capability_registry.local_precheck(autocad, "autocad.propose_annotation") == "require_approval"
    assert capability_registry.local_precheck(autocad, "autocad.modify_drawing_direct") == "deny"
    db.close()


# ---------------------------------------------------------------------------
# Calculation Agent — the model never asserts a number itself; every
# result comes from eval_formula.py's real restricted-AST evaluation.
# ---------------------------------------------------------------------------

def test_calc_apply_formula_uses_a_real_registered_formula_and_real_computation(
    full_stack, execution_url, knowledge_pipelines_url, monkeypatch,
):
    _ensure_ready(calculation_agent_register, full_stack["governance"], full_stack["assembly"])

    formula_name = f"phase17_test_formula_{uuid.uuid4().hex[:8]}"
    reg = httpx.post(
        f"{knowledge_pipelines_url}/erp-knowledge/formula/register",
        json={
            "name": formula_name, "formula_ref": "base_cost * 1.05", "business_purpose": "test surcharge",
            "defined_by": "human_admin", "target_namespace": "demo_erp",
        },
    ).json()
    httpx.post(f"{full_stack['governance']}/approval/{reg['memory_approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})

    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub("calc.apply_formula", formula_name=formula_name, formula_inputs_json=json.dumps({"base_cost": 420}))
        assert "441" in prompt  # the REAL computed number, not a model guess
        return _stub("calc.explain_formula", formula_name="", answer_or_proposal="Applying the surcharge formula gives 441.0.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"calc-test-{uuid.uuid4().hex[:8]}", task_description=f"Apply {formula_name} with base_cost 420.",
        agent_capability="calculation_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


def test_calc_apply_formula_never_completes_without_a_real_tool_call_round_trip(full_stack, monkeypatch):
    """Structural, not just prompted: a model that jumps straight to a
    final answer for an unresolvable formula never gets a 'completed'
    status backed by an invented number."""
    _ensure_ready(calculation_agent_register, full_stack["governance"], full_stack["assembly"])

    def fake_generate(model, prompt):
        return _stub("calc.apply_formula", formula_name="totally_nonexistent_formula_xyz", formula_inputs_json="{}")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"calc-badformula-test-{uuid.uuid4().hex[:8]}", task_description="Apply a nonexistent formula.",
        agent_capability="calculation_agent", namespace="default", target_model=LOCAL_MODEL, max_iterations=2,
    )
    db.close()
    # Exhausts iterations rather than fabricating a result — the model
    # kept re-requesting the same unresolvable formula, never got a real
    # number, never reached "completed".
    assert execution.status == "failed"


# ---------------------------------------------------------------------------
# Cutlist Optimization Agent — real FFD solve, requires approval on the
# finalizing turn.
# ---------------------------------------------------------------------------

def test_cutlist_run_optimizer_uses_the_real_solver(full_stack, execution_url, monkeypatch):
    _ensure_ready(cutlist_optimization_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub("cutlist.run_optimizer", stock_length="96", cut_lengths_json=json.dumps([42, 42, 30, 24, 18]), kerf="0.125")
        assert "first_fit_decreasing" in prompt
        assert "bins_used" in prompt
        return _stub("cutlist.run_optimizer", stock_length="", answer_or_proposal="The real solve uses 2 bins.", risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"cutlist-test-{uuid.uuid4().hex[:8]}", task_description="Optimize cuts for 96in stock: 42,42,30,24,18 with 0.125 kerf.",
        agent_capability="cutlist_optimization_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "awaiting_approval"
    assert execution.iterations_used == 2


# ---------------------------------------------------------------------------
# AutoCAD Agent — real DXF parsing via ezdxf, real geometric extents.
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_dxf(tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_line((100, 0), (100, 50))
    msp.add_text("Panel A").set_placement((10, 10))
    path = tmp_path / "sample.dxf"
    doc.saveas(str(path))
    return path


def test_autocad_explain_drawing_parses_a_real_file(full_stack, execution_url, sample_dxf, monkeypatch):
    _ensure_ready(autocad_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub("autocad.explain_drawing", dxf_path=str(sample_dxf))
        assert "Panel A" in prompt
        assert "100.0" in prompt  # real extents
        return _stub("autocad.explain_drawing", dxf_path="", answer_or_proposal="The drawing contains a panel labeled 'Panel A'.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"autocad-test-{uuid.uuid4().hex[:8]}", task_description=f"Explain the drawing at {sample_dxf}.",
        agent_capability="autocad_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


def test_autocad_propose_annotation_materializes_as_a_real_git_document(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(autocad_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Add a callout noting the 3in tolerance on the panel edge."

    def fake_generate(model, prompt):
        return _stub("autocad.propose_annotation", answer_or_proposal=proposal_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    task_id = f"autocad-propose-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    execution = loop.execute(
        db, task_id=task_id, task_description="Propose an annotation for the panel drawing.",
        agent_capability="autocad_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == f"autocad-agent/task-{task_id}"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/{task_id}.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output


# ---------------------------------------------------------------------------
# Live-model smoke tests
# ---------------------------------------------------------------------------

_TERMINAL_STATES = ("completed", "awaiting_approval", "refused", "delegated", "awaiting_delegation", "failed")


@pytest.mark.parametrize("agent_capability,register_module,question", [
    ("calculation_agent", calculation_agent_register, "In one sentence, explain why you never compute a formula result yourself. Don't apply any formula."),
    ("cutlist_optimization_agent", cutlist_optimization_agent_register, "In one sentence, explain what a cutting-stock problem is. Don't run any optimizer."),
    ("autocad_agent", autocad_agent_register, "In one sentence, explain the difference between DWG and DXF. Don't parse any drawing."),
])
def test_live_explain_only_smoke(full_stack, ollama_available, agent_capability, register_module, question):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    _ensure_ready(register_module, full_stack["governance"], full_stack["assembly"])

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"{agent_capability}-live-test-1", task_description=question,
        agent_capability=agent_capability, namespace="default", target_model=LOCAL_MODEL, max_iterations=6,
    )
    db.close()
    assert execution.status in _TERMINAL_STATES, f"unexpected status {execution.status!r}, failure_reason={execution.failure_reason!r}"
    assert execution.iterations_used >= 1
