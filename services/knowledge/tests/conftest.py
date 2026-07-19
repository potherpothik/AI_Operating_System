import os
import subprocess
import sys
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_knowledge.db")

import pytest
import httpx

from knowledge.db import engine, Base


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture(scope="session")
def security_layer_url():
    """Same pattern as Phase 2's conftest — real Phase 1 instance, or a clean skip."""
    url = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")

    try:
        if httpx.get(f"{url}/", timeout=1.0).status_code == 200:
            yield url
            return
    except Exception:
        pass

    phase1_path = os.environ.get("PHASE1_PATH")
    if not phase1_path or not os.path.isdir(phase1_path):
        pytest.skip("Security Layer not reachable and PHASE1_PATH not set")

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
