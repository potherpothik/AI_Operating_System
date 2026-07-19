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
