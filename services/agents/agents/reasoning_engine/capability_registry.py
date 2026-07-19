from pathlib import Path
import yaml
from sqlalchemy.orm import Session

from agents.reasoning_engine.models import AgentCapabilityDef

AGENTS_DIR = Path(__file__).parent.parent


def _discover_capability_files():
    """Any agents/<name>/capability.yaml under this package — new agents register themselves just by existing here."""
    return sorted(AGENTS_DIR.glob("*/capability.yaml"))


def load_all(db: Session):
    """Idempotent upsert from capability.yaml files — the on-disk file is the source of truth, DB is a queryable mirror."""
    loaded = []
    for path in _discover_capability_files():
        data = yaml.safe_load(path.read_text())
        cap = data["capability"]
        existing = db.query(AgentCapabilityDef).filter(AgentCapabilityDef.agent_capability == cap).first()
        if existing:
            existing.allowed_actions = data.get("allowed_actions", [])
            existing.forbidden_actions = data.get("forbidden_actions", [])
            existing.requires_approval = data.get("requires_approval", [])
            existing.classification_ceiling = data.get("classification_ceiling", "internal")
            existing.template_id = data.get("template_id", cap)
        else:
            db.add(AgentCapabilityDef(
                agent_capability=cap,
                allowed_actions=data.get("allowed_actions", []),
                forbidden_actions=data.get("forbidden_actions", []),
                requires_approval=data.get("requires_approval", []),
                classification_ceiling=data.get("classification_ceiling", "internal"),
                template_id=data.get("template_id", cap),
            ))
        loaded.append(cap)
    db.commit()
    return loaded


def get_capability(db: Session, agent_capability: str) -> AgentCapabilityDef | None:
    return db.query(AgentCapabilityDef).filter(AgentCapabilityDef.agent_capability == agent_capability).first()


class UnknownCapability(Exception):
    pass


class ForbiddenAction(Exception):
    pass


def local_precheck(cap_def: AgentCapabilityDef, action: str) -> str:
    """
    Fast, local, deny-by-default check before ever calling Security Layer —
    defense in depth per Phase 5 doc: a model's declared action is untrusted
    input and must be re-validated against what the agent is actually
    permitted to do, not trusted just because the model said so.
    Returns 'allow' | 'require_approval' | 'deny'.
    """
    if action in cap_def.forbidden_actions:
        return "deny"
    if action not in cap_def.allowed_actions:
        return "deny"  # deny-by-default: not explicitly allowed means not allowed
    if action in cap_def.requires_approval:
        return "require_approval"
    return "allow"
