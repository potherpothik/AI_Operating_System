import os
import subprocess
import sys
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_agents.db")

import pytest
import httpx

from agents.db import engine, Base


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


def _ensure_service(url_env_var: str, default_url: str, path_env_var: str, port: int, extra_env: dict = None):
    """Shared logic: use an already-running instance if reachable, else
    start one from PATH_ENV_VAR's checkout, else skip the test cleanly."""
    url = os.environ.get(url_env_var, default_url)
    try:
        if httpx.get(f"{url}/", timeout=1.0).status_code == 200:
            return url, None
    except Exception:
        pass

    path = os.environ.get(path_env_var)
    if not path or not os.path.isdir(path):
        pytest.skip(f"{url_env_var} not reachable and {path_env_var} not set")

    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=path, env=env,
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


@pytest.fixture(scope="session")
def platform_url(governance_url):
    url, proc = _ensure_service(
        "PLATFORM_URL", "http://localhost:8002", "PHASE2_PATH", 8002,
        extra_env={"SECURITY_LAYER_URL": governance_url},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def knowledge_url(governance_url):
    url, proc = _ensure_service(
        "KNOWLEDGE_URL", "http://localhost:8003", "PHASE3_PATH", 8003,
        extra_env={"SECURITY_LAYER_URL": governance_url},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def assembly_url(governance_url, platform_url, knowledge_url):
    url, proc = _ensure_service(
        "ASSEMBLY_URL", "http://localhost:8004", "PHASE4_PATH", 8004,
        extra_env={"SECURITY_LAYER_URL": governance_url, "PLATFORM_URL": platform_url, "KNOWLEDGE_URL": knowledge_url},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture
def full_stack(governance_url, platform_url, knowledge_url, assembly_url):
    return {"governance": governance_url, "platform": platform_url, "knowledge": knowledge_url, "assembly": assembly_url}


@pytest.fixture(scope="session")
def ollama_available():
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    try:
        return httpx.get(f"{url}/api/tags", timeout=2.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session")
def execution_sandbox_root(tmp_path_factory):
    return tmp_path_factory.mktemp("execution_sandbox_root")


@pytest.fixture(scope="session")
def execution_url(governance_url, execution_sandbox_root):
    url, proc = _ensure_service(
        "EXECUTION_URL", "http://localhost:8006", "PHASE6_PATH", 8006,
        extra_env={"SECURITY_LAYER_URL": governance_url, "SANDBOX_ROOT": str(execution_sandbox_root)},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture
def disposable_bare_repo_for_bridge(execution_sandbox_root):
    """A real, throwaway bare repo the wired-together Phase 5/6 flow
    pushes to — never the actual project repo or real GitHub."""
    import subprocess
    bare = execution_sandbox_root / "origin.git"
    if not bare.exists():
        subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    return bare


@pytest.fixture
def proposal_repo(execution_sandbox_root, disposable_bare_repo_for_bridge, monkeypatch):
    """A real clone, inside execution's own SANDBOX_ROOT so the live
    execution service (a separate process) will accept it as a
    working_dir, with an initial commit so there's a real HEAD."""
    import subprocess
    import uuid
    work_dir = execution_sandbox_root / f"proposal-repo-{uuid.uuid4().hex[:8]}"
    subprocess.run(["git", "clone", str(disposable_bare_repo_for_bridge), str(work_dir)], check=True, capture_output=True)
    (work_dir / "README.md").write_text("initial\n")
    subprocess.run(["git", "-C", str(work_dir), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(work_dir), "-c", "user.email=test@test.local", "-c", "user.name=test", "commit", "-m", "initial commit"],
        check=True, capture_output=True,
    )
    subprocess.run(["git", "-C", str(work_dir), "push", "origin", "main"], check=True, capture_output=True)
    monkeypatch.setenv("PROPOSAL_REPO_PATH", str(work_dir))
    from agents.reasoning_engine import execution_bridge
    monkeypatch.setattr(execution_bridge, "PROPOSAL_REPO_PATH", str(work_dir))
    return work_dir
