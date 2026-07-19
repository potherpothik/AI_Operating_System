import os
import subprocess
import sys
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_database_connector.db")
os.environ.setdefault("DEMO_ERP_DATABASE_URL", "postgresql://saadi:devpassword@localhost:5432/demo_erp")

import pytest
import httpx

from database.db import engine, Base
from database.database_connector import pool


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    pool.reset()
    yield
    pool.reset()


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
def governance_url():
    url, proc = _ensure_service("SECURITY_LAYER_URL", "http://localhost:8000", "PHASE1_PATH", 8000)
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture
def demo_erp_clean(governance_url):
    """Resets the disposable demo_erp target's mutable rows to a known
    state before/after each test that writes to it — never touches any
    other service's own operational database."""
    import sqlalchemy
    target_engine = sqlalchemy.create_engine(os.environ["DEMO_ERP_DATABASE_URL"])
    with target_engine.begin() as conn:
        conn.execute(sqlalchemy.text("UPDATE sale_order SET state = 'sale' WHERE name = 'SO0003'"))
        conn.execute(sqlalchemy.text("DELETE FROM sale_order WHERE name LIKE 'TEST_%'"))
    yield
    with target_engine.begin() as conn:
        conn.execute(sqlalchemy.text("UPDATE sale_order SET state = 'draft' WHERE name = 'SO0003'"))
        conn.execute(sqlalchemy.text("DELETE FROM sale_order WHERE name LIKE 'TEST_%'"))
