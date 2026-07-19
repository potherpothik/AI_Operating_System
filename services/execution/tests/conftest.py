import os
import subprocess
import sys
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_execution.db")

import pytest
import httpx

from execution.db import engine, Base


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


def _ensure_service(url_env_var: str, default_url: str, path_env_var: str, port: int):
    url = os.environ.get(url_env_var, default_url)
    try:
        if httpx.get(f"{url}/", timeout=1.0).status_code == 200:
            return url, None
    except Exception:
        pass

    path = os.environ.get(path_env_var)
    if not path or not os.path.isdir(path):
        pytest.skip(f"{url_env_var} not reachable and {path_env_var} not set")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            if httpx.get(f"{url}/", timeout=1.0).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.fail(f"started a process for {url_env_var} but it never became healthy")
    return url, proc


@pytest.fixture(scope="session")
def governance_url():
    url, proc = _ensure_service("SECURITY_LAYER_URL", "http://localhost:8000", "PHASE1_PATH", 8000)
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture
def sandbox_root(tmp_path, monkeypatch):
    """Every test gets its own SANDBOX_ROOT under pytest's tmp_path — real
    filesystem operations, fully disposable, never touches anything
    outside the test run."""
    root = tmp_path / "ai_os_sandbox"
    root.mkdir()
    monkeypatch.setenv("SANDBOX_ROOT", str(root))
    from execution.shell_executor import sandbox as sandbox_module
    monkeypatch.setattr(sandbox_module, "SANDBOX_ROOT", root)
    return root


@pytest.fixture
def disposable_bare_repo(tmp_path):
    """A real, throwaway bare git repo standing in for 'the forge's
    remote' — never the actual potherpothik/AI_Operating_System repo or
    real GitHub. Proves branch protection, provenance trailers, and push
    behavior against genuine git, safely."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    return bare


@pytest.fixture
def cloned_repo(sandbox_root, disposable_bare_repo):
    """A working clone of disposable_bare_repo, inside SANDBOX_ROOT so
    Shell Executor will actually accept it as a working_dir, with an
    initial commit on main so there's a real HEAD to branch from."""
    work_dir = sandbox_root / "task-1"
    subprocess.run(["git", "clone", str(disposable_bare_repo), str(work_dir)], check=True, capture_output=True)
    (work_dir / "README.md").write_text("initial\n")
    subprocess.run(["git", "-C", str(work_dir), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(work_dir), "-c", "user.email=test@test.local", "-c", "user.name=test", "commit", "-m", "initial commit"],
        check=True, capture_output=True,
    )
    subprocess.run(["git", "-C", str(work_dir), "push", "origin", "main"], check=True, capture_output=True)
    return work_dir
