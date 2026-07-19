import os
from pathlib import Path

from extensibility import clients

# Must point at the SAME directory the agents service's own
# PLUGIN_CAPABILITIES_DIR env var names (capability_registry.py, Phase
# 12 addition) — an operational convention, not enforced automatically
# across two separate processes, same class of shared-path requirement
# Phase 6/7's SANDBOX_ROOT already established.
PLUGIN_CAPABILITIES_DIR = os.environ.get("PLUGIN_CAPABILITIES_DIR", "/tmp/ai_os_plugins")

DEFAULT_EXPECTED_OUTPUT_SCHEMA = {
    "reasoning": "str",
    "answer_or_proposal": "str",
    "confidence": "float",
    "provenance": "list",
    "risk_classification": "str",
    "delegate_to": "optional_str",
    "action": "str",
}


def materialize(plugin) -> dict:
    """
    The two real steps that make an APPROVED plugin actually runnable —
    called once, on activation, never before approval:
    1. Write capability.yaml (+ template.md, for a human inspecting the
       plugin directory) to a real file the agents service's
       capability_registry.py already knows to glob.
    2. Register the template with Prompt Builder (Phase 4) — itself
       still its own separately-approval-gated step, same as every
       built-in agent's register.py already goes through; a plugin
       gets no shortcut around that second gate.
    Then best-effort triggers a hot reload so the new capability is
    usable immediately rather than only after the agents service's next
    restart.
    """
    plugin_dir = Path(PLUGIN_CAPABILITIES_DIR) / plugin.name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "capability.yaml").write_text(plugin.capability_yaml)
    (plugin_dir / "template.md").write_text(plugin.template_md)

    schema = plugin.expected_output_schema or DEFAULT_EXPECTED_OUTPUT_SCHEMA
    template_result = clients.register_template(plugin.name, plugin.template_md, schema, created_by=f"plugin:{plugin.name}")
    reload_result = clients.reload_agent_capabilities()

    return {
        "capability_yaml_path": str(plugin_dir / "capability.yaml"),
        "template_registration": template_result,
        "agents_reload": reload_result,
    }
