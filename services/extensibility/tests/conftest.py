import http.server
import os
import json
import socket
import subprocess
import sys
import threading
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_extensibility.db")

import pytest
import httpx

from extensibility.db import engine, Base


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


@pytest.fixture(scope="session")
def plugin_capabilities_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("plugin_capabilities")


@pytest.fixture(scope="session")
def agents_url(governance_url, platform_url, knowledge_url, assembly_url, plugin_capabilities_dir):
    url, proc = _ensure_service(
        "AGENTS_URL", "http://localhost:8005", "PHASE5_PATH", 8005,
        extra_env={
            "SECURITY_LAYER_URL": governance_url, "PLATFORM_URL": platform_url, "KNOWLEDGE_URL": knowledge_url,
            "ASSEMBLY_URL": assembly_url, "PLUGIN_CAPABILITIES_DIR": str(plugin_capabilities_dir),
        },
    )
    yield url
    if proc:
        proc.terminate()
        proc.wait(timeout=5)


class _StubMcpHandler(http.server.BaseHTTPRequestHandler):
    """A real, minimal HTTP server speaking this adapter's simplified
    REST contract — genuinely listens on a real socket and answers a
    real POST /invoke, not a mocked httpx call."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        tool = body.get("tool")
        params = body.get("params", {})

        if tool == "echo":
            response = {"result": {"echoed": params.get("text", "")}}
        elif tool == "bad_schema":
            response = {"result": {"wrong_field": "nope"}}
        elif tool == "add":
            response = {"result": {"sum": params.get("a", 0) + params.get("b", 0)}}
        else:
            response = {"result": {}}

        payload = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002 — silence default request logging
        pass


@pytest.fixture(scope="session")
def stub_mcp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = http.server.HTTPServer(("127.0.0.1", port), _StubMcpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
