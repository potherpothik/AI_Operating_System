from assembly.clients import get_reasoning_engine_config

_TIERS = ["public", "internal", "confidential"]


def ceiling_for_model(target_model: str) -> dict:
    """
    Local models get the project's normal ceiling (confidential — the
    highest tier this reference implementation defines). Anything not
    recognized as local defaults to public, the most restrictive tier,
    unless Config Manager's external_model_allowed flag says otherwise —
    and even then, capped at internal, not confidential: a blanket
    "external allowed" flag is not the same as approval to release
    confidential content externally, which still needs its own explicit
    approval per task (Phase 6's Human Approval Layer pattern).
    """
    config = get_reasoning_engine_config()
    local_models = {m for m in (config.get("default_local_model"), config.get("fallback_local_model")) if m}

    is_local = target_model in local_models
    if is_local:
        return {"ceiling": "confidential", "reason": f"{target_model} is a configured local model"}

    external_allowed = config.get("external_model_allowed") in (True, "true", "True")
    if external_allowed:
        return {"ceiling": "internal", "reason": f"{target_model} is external; external_model_allowed=true caps at internal, not confidential"}

    return {"ceiling": "public", "reason": f"{target_model} is not a recognized local model and external_model_allowed is false"}


def tier_index(tier: str) -> int:
    return _TIERS.index(tier) if tier in _TIERS else 0
