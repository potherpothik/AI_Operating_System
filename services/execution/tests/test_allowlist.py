from execution.shell_executor import allowlist


def test_unknown_capability_denied_by_default():
    allowed, reason = allowlist.check("nonexistent_capability", "git", ["status"], "read_only")
    assert allowed is False


def test_read_only_git_diff_allowed():
    allowed, reason = allowlist.check("odoo_agent", "git", ["diff", "--stat"], "read_only")
    assert allowed is True


def test_mutating_git_commit_allowed():
    allowed, reason = allowlist.check("odoo_agent", "git", ["commit", "-m", "msg"], "mutating")
    assert allowed is True


def test_push_only_allowed_to_own_branch_namespace():
    allowed, _ = allowlist.check("odoo_agent", "git", ["push", "origin", "odoo-agent/task-1"], "mutating")
    assert allowed is True
    allowed, reason = allowlist.check("odoo_agent", "git", ["push", "origin", "main"], "mutating")
    assert allowed is False


def test_arbitrary_command_not_on_allowlist_denied():
    allowed, reason = allowlist.check("odoo_agent", "rm", ["-rf", "/"], "mutating")
    assert allowed is False


def test_mode_mismatch_is_denied():
    """A command declared read_only that matches a pattern only registered
    as mutating (or vice versa) must not slip through — the caller's own
    mode claim has to match what's actually allowed."""
    allowed, reason = allowlist.check("odoo_agent", "git", ["commit", "-m", "msg"], "read_only")
    assert allowed is False
