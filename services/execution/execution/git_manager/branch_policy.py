import os
import re

PROTECTED_BRANCHES = set(os.environ.get("GIT_PROTECTED_BRANCHES", "main,master,production").split(","))

_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class ProtectedBranchError(Exception):
    pass


class InvalidTaskId(Exception):
    pass


def agent_branch_prefix(agent_capability: str) -> str:
    return agent_capability.replace("_", "-")


def agent_branch_name(agent_capability: str, task_id: str) -> str:
    """
    The only way an agent-originated branch name is produced — Git
    Manager computes it, it is never taken verbatim from agent/model
    input (Phase 6 doc, Git Manager security notes: "the push target is
    computed by Git Manager itself, never taken from agent input").
    """
    if not task_id or not _SAFE_TASK_ID.match(task_id):
        raise InvalidTaskId(f"task_id {task_id!r} contains characters not safe for a branch name")
    return f"{agent_branch_prefix(agent_capability)}/task-{task_id}"


def assert_not_protected(branch_name: str):
    if branch_name in PROTECTED_BRANCHES:
        raise ProtectedBranchError(f"{branch_name!r} is a protected branch — agents may never target it directly")


def assert_push_target_is_own_branch(branch_name: str, agent_capability: str):
    """
    Structural, in-code enforcement — not only an external policy check.
    Even if Security Layer or the command allowlist were somehow
    bypassed, this still refuses to construct a push command targeting
    anything but the calling agent's own branch namespace.
    """
    assert_not_protected(branch_name)
    prefix = agent_branch_prefix(agent_capability) + "/"
    if not branch_name.startswith(prefix):
        raise ProtectedBranchError(
            f"{branch_name!r} is outside {agent_capability!r}'s own branch namespace ({prefix}*) — refusing to push"
        )
