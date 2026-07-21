from control_ui import clients


def build(actor: str) -> dict:
    """
    One-shot boot payload — real reachability of every peer this UI
    depends on, checked live, not assumed. `capability_views` is
    honestly empty: extensibility has no view-manifest convention yet
    (Phase 24 doc §1 names this as a gap-fill row; not built this
    session — see services/control-ui/README.md).
    """
    return {
        "actor": actor,
        "services": {
            "governance": clients.is_reachable(clients.SECURITY_LAYER_URL),
            "platform_spine": clients.is_reachable(clients.PLATFORM_URL),
            "observability": clients.is_reachable(clients.OBSERVABILITY_URL),
        },
        "capability_views": [],
    }
