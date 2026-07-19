def agent_git_identity(agent_capability: str) -> dict:
    """
    A distinct author/committer identity per agent capability, injected as
    explicit env vars for the sandboxed `git commit` call (git prioritizes
    GIT_AUTHOR_*/GIT_COMMITTER_* env vars over any user.name/email in
    config) — never the sandboxed process's ambient git config, which
    would otherwise resolve to whatever human operator's global identity
    happens to be configured on the host. Real, cryptographic GPG signing
    (per the Phase 6 doc) needs a signing key this environment doesn't
    have configured; this is the honest baseline that's achievable
    without generating one — distinguishable in `git log`, not yet
    cryptographically verifiable.
    """
    display = agent_capability.replace("_", " ").title()
    email = f"agent+{agent_capability}@ai-orchestration.local"
    return {
        "GIT_AUTHOR_NAME": display, "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": display, "GIT_COMMITTER_EMAIL": email,
    }


def build_trailer(task_id: str, agent_capability: str, context_id: str, reasoning_execution_id: str) -> str:
    """
    Structured git trailer (RFC 822-style, same convention as Signed-off-by/
    Co-authored-by) so any commit traces back to the exact reasoning trace
    and context that produced it (Phase 6 doc, Git Manager responsibilities).
    """
    lines = [f"Task-Id: {task_id}", f"Agent-Capability: {agent_capability}"]
    if context_id:
        lines.append(f"Context-Id: {context_id}")
    if reasoning_execution_id:
        lines.append(f"Reasoning-Execution-Id: {reasoning_execution_id}")
    return "\n".join(lines)


def build_commit_message(summary: str, task_id: str, agent_capability: str, context_id: str = None, reasoning_execution_id: str = None, body: str = None) -> str:
    parts = [summary.strip()]
    if body:
        parts.append(body.strip())
    parts.append(build_trailer(task_id, agent_capability, context_id, reasoning_execution_id))
    return "\n\n".join(parts) + "\n"
