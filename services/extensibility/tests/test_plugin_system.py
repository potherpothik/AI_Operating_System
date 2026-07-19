import httpx
import pytest

from extensibility.db import SessionLocal
from extensibility.plugin_system import api, store, manifest, installer

SAMPLE_CAPABILITY_YAML = """\
capability: greeter_plugin_agent
allowed_actions:
  - greeter.say_hello
forbidden_actions: []
requires_approval: []
classification_ceiling: internal
template_id: greeter_plugin_agent
"""

SAMPLE_TEMPLATE_MD = """\
You are Greeter Plugin Agent, a small test plugin.

Task: {task_description}

{untrusted_warning}
{context}

{shared_fragment}
Also include: "action": always "greeter.say_hello"
"""


def _install_and_approve(db, governance_url, name, required_permissions=None):
    result = api.install(api.InstallRequest(
        name=name, capability_yaml=SAMPLE_CAPABILITY_YAML.replace("greeter_plugin_agent", name),
        template_md=SAMPLE_TEMPLATE_MD, required_permissions=required_permissions or [], installed_by="human_admin",
    ), db)
    httpx.post(f"{governance_url}/approval/{result['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})
    return result


def test_install_is_pending_until_approved(governance_url):
    db = SessionLocal()
    result = api.install(api.InstallRequest(
        name="plugin-1", capability_yaml=SAMPLE_CAPABILITY_YAML.replace("greeter_plugin_agent", "plugin_1"),
        template_md=SAMPLE_TEMPLATE_MD, installed_by="human_admin",
    ), db)
    db.close()
    assert result["status"] == "pending_approval"
    assert result["approval_id"]


def test_install_rejected_for_unverifiable_permission():
    db = SessionLocal()
    with pytest.raises(Exception):
        api.install(api.InstallRequest(
            name="plugin-bad-perm", capability_yaml=SAMPLE_CAPABILITY_YAML.replace("greeter_plugin_agent", "plugin_bad_perm"),
            template_md=SAMPLE_TEMPLATE_MD, required_permissions=["totally.made_up_permission"], installed_by="human_admin",
        ), db)
    db.close()
    # never even reached the store, since rejection happens before persistence
    assert store.get_plugin_by_name(db, "plugin-bad-perm") is None


def test_install_rejected_for_malformed_capability_yaml():
    db = SessionLocal()
    with pytest.raises(Exception):
        api.install(api.InstallRequest(
            name="plugin-malformed", capability_yaml="not: valid: yaml: [", template_md=SAMPLE_TEMPLATE_MD, installed_by="human_admin",
        ), db)
    db.close()


def test_install_rejected_when_capability_yaml_missing_capability_key():
    db = SessionLocal()
    with pytest.raises(Exception):
        api.install(api.InstallRequest(
            name="plugin-no-cap", capability_yaml="allowed_actions: [foo.bar]\n", template_md=SAMPLE_TEMPLATE_MD, installed_by="human_admin",
        ), db)
    db.close()


def test_known_permission_passes_validation():
    assert manifest.validate_permissions(["shell.execute", "git.branch"]) == []


def test_unknown_permission_fails_validation():
    assert "made_up.permission" in manifest.validate_permissions(["shell.execute", "made_up.permission"])


def test_duplicate_plugin_name_rejected(governance_url):
    db = SessionLocal()
    _install_and_approve(db, governance_url, "plugin-dup")
    with pytest.raises(Exception):
        api.install(api.InstallRequest(
            name="plugin-dup", capability_yaml=SAMPLE_CAPABILITY_YAML, template_md=SAMPLE_TEMPLATE_MD, installed_by="human_admin",
        ), db)
    db.close()


def test_activate_before_approval_stays_pending():
    db = SessionLocal()
    result = api.install(api.InstallRequest(
        name="plugin-pending", capability_yaml=SAMPLE_CAPABILITY_YAML.replace("greeter_plugin_agent", "plugin_pending"),
        template_md=SAMPLE_TEMPLATE_MD, installed_by="human_admin",
    ), db)
    activated = api.activate(result["plugin_id"], db)
    db.close()
    assert activated["status"] == "pending_approval"


def test_activate_writes_a_real_capability_yaml_to_disk(governance_url, assembly_url, plugin_capabilities_dir, monkeypatch):
    monkeypatch.setattr(installer, "PLUGIN_CAPABILITIES_DIR", str(plugin_capabilities_dir))
    db = SessionLocal()
    result = _install_and_approve(db, governance_url, "plugin-disk-1")
    activated = api.activate(result["plugin_id"], db)
    db.close()

    assert activated["status"] == "active"
    written = plugin_capabilities_dir / "plugin-disk-1" / "capability.yaml"
    assert written.exists()
    assert "plugin_disk_1" in written.read_text() or "plugin-disk-1" in written.read_text()
    assert (plugin_capabilities_dir / "plugin-disk-1" / "template.md").exists()


def test_activate_registers_the_template_with_assembly(governance_url, assembly_url, plugin_capabilities_dir, monkeypatch):
    monkeypatch.setattr(installer, "PLUGIN_CAPABILITIES_DIR", str(plugin_capabilities_dir))
    db = SessionLocal()
    result = _install_and_approve(db, governance_url, "plugin-tmpl-1")
    api.activate(result["plugin_id"], db)
    db.close()

    templates = httpx.get(f"{assembly_url}/prompt/templates").json()
    matching = [t for t in templates if t["agent_template_id"] == "plugin-tmpl-1"]
    # >= 1, not == 1: assembly's own DB is a separate, longer-lived
    # process not reset by this suite's clean_state fixture, so a
    # repeated local test run can accumulate more than one registration
    # attempt for the same template_id — the same reason every existing
    # agent's register.py checks for an already-"pending_approval"/"active"
    # entry before registering again, rather than assuming a clean slate.
    assert len(matching) >= 1
    assert matching[-1]["status"] == "pending_approval"  # template registration is its own separate gate (Phase 4)


def test_installed_plugin_capability_is_discovered_by_a_live_agents_service(
    governance_url, assembly_url, agents_url, plugin_capabilities_dir, monkeypatch,
):
    """
    The real end-to-end claim: an approved plugin's capability.yaml,
    written to PLUGIN_CAPABILITIES_DIR, is picked up by the agents
    service's own capability_registry.py — "adding new agents... without
    modifying core code" proven live, not just by inspection.
    """
    monkeypatch.setattr(installer, "PLUGIN_CAPABILITIES_DIR", str(plugin_capabilities_dir))
    db = SessionLocal()
    result = _install_and_approve(db, governance_url, "plugin-live-1")
    api.activate(result["plugin_id"], db)
    db.close()

    capabilities = httpx.get(f"{agents_url}/capabilities").json()["capabilities"]
    names = {c["agent_capability"] for c in capabilities}
    assert "plugin-live-1".replace("-", "_") in names or "plugin-live-1" in names


def test_disable_marks_plugin_disabled(governance_url):
    db = SessionLocal()
    result = _install_and_approve(db, governance_url, "plugin-disable-1")
    disabled = api.disable(result["plugin_id"], db)
    db.close()
    assert disabled["status"] == "disabled"


def test_report_error_below_threshold_does_not_disable(governance_url, assembly_url, plugin_capabilities_dir, monkeypatch):
    monkeypatch.setattr(installer, "PLUGIN_CAPABILITIES_DIR", str(plugin_capabilities_dir))
    db = SessionLocal()
    result = _install_and_approve(db, governance_url, "plugin-err-1")
    api.activate(result["plugin_id"], db)

    for _ in range(store.ERROR_THRESHOLD - 1):
        reported = api.report_error(result["plugin_id"], api.ReportErrorRequest(reason="transient"), db)
    db.close()

    assert reported["auto_disabled"] is False
    assert reported["status"] == "active"


def test_report_error_at_threshold_auto_disables(governance_url, assembly_url, plugin_capabilities_dir, monkeypatch):
    monkeypatch.setattr(installer, "PLUGIN_CAPABILITIES_DIR", str(plugin_capabilities_dir))
    db = SessionLocal()
    result = _install_and_approve(db, governance_url, "plugin-err-2")
    api.activate(result["plugin_id"], db)

    reported = None
    for _ in range(store.ERROR_THRESHOLD):
        reported = api.report_error(result["plugin_id"], api.ReportErrorRequest(reason="crash"), db)
    db.close()

    assert reported["auto_disabled"] is True
    assert reported["status"] == "disabled"
