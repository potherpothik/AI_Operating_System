import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

SANDBOX_ROOT = Path(os.environ.get("SANDBOX_ROOT", "/tmp/ai_os_sandbox")).resolve()
SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "python:3.12-slim")
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("SANDBOX_TIMEOUT_SECONDS", "60"))

# Only these env vars pass through to a sandboxed process — never the
# full parent environment, which could otherwise leak secrets/credentials
# from this service's own process into agent-triggered commands.
_SAFE_ENV_KEYS = {"PATH", "HOME", "LANG", "LC_ALL", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"}

# Tracks in-flight executions so /shell/{id}/kill can act on a genuinely
# running process, not just a stored final record.
_ACTIVE: dict[str, subprocess.Popen] = {}


@dataclass
class SandboxResult:
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    sandbox_id: str
    backend: str
    timed_out: bool = False


class WorkingDirNotAllowed(Exception):
    pass


class SandboxCreationError(Exception):
    pass


def _validate_working_dir(working_dir: str) -> Path:
    resolved = Path(working_dir).resolve()
    try:
        resolved.relative_to(SANDBOX_ROOT)
    except ValueError:
        raise WorkingDirNotAllowed(
            f"working_dir {resolved} is outside SANDBOX_ROOT {SANDBOX_ROOT} — "
            f"refusing rather than executing against an arbitrary path"
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _safe_env() -> dict:
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}


def docker_available() -> bool:
    return shutil.which("docker") is not None


class SubprocessSandbox:
    """
    Fallback used when Docker isn't available (confirmed absent in this
    environment — no `docker` binary at all). Real, tested isolation
    properties: working-directory confinement to SANDBOX_ROOT, a minimal
    explicit env allowlist (not the parent process's full environment),
    a hard timeout, and CPU/memory resource limits via the `resource`
    module. NOT real filesystem or network isolation — a command can
    still read/write outside working_dir via absolute paths, and network
    access isn't blocked. The command allowlist (allowlist.py) is the
    actual defense against that gap: only pre-approved patterns ever
    reach this function at all. Same "real but reduced, honestly
    labeled" pattern as Phase 3's HashingEmbedding fallback.
    """

    backend_name = "subprocess"

    def run(self, command: str, args: list[str], working_dir: str, mode: str, timeout_seconds: int = None, network: bool = False, sandbox_id: str = None, extra_env: dict = None) -> SandboxResult:
        resolved_dir = _validate_working_dir(working_dir)
        timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        sandbox_id = sandbox_id or str(uuid.uuid4())

        def _limit_resources():
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            # Deliberately NOT setting RLIMIT_NPROC here: confirmed via live
            # testing that it's a per-UID, system-wide limit, not scoped to
            # this subprocess's own tree — it broke `git push`'s legitimate
            # fork of git-receive-pack because the host's ambient process
            # count (everything else this user is running) already ate into
            # the budget, with "fatal: unable to fork" from a command that
            # did nothing wrong. Real per-execution process-count limiting
            # needs cgroups (Docker's --pids-limit), which is what
            # DockerSandbox is for — this fallback settles for CPU/memory
            # limits it can actually scope correctly, rather than a process
            # limit that looks like isolation but isn't.

        env = _safe_env()
        if extra_env:
            env.update(extra_env)

        start = time.monotonic()
        try:
            proc = subprocess.Popen(
                [command] + list(args),
                cwd=str(resolved_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=_limit_resources,
            )
        except FileNotFoundError as e:
            raise SandboxCreationError(f"command {command!r} not found: {e}")

        _ACTIVE[sandbox_id] = proc
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            exit_code = None
            timed_out = True
        finally:
            _ACTIVE.pop(sandbox_id, None)

        duration_ms = int((time.monotonic() - start) * 1000)
        return SandboxResult(
            exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=duration_ms,
            sandbox_id=sandbox_id, backend=self.backend_name, timed_out=timed_out,
        )

    def kill(self, sandbox_id: str) -> bool:
        proc = _ACTIVE.get(sandbox_id)
        if not proc:
            return False
        proc.kill()
        return True


class DockerSandbox:
    """
    Production path: container-per-execution, no network by default,
    read-only mount unless mode=mutating, non-root, resource-limited.
    Built against the real `docker` CLI contract but UNVERIFIED in this
    environment — Docker isn't installed here (confirmed: no `docker`
    binary on PATH). Same honesty pattern as Phase 3's untested
    OllamaEmbedding: written to the real interface, not exercised live,
    swappable via SANDBOX_BACKEND without touching calling code.
    """

    backend_name = "docker"

    def run(self, command: str, args: list[str], working_dir: str, mode: str, timeout_seconds: int = None, network: bool = False, sandbox_id: str = None, extra_env: dict = None) -> SandboxResult:
        resolved_dir = _validate_working_dir(working_dir)
        timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        sandbox_id = sandbox_id or str(uuid.uuid4())
        mount_flag = "rw" if mode == "mutating" else "ro"

        docker_args = [
            "docker", "run", "--rm",
            "--name", f"ai-os-exec-{sandbox_id}",
            "--memory=512m", "--cpus=1",
            "--pids-limit=64",  # cgroup-scoped to this container only — correctly isolated, unlike RLIMIT_NPROC's per-host-UID scope in the subprocess fallback
            "--user", "1000:1000",
            "--workdir", "/workspace",
            "-v", f"{resolved_dir}:/workspace:{mount_flag}",
        ]
        if not network:
            docker_args += ["--network", "none"]
        for k, v in (extra_env or {}).items():
            docker_args += ["-e", f"{k}={v}"]
        docker_args += [SANDBOX_IMAGE, command] + list(args)

        start = time.monotonic()
        try:
            proc = subprocess.Popen(docker_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except FileNotFoundError as e:
            raise SandboxCreationError(f"docker not available: {e}")

        _ACTIVE[sandbox_id] = proc
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", f"ai-os-exec-{sandbox_id}"], capture_output=True)
            stdout, stderr = proc.communicate()
            exit_code = None
            timed_out = True
        finally:
            _ACTIVE.pop(sandbox_id, None)

        duration_ms = int((time.monotonic() - start) * 1000)
        return SandboxResult(
            exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=duration_ms,
            sandbox_id=sandbox_id, backend=self.backend_name, timed_out=timed_out,
        )

    def kill(self, sandbox_id: str) -> bool:
        proc = _ACTIVE.get(sandbox_id)
        if not proc:
            return False
        subprocess.run(["docker", "kill", f"ai-os-exec-{sandbox_id}"], capture_output=True)
        proc.kill()
        return True


def get_sandbox():
    backend = os.environ.get("SANDBOX_BACKEND")
    if backend == "docker":
        return DockerSandbox()
    if backend == "subprocess":
        return SubprocessSandbox()
    return DockerSandbox() if docker_available() else SubprocessSandbox()
