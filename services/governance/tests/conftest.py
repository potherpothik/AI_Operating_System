import os
import subprocess
import sys
import time

# Only default to SQLite if the caller hasn't already set DATABASE_URL —
# unconditionally overwriting it here would silently run every test
# against SQLite even when a real Postgres URL was passed in, which is
# exactly what happened once already while verifying this project.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_governance.db")

import pytest
import httpx

from governance.db import engine, Base


@pytest.fixture(autouse=True)
def clean_db():
    """
    Truncates tables through the same live connection rather than deleting
    the SQLite file — StaticPool (governance/db.py) holds one persistent
    connection for the whole test session, and removing the file out from
    under that open connection is what was producing "readonly database"
    errors, not a real permissions problem.
    """
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture(scope="session")
def identity_url():
    """
    Phase 31: governance/security/oidc.py's verify_token() makes a real
    HTTP call to services/identity/'s real JWKS endpoint — same
    spin-up-or-skip pattern every other cross-service test dependency in
    this repo uses since services/agents/tests/conftest.py first
    established it.
    """
    url = os.environ.get("IDENTITY_URL", "http://localhost:8011")
    try:
        if httpx.get(f"{url}/", timeout=1.0).status_code == 200:
            yield url
            return
    except Exception:
        pass

    path = os.environ.get("PHASE31_PATH")
    if not path or not os.path.isdir(path):
        pytest.skip("IDENTITY_URL not reachable and PHASE31_PATH not set")

    env = dict(os.environ)
    env["IDENTITY_ISSUER"] = url
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", url.rsplit(":", 1)[-1]],
        cwd=path, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
        pytest.fail("identity service never became healthy")
    yield url
    proc.terminate()
    proc.wait(timeout=5)
