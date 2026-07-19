import os
import threading
import time
import pytest

from execution.shell_executor import sandbox as sandbox_module
from execution.shell_executor.sandbox import SubprocessSandbox, WorkingDirNotAllowed, docker_available


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    root = tmp_path / "sandbox_root"
    root.mkdir()
    monkeypatch.setattr(sandbox_module, "SANDBOX_ROOT", root)
    d = root / "task-1"
    d.mkdir()
    return d


def test_docker_confirmed_unavailable_in_this_environment():
    """Documents the actual state of this sandbox environment — Docker
    genuinely isn't installed here, which is why SubprocessSandbox is the
    backend actually exercised by the rest of this test file."""
    assert docker_available() is False


def test_simple_command_runs_and_captures_output(work_dir):
    result = SubprocessSandbox().run("echo", ["hello"], str(work_dir), "read_only")
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.backend == "subprocess"


def test_nonzero_exit_code_is_captured_not_raised(work_dir):
    result = SubprocessSandbox().run("sh", ["-c", "exit 7"], str(work_dir), "read_only")
    assert result.exit_code == 7


def test_working_dir_outside_sandbox_root_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "sandbox_root"
    root.mkdir()
    monkeypatch.setattr(sandbox_module, "SANDBOX_ROOT", root)
    outside = tmp_path / "somewhere_else"
    outside.mkdir()
    with pytest.raises(WorkingDirNotAllowed):
        SubprocessSandbox().run("echo", ["hi"], str(outside), "read_only")


def test_command_actually_runs_inside_working_dir(work_dir):
    (work_dir / "marker.txt").write_text("present")
    result = SubprocessSandbox().run("ls", [], str(work_dir), "read_only")
    assert "marker.txt" in result.stdout


def test_timeout_kills_long_running_command(work_dir):
    result = SubprocessSandbox().run("sleep", ["10"], str(work_dir), "read_only", timeout_seconds=1)
    assert result.timed_out is True
    assert result.duration_ms < 5000


def test_command_that_forks_a_child_process_is_not_blocked(work_dir):
    """
    Regression test: an earlier version set RLIMIT_NPROC(64, 64) as a
    per-execution process-count limit, but that rlimit is actually scoped
    per-UID, system-wide — not per-subprocess-tree. It broke `git push`
    against even a local repo ("fatal: unable to fork" from git's
    legitimate fork of git-receive-pack) purely because of this host's
    ambient process count, nothing to do with the command itself. A
    shell command that forks a child (sh -c 'true & wait') must succeed.
    """
    result = SubprocessSandbox().run("sh", ["-c", "true & wait"], str(work_dir), "read_only")
    assert result.exit_code == 0
    assert "unable to fork" not in (result.stderr or "")


def test_env_is_restricted_not_inherited_wholesale(work_dir, monkeypatch):
    monkeypatch.setenv("SOME_SECRET_LOOKING_VAR", "should-not-leak")
    result = SubprocessSandbox().run("sh", ["-c", "echo $SOME_SECRET_LOOKING_VAR"], str(work_dir), "read_only")
    assert result.stdout.strip() == ""


def test_kill_terminates_a_genuinely_running_process(work_dir):
    sandbox = SubprocessSandbox()
    results = {}

    def _run():
        results["result"] = sandbox.run("sleep", ["5"], str(work_dir), "read_only", timeout_seconds=30, sandbox_id="kill-test-1")

    thread = threading.Thread(target=_run)
    thread.start()
    time.sleep(0.5)  # let the subprocess actually start
    was_killed = sandbox.kill("kill-test-1")
    thread.join(timeout=10)

    assert was_killed is True
    assert results["result"].duration_ms < 4000  # killed well before the 5s sleep or 30s timeout would've elapsed
