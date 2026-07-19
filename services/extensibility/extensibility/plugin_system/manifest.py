import yaml

# Every action name any existing role in governance/security/policies/default.yaml
# is actually granted, across every phase — the set a plugin's declared
# required_permissions is checked against. Not derived dynamically from
# governance at install time (that would make installation depend on a
# live network call succeeding just to validate a manifest); kept here
# as the deliberately explicit, version-controlled source of truth for
# what's "verifiable," mirroring how Shell Executor's allowlists are
# themselves explicit files, not inferred.
KNOWN_PERMISSIONS = {
    "task.create", "task.read", "task.update_status",
    "shell.execute", "git.branch", "git.commit", "git.diff", "git.push", "git.open_mr",
    "db.read", "db.dry_run", "db.propose_write", "db.propose_migration", "db.write", "db.migrate",
    "code_analysis.raw_source_request", "mcp.invoke",
}


class InvalidManifest(Exception):
    pass


def validate_permissions(required_permissions: list[str]) -> list[str]:
    """Returns the subset of required_permissions NOT in the known set —
    empty means the manifest is clean. "A manifest claiming permissions
    it can't be verified to need is rejected at install time, not
    silently granted" (doc, Plugin System failure handling)."""
    return [p for p in required_permissions if p not in KNOWN_PERMISSIONS]


def validate_capability_yaml(capability_yaml: str) -> dict:
    """
    Parses and structurally validates the plugin's capability.yaml —
    same required shape every built-in agent's own file has
    (capability, allowed_actions, forbidden_actions, requires_approval,
    classification_ceiling). Raises InvalidManifest with a specific
    reason rather than letting a malformed file surface as an opaque
    YAML parse error deep inside capability_registry.py later.
    """
    try:
        data = yaml.safe_load(capability_yaml)
    except yaml.YAMLError as e:
        raise InvalidManifest(f"capability.yaml is not valid YAML: {e}")

    if not isinstance(data, dict):
        raise InvalidManifest("capability.yaml must be a YAML mapping")
    if "capability" not in data or not isinstance(data["capability"], str):
        raise InvalidManifest("capability.yaml must declare a string 'capability' name")
    for key in ("allowed_actions", "forbidden_actions", "requires_approval"):
        if key in data and not isinstance(data[key], list):
            raise InvalidManifest(f"capability.yaml's {key!r} must be a list")
    return data
