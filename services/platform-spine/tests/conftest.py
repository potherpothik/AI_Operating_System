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


@pytest.fixture(scope="session")
def security_layer_url():
    """
    Integration tests need a real Security Layer (Phase 1) instance
    reachable. If one is already running at SECURITY_LAYER_URL, use it.
    If not, and PHASE1_PATH points at a Phase 1 checkout, start one for
    the duration of the test session. Otherwise, tests that need it are
    skipped rather than failing confusingly.
    """
    url = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")

    try:
        if httpx.get(f"{url}/", timeout=1.0).status_code == 200:
            yield url
            return
    except Exception:
        pass

    phase1_path = os.environ.get("PHASE1_PATH")
    if not phase1_path or not os.path.isdir(phase1_path):
        pytest.skip(
            "Security Layer not reachable and PHASE1_PATH not set — "
            "start Phase 1 (see its README) or set PHASE1_PATH to its checkout"
        )

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=phase1_path,
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
        pytest.fail("Started Phase 1 but it never became healthy")

    yield url
    proc.terminate()
    proc.wait(timeout=5)
