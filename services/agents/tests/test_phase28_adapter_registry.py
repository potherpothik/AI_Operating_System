from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_adapters_lists_real_model_provider_configuration_status():
    r = client.get("/reasoning/adapters")
    assert r.status_code == 200
    body = r.json()

    providers = {p["name"]: p["configured"] for p in body["model_providers"]}
    assert set(providers) == {"ollama", "openai", "anthropic", "gemini"}
    # Real, live-checked status, not a guess: openai/anthropic/gemini are
    # genuinely never configured in this offline-first build (Phase 23's
    # own scope decision — no API keys are ever set here).
    assert providers["openai"] is False
    assert providers["anthropic"] is False
    assert providers["gemini"] is False


def test_adapters_lists_the_real_tool_adapters_and_ide_surfaces():
    body = client.get("/reasoning/adapters").json()

    tool_names = {a["name"] for a in body["tool_adapters"]}
    assert tool_names == {"shell_executor", "git_manager", "database_connector", "mcp_client"}

    surface_names = {a["name"] for a in body["ide_surfaces"]}
    assert surface_names == {"mcp_surface", "openai_shim"}
