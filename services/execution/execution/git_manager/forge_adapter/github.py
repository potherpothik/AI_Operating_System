import os
import httpx


class GitHubNotConfigured(Exception):
    pass


class GitHubAdapter:
    """
    Built against GitHub's real REST API contract (POST /repos/{owner}/
    {repo}/pulls). UNVERIFIED against real GitHub in this environment —
    no `gh` CLI and no GITHUB_TOKEN configured here, and deliberately not
    exercised against the actual project repo from an automated test run
    even if a token were available (opening a real PR is a publishing
    action, not something to do without the human asking for it
    specifically). Same honesty pattern as Phase 3's untested
    OllamaEmbedding and Phase 6's untested DockerSandbox — written to the
    real interface, swappable, not silently assumed to work.
    """

    def __init__(self, token: str = None, api_base: str = "https://api.github.com"):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.api_base = api_base

    def open_pr(self, repo: str, base: str, head: str, title: str, body: str) -> dict:
        if not self.token:
            raise GitHubNotConfigured("GITHUB_TOKEN not set — cannot open a real pull request")
        resp = httpx.post(
            f"{self.api_base}/repos/{repo}/pulls",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"},
            json={"title": title, "head": head, "base": base, "body": body},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return {"url": data["html_url"], "number": data["number"]}
