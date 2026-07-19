import pytest

from execution.git_manager import branch_policy


def test_agent_branch_name_uses_hyphenated_capability():
    assert branch_policy.agent_branch_name("odoo_agent", "abc123") == "odoo-agent/task-abc123"


def test_agent_branch_name_rejects_unsafe_task_id():
    with pytest.raises(branch_policy.InvalidTaskId):
        branch_policy.agent_branch_name("odoo_agent", "abc; rm -rf /")


def test_agent_branch_name_rejects_empty_task_id():
    with pytest.raises(branch_policy.InvalidTaskId):
        branch_policy.agent_branch_name("odoo_agent", "")


def test_protected_branches_rejected():
    for b in ("main", "master", "production"):
        with pytest.raises(branch_policy.ProtectedBranchError):
            branch_policy.assert_not_protected(b)


def test_non_protected_branch_passes():
    branch_policy.assert_not_protected("odoo-agent/task-1")  # should not raise


def test_push_target_must_be_own_namespace():
    branch_policy.assert_push_target_is_own_branch("odoo-agent/task-1", "odoo_agent")  # should not raise
    with pytest.raises(branch_policy.ProtectedBranchError):
        branch_policy.assert_push_target_is_own_branch("django-agent/task-1", "odoo_agent")


def test_push_target_rejects_protected_branch_even_with_matching_prefix_trick():
    with pytest.raises(branch_policy.ProtectedBranchError):
        branch_policy.assert_push_target_is_own_branch("main", "odoo_agent")
