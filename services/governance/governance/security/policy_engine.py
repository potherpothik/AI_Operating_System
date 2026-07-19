import fnmatch
from pathlib import Path
import yaml


class PolicyEngine:
    """
    Embedded rule evaluator (Phase 1's noted starting point before an
    OPA swap-in, if policy complexity grows). Loads every *.yaml file
    in the policy directory at startup.
    """

    def __init__(self, policy_dir: str = None):
        self.policy_dir = Path(policy_dir or Path(__file__).parent / "policies")
        self.rules: list[dict] = []
        self._load()

    def _load(self):
        self.rules = []
        for f in sorted(self.policy_dir.glob("*.yaml")):
            data = yaml.safe_load(f.read_text()) or {}
            for role, rules in data.get("roles", {}).items():
                for rule in rules:
                    self.rules.append(
                        {
                            "role": role,
                            "action_pattern": rule["action"],
                            "resource_pattern": rule.get("resource", "*"),
                            "effect": rule["effect"],
                        }
                    )

    def authorize(self, role: str, action: str, resource: str) -> dict:
        """
        Fail closed: no matching rule -> deny. Never raises past this
        point without the caller (security/api.py) converting the
        exception into a deny as well.
        """
        matches = [
            r
            for r in self.rules
            if r["role"] == role
            and fnmatch.fnmatch(action, r["action_pattern"])
            and fnmatch.fnmatch(resource, r["resource_pattern"])
        ]
        if not matches:
            return {"decision": "deny", "reason": "no matching policy — fail closed"}

        effects = {m["effect"] for m in matches}
        # Most restrictive match wins when several rules apply.
        if "deny" in effects:
            return {"decision": "deny", "reason": "explicit deny rule matched"}
        if "require_approval" in effects:
            return {"decision": "require_approval", "reason": "matched a require_approval rule"}
        return {"decision": "allow", "reason": "matched an allow rule"}

    def policy_for_role(self, role: str) -> list[dict]:
        return [r for r in self.rules if r["role"] == role]
