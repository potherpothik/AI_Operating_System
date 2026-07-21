import os
import subprocess
import sys
import time

import pytest
import httpx


def _ensure_service(url_env_var: str, default_url: str, path_env_var: str, port: int, extra_env: dict = None):
    """Same shared spin-up-or-skip pattern every other service's own
    conftest.py uses since services/agents/tests/conftest.py first
    established it."""
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

    # Each backing service runs from the SHARED repo .venv, not this
    # service's own isolated one — the mcp SDK stays confined to
    # services/mcp-surface/.venv precisely so it never touches the
    # shared venv other services depend on (a real starlette/fastapi
    # version conflict was found and fixed this phase).
    shared_venv_python = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(path))), ".venv", "bin", "python")
    python_bin = shared_venv_python if os.path.exists(shared_venv_python) else sys.executable

    proc = subprocess.Popen(
        [python_bin, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
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
def mcp_server_url(governance_url, platform_url):
    """The mcp-surface server itself, started from ITS OWN isolated venv
    (sys.executable — this test process already runs inside it)."""
    url = "http://localhost:8025"
    try:
        if httpx.get(f"{url}/healthz", timeout=1.0).status_code == 200:
            yield url
            return
    except Exception:
        pass

    env = dict(os.environ)
    env["SECURITY_LAYER_URL"] = governance_url
    env["PLATFORM_URL"] = platform_url
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8025"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            if httpx.get(f"{url}/healthz", timeout=1.0).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.fail("mcp-surface never became healthy")
    yield url
    proc.terminate()
    proc.wait(timeout=5)
