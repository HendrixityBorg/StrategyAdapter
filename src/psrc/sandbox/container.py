from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from psrc.contract.errors import ContractError, ContractViolation, ErrorCode, ErrorStage
from psrc.contract.models import ResourcePolicy


@dataclass(frozen=True)
class ContainerMounts:
    data: Path
    artifacts: Path
    reports: Path


@dataclass(frozen=True)
class SandboxExecutionResult:
    returncode: int
    stdout: str
    stderr: str
    attested: bool = True


class DockerSandbox:
    """Builds a fail-closed Docker invocation for untrusted strategy execution."""

    image = "psrc-verifier:local"

    @staticmethod
    def available() -> bool:
        return shutil.which("docker") is not None

    @classmethod
    def require_available(cls, *, run_id: str, strategy_id: str) -> None:
        if not cls.available():
            cls._fail(
                run_id=run_id,
                strategy_id=strategy_id,
                code=ErrorCode.SANDBOX_UNAVAILABLE,
                message="Strict-container execution was requested but Docker is unavailable",
                details={"required_backend": "docker", "fallback_used": False},
            )

    @classmethod
    def command(
        cls,
        *,
        policy: ResourcePolicy,
        mounts: ContainerMounts,
        command: tuple[str, ...],
    ) -> tuple[str, ...]:
        uid = os.getuid()
        gid = os.getgid()
        container_user = f"{uid}:{gid}" if uid != 0 else "65532:65532"
        return (
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(policy.process_limit),
            "--memory",
            f"{policy.memory_mb}m",
            "--cpus",
            "1.0",
            "--user",
            container_user,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--mount",
            f"type=bind,src={mounts.data.resolve()},dst=/psrc/data,readonly",
            "--mount",
            f"type=bind,src={mounts.artifacts.resolve()},dst=/psrc/artifacts",
            "--mount",
            f"type=bind,src={mounts.reports.resolve()},dst=/psrc/reports",
            "--env",
            "PSRC_STRICT_SANDBOX=1",
            "--env",
            "PSRC_SANDBOX_ATTESTATION=strict-container-v1",
            cls.image,
            *command,
        )

    @staticmethod
    def _container_marker_present() -> bool:
        return Path("/.dockerenv").is_file() or Path("/run/.containerenv").is_file()

    @staticmethod
    def _runtime_controls_present() -> bool:
        try:
            interfaces = {path.name for path in Path("/sys/class/net").iterdir()}
            status = {
                key: value.strip()
                for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines()
                if ":" in line
                for key, value in (line.split(":", maxsplit=1),)
            }
            mounts = [line.split() for line in Path("/proc/mounts").read_text().splitlines()]
            root_options = next(parts[3].split(",") for parts in mounts if parts[1] == "/")
            tmp_options = next(parts[3].split(",") for parts in mounts if parts[1] == "/tmp")
            effective_capabilities = int(status.get("CapEff", "1"), 16)
        except (OSError, StopIteration, IndexError, ValueError):
            return False
        return (
            interfaces <= {"lo"}
            and effective_capabilities == 0
            and status.get("NoNewPrivs") == "1"
            and "ro" in root_options
            and {"noexec", "nosuid", "nodev"} <= set(tmp_options)
        )

    @classmethod
    def current_process_attested(cls) -> bool:
        return (
            os.environ.get("PSRC_STRICT_SANDBOX") == "1"
            and os.environ.get("PSRC_SANDBOX_ATTESTATION") == "strict-container-v1"
            and os.geteuid() != 0
            and cls._container_marker_present()
            and cls._runtime_controls_present()
        )

    @classmethod
    def execute(
        cls,
        *,
        run_id: str,
        strategy_id: str,
        policy: ResourcePolicy,
        mounts: ContainerMounts,
        command: tuple[str, ...],
    ) -> SandboxExecutionResult:
        cls.require_available(run_id=run_id, strategy_id=strategy_id)
        invocation = cls.command(policy=policy, mounts=mounts, command=command)
        try:
            completed = subprocess.run(
                invocation,
                check=False,
                capture_output=True,
                text=True,
                timeout=policy.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            cls._fail(
                run_id=run_id,
                strategy_id=strategy_id,
                code=ErrorCode.SANDBOX_TIMEOUT,
                message="Strict-container strategy exceeded its declared timeout",
                details={"timeout_seconds": policy.timeout_seconds, "fallback_used": False},
            )
        if completed.returncode != 0:
            exhausted = completed.returncode in {137, -9}
            cls._fail(
                run_id=run_id,
                strategy_id=strategy_id,
                code=(
                    ErrorCode.SANDBOX_RESOURCE_EXHAUSTED
                    if exhausted
                    else ErrorCode.SANDBOX_EXECUTION_FAILED
                ),
                message="Strict-container strategy process failed",
                details={
                    "returncode": completed.returncode,
                    "stderr_tail": completed.stderr[-2000:],
                    "fallback_used": False,
                },
            )
        return SandboxExecutionResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    @staticmethod
    def _fail(
        *,
        run_id: str,
        strategy_id: str,
        code: ErrorCode,
        message: str,
        details: dict[str, object],
    ) -> NoReturn:
        raise ContractViolation(
            ContractError(
                run_id=run_id,
                stage=ErrorStage.SANDBOX,
                code=code,
                message=message,
                strategy_id=strategy_id,
                details=details,
            )
        )
