import os
import subprocess
import sys
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_observability.db")

import pytest
import httpx

from observability.db import engine, Base


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
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
def governance_url():
    url, proc = _ensure_service("GOVERNANCE_URL", "http://localhost:8000", "PHASE1_PATH", 8000)
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


@pytest.fixture(scope="session")
def agents_url(governance_url, platform_url, knowledge_url, assembly_url):
    url, proc = _ensure_service(
        "AGENTS_URL", "http://localhost:8005", "PHASE5_PATH", 8005,
        extra_env={
            "SECURITY_LAYER_URL": governance_url, "PLATFORM_URL": platform_url,
            "KNOWLEDGE_URL": knowledge_url, "ASSEMBLY_URL": assembly_url,
        },
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def execution_url(governance_url):
    url, proc = _ensure_service(
        "EXECUTION_URL", "http://localhost:8006", "PHASE6_PATH", 8006,
        extra_env={"SECURITY_LAYER_URL": governance_url, "SANDBOX_ROOT": "/tmp/ai_os_sandbox"},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def database_url(governance_url):
    url, proc = _ensure_service(
        "DATABASE_CONNECTOR_URL", "http://localhost:8007", "PHASE7_PATH", 8007,
        extra_env={
            "SECURITY_LAYER_URL": governance_url,
            "DEMO_ERP_DATABASE_URL": os.environ.get("DEMO_ERP_DATABASE_URL", "postgresql://saadi:devpassword@localhost:5432/demo_erp"),
        },
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def planning_url(governance_url, agents_url, platform_url):
    url, proc = _ensure_service(
        "PLANNING_URL", "http://localhost:8008", "PHASE8_PATH", 8008,
        extra_env={"SECURITY_LAYER_URL": governance_url, "AGENTS_URL": agents_url, "PLATFORM_URL": platform_url},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def knowledge_pipelines_url(governance_url, knowledge_url, database_url):
    url, proc = _ensure_service(
        "KNOWLEDGE_PIPELINES_URL", "http://localhost:8009", "PHASE9_PATH", 8009,
        extra_env={"SECURITY_LAYER_URL": governance_url, "KNOWLEDGE_URL": knowledge_url, "DATABASE_CONNECTOR_URL": database_url},
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def ollama_available():
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    try:
        return httpx.get(f"{url}/api/tags", timeout=2.0).status_code == 200
    except Exception:
        return False


@pytest.fixture
def full_stack(governance_url, platform_url, knowledge_url, assembly_url, agents_url, execution_url, database_url, knowledge_pipelines_url):
    """Points observability's own registry.py env vars at every real,
    already-started peer service — used by tests that exercise health_monitor
    or metrics_dashboard against genuine live data, not fixtures."""
    import os as _os
    _os.environ["GOVERNANCE_URL"] = governance_url
    _os.environ["PLATFORM_URL"] = platform_url
    _os.environ["KNOWLEDGE_URL"] = knowledge_url
    _os.environ["ASSEMBLY_URL"] = assembly_url
    _os.environ["AGENTS_URL"] = agents_url
    _os.environ["EXECUTION_URL"] = execution_url
    _os.environ["DATABASE_CONNECTOR_URL"] = database_url
    _os.environ["KNOWLEDGE_PIPELINES_URL"] = knowledge_pipelines_url
    return {
        "governance": governance_url, "platform-spine": platform_url, "knowledge": knowledge_url,
        "assembly": assembly_url, "agents": agents_url, "execution": execution_url,
        "database": database_url, "knowledge_pipelines": knowledge_pipelines_url,
    }
