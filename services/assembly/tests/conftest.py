import os
import subprocess
import sys
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_assembly.db")

import pytest
import httpx

from assembly.db import engine, Base


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


def _ensure_service(url_env_var: str, default_url: str, path_env_var: str, port: int):
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


@pytest.fixture(scope="session")
def platform_url(governance_url):
    url, proc = _ensure_service("PLATFORM_URL", "http://localhost:8002", "PHASE2_PATH", 8002)
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def knowledge_url(governance_url):
    url, proc = _ensure_service("KNOWLEDGE_URL", "http://localhost:8003", "PHASE3_PATH", 8003)
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture
def full_stack(governance_url, platform_url, knowledge_url):
    """Convenience fixture for tests that need all three."""
    return {"governance": governance_url, "platform": platform_url, "knowledge": knowledge_url}
