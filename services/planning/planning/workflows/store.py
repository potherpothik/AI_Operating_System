import os
from pathlib import Path

import yaml

# Phase 30: a real repo-tracked directory (workflows/, checked into git,
# not a runtime /tmp path) — needs an explicit path, same "real local
# path, single-host dev convention" PROPOSAL_REPO_PATH already
# established, since there's no universal correct relative guess from
# wherever this service happens to be started.
WORKFLOWS_DIR = os.environ.get("WORKFLOWS_DIR")

_REQUIRED_WORKFLOW_KEYS = {"workflow", "steps"}
_REQUIRED_STEP_KEYS = {"subtask_id", "description", "agent_capability"}


class WorkflowNotConfigured(Exception):
    pass


class WorkflowNotFound(Exception):
    pass


class WorkflowDefinitionInvalid(Exception):
    pass


def _validate(data: dict, path: Path) -> dict:
    missing = _REQUIRED_WORKFLOW_KEYS - data.keys()
    if missing:
        raise WorkflowDefinitionInvalid(f"{path}: missing required key(s) {sorted(missing)}")
    step_ids = set()
    for step in data["steps"]:
        missing_step = _REQUIRED_STEP_KEYS - step.keys()
        if missing_step:
            raise WorkflowDefinitionInvalid(f"{path}: step missing required key(s) {sorted(missing_step)}")
        step_ids.add(step["subtask_id"])
    for step in data["steps"]:
        unknown_deps = set(step.get("depends_on", [])) - step_ids
        if unknown_deps:
            raise WorkflowDefinitionInvalid(
                f"{path}: step {step['subtask_id']!r} depends_on unknown step id(s) {sorted(unknown_deps)}"
            )
    return data


def list_workflows() -> list[dict]:
    """Real discovery, same glob-and-load pattern
    capability_registry.py's _discover_capability_files() already
    established — every *.yaml file under WORKFLOWS_DIR is a real,
    reusable workflow definition, not a database row."""
    if not WORKFLOWS_DIR:
        raise WorkflowNotConfigured("WORKFLOWS_DIR not configured — cannot discover any workflow definitions")
    root = Path(WORKFLOWS_DIR)
    if not root.is_dir():
        raise WorkflowNotConfigured(f"WORKFLOWS_DIR={WORKFLOWS_DIR!r} is not a real directory")

    workflows = []
    for path in sorted(root.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        workflows.append(_validate(data, path))
    return workflows


def get_workflow(name: str) -> dict:
    for wf in list_workflows():
        if wf["workflow"] == name:
            return wf
    raise WorkflowNotFound(f"no workflow named {name!r} found under {WORKFLOWS_DIR}")
