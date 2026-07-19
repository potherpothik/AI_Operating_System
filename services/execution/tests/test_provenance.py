from execution.git_manager import provenance


def test_trailer_includes_all_fields():
    trailer = provenance.build_trailer("task-1", "odoo_agent", "ctx-1", "exec-1")
    assert "Task-Id: task-1" in trailer
    assert "Agent-Capability: odoo_agent" in trailer
    assert "Context-Id: ctx-1" in trailer
    assert "Reasoning-Execution-Id: exec-1" in trailer


def test_trailer_omits_missing_optional_fields():
    trailer = provenance.build_trailer("task-1", "odoo_agent", None, None)
    assert "Context-Id" not in trailer
    assert "Reasoning-Execution-Id" not in trailer


def test_commit_message_ends_with_trailer():
    message = provenance.build_commit_message("Fix invoice threshold", "task-1", "odoo_agent", context_id="ctx-1")
    lines = message.strip().split("\n")
    assert lines[0] == "Fix invoice threshold"
    assert "Task-Id: task-1" in message
    assert message.endswith("\n")


def test_commit_message_includes_body_when_given():
    message = provenance.build_commit_message("Summary line", "task-1", "odoo_agent", body="Longer explanation here.")
    assert "Summary line" in message
    assert "Longer explanation here." in message


def test_agent_git_identity_is_distinct_not_the_host_users_identity():
    import subprocess
    identity = provenance.agent_git_identity("odoo_agent")
    assert identity["GIT_AUTHOR_EMAIL"] == "agent+odoo_agent@ai-orchestration.local"
    assert identity["GIT_AUTHOR_NAME"] == "Odoo Agent"

    # The actual point of this test: whatever the host's own global git
    # identity happens to be, the agent's identity must never collide
    # with it — this is what makes agent commits distinguishable from
    # human ones in git log, per the Phase 6 doc's security requirement.
    host_email = subprocess.run(
        ["git", "config", "--global", "user.email"], capture_output=True, text=True
    ).stdout.strip()
    if host_email:
        assert identity["GIT_AUTHOR_EMAIL"] != host_email
