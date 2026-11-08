"""Hardened Docker-backed worker orchestration."""
from __future__ import annotations

import math
import subprocess
import threading
from typing import Any
from uuid import uuid4

from .worker import WorkerExecutionError, WorkerProcess


class DockerWorker:
    """Execute one AgentOps JSONL request in a constrained Docker container.

    The Docker daemon and host kernel remain trusted. This profile is defense
    in depth, not a guarantee against container escapes or kernel vulnerabilities.
    """

    def __init__(
        self,
        image: str,
        *,
        docker_executable: str = "docker",
        timeout_seconds: float = 30.0,
        max_input_bytes: int = 1_048_576,
        max_output_bytes: int = 1_048_576,
        memory_limit_bytes: int = 268_435_456,
        cpu_limit: float = 1.0,
        pids_limit: int = 64,
        tmpfs_size_bytes: int = 16_777_216,
        max_concurrent_workers: int = 4,
    ) -> None:
        if not isinstance(image, str) or not image or image.startswith("-") or "\x00" in image or any(ch.isspace() for ch in image):
            raise ValueError("image must be a non-empty Docker image reference without whitespace")
        if not isinstance(docker_executable, str) or not docker_executable or "\x00" in docker_executable:
            raise ValueError("docker_executable must be non-empty")
        if isinstance(memory_limit_bytes, bool) or not isinstance(memory_limit_bytes, int) or memory_limit_bytes <= 0:
            raise ValueError("memory_limit_bytes must be a positive integer")
        if isinstance(pids_limit, bool) or not isinstance(pids_limit, int) or pids_limit <= 0:
            raise ValueError("pids_limit must be a positive integer")
        if isinstance(tmpfs_size_bytes, bool) or not isinstance(tmpfs_size_bytes, int) or tmpfs_size_bytes <= 0:
            raise ValueError("tmpfs_size_bytes must be a positive integer")
        if isinstance(max_concurrent_workers, bool) or not isinstance(max_concurrent_workers, int) or max_concurrent_workers <= 0:
            raise ValueError("max_concurrent_workers must be a positive integer")
        if isinstance(cpu_limit, bool) or not isinstance(cpu_limit, (int, float)) or not math.isfinite(cpu_limit) or cpu_limit <= 0:
            raise ValueError("cpu_limit must be positive and finite")
        self.image = image
        self.docker_executable = docker_executable
        self.timeout_seconds = timeout_seconds
        self.max_input_bytes = max_input_bytes
        self.max_output_bytes = max_output_bytes
        self.memory_limit_bytes = memory_limit_bytes
        self.cpu_limit = float(cpu_limit)
        self.pids_limit = pids_limit
        self.tmpfs_size_bytes = tmpfs_size_bytes
        self.max_concurrent_workers = max_concurrent_workers
        self._slots = threading.BoundedSemaphore(max_concurrent_workers)

    def _run_args(self, container_name: str) -> list[str]:
        return [
            "run", "--rm", "--interactive", "--pull=never", f"--name={container_name}",
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user=65532:65532",
            f"--memory={self.memory_limit_bytes}",
            f"--memory-swap={self.memory_limit_bytes}",
            f"--cpus={self.cpu_limit:g}", f"--pids-limit={self.pids_limit}",
            f"--tmpfs=/tmp:rw,noexec,nosuid,nodev,size={self.tmpfs_size_bytes}",
            self.image,
        ]

    def execute(self, tool_name: str, input: Any, *, request_id: str | None = None) -> Any:
        if not self._slots.acquire(timeout=self.timeout_seconds):
            raise WorkerExecutionError("worker concurrency wait deadline exceeded")
        try:
            return self._execute_one(tool_name, input, request_id=request_id)
        finally:
            self._slots.release()

    def _execute_one(self, tool_name: str, input: Any, *, request_id: str | None = None) -> Any:
        container_name = f"agentops-worker-{uuid4().hex}"
        worker = WorkerProcess(
            [self.docker_executable, *self._run_args(container_name)],
            timeout_seconds=self.timeout_seconds,
            max_input_bytes=self.max_input_bytes,
            max_output_bytes=self.max_output_bytes,
        )
        try:
            return worker.execute(tool_name, input, request_id=request_id)
        finally:
            # --rm handles normal exit; explicit removal also covers client-side
            # termination on timeout or output overflow.
            try:
                subprocess.run(
                    [self.docker_executable, "rm", "--force", container_name],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=5, check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
