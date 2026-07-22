import os
import subprocess
import time
import sys

# Only default to SQLite if the caller hasn't already set DATABASE_URL.
# Phase 1's conftest.py originally overwrote this unconditionally, which
# silently made every "Postgres" test run actually run against SQLite —
# not repeating that here.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_platform.db")

import pytest
import httpx

from platform_spine.db import engine, Base
from platform_spine.gateway import rate_limit


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    rate_limit.reset()
    yield


def _ensure_service(url_env_var: str, default_url: str, path_env_var: str, port: int, extra_env: dict = None):
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
def security_layer_url():
    """
    Integration tests need a real Security Layer (Phase 1) instance
    reachable. If one is already running at SECURITY_LAYER_URL, use it.
    If not, and PHASE1_PATH points at a Phase 1 checkout, start one for
    the duration of the test session. Otherwise, tests that need it are
    skipped rather than failing confusingly.
    """
    url, proc = _ensure_service("SECURITY_LAYER_URL", "http://localhost:8000", "PHASE1_PATH", 8000)
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def identity_url(security_layer_url):
    """Phase 31: AUTH_MODE=oidc tests need a real identity token — this
    just needs identity reachable directly (governance calls it
    independently for /security/verify_token)."""
    url, proc = _ensure_service(
        "IDENTITY_URL", "http://localhost:8011", "PHASE31_PATH", 8011,
        extra_env={"IDENTITY_ISSUER": "http://localhost:8011"},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def assembly_url(security_layer_url):
    """
    Phase 27: the OpenAI shim's real classification-ceiling check
    (assembly's ceiling_for_model()) needs a real Assembly instance.
    """
    url, proc = _ensure_service(
        "ASSEMBLY_URL", "http://localhost:8004", "PHASE4_PATH", 8004,
        extra_env={"SECURITY_LAYER_URL": security_layer_url},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def agents_url(security_layer_url, assembly_url):
    """Phase 27: the OpenAI shim's real model calls proxy through
    services/agents' /reasoning/raw_generate* endpoints."""
    url, proc = _ensure_service(
        "AGENTS_URL", "http://localhost:8005", "PHASE5_PATH", 8005,
        extra_env={"SECURITY_LAYER_URL": security_layer_url, "ASSEMBLY_URL": assembly_url},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)
