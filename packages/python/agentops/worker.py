"""Bounded subprocess worker adapter using the AgentOps JSONL protocol."""
from __future__ import annotations

import json
import math
import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Sequence
from typing import Any
from uuid import uuid4


class WorkerExecutionError(RuntimeError):
    """A worker failed, timed out, exceeded a budget, or violated the protocol."""


class WorkerProcess:
    """Run one JSONL request in a fresh subprocess.

    This provides process separation only. Apply OS/container controls for a
    security sandbox, resource isolation, filesystem restrictions, and network policy.
    """

    PROTOCOL_VERSION = 1

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 30.0,
        max_input_bytes: int = 1_048_576,
        max_output_bytes: int = 1_048_576,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("command must contain non-empty strings")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")
        if any(isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0 for limit in (max_input_bytes, max_output_bytes)):
            raise ValueError("byte limits must be positive integers")
        self.command = tuple(command)
        self.timeout_seconds = float(timeout_seconds)
        self.max_input_bytes = max_input_bytes
        self.max_output_bytes = max_output_bytes

    def execute(self, tool_name: str, input: Any, *, request_id: str | None = None) -> Any:
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")
        identifier = request_id or str(uuid4())
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("request_id must be a non-empty string")
        try:
            line = json.dumps(
                {"protocol_version": self.PROTOCOL_VERSION, "request_id": identifier,
                 "tool_name": tool_name, "input": input},
                ensure_ascii=False, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8") + b"\n"
        except (TypeError, ValueError) as exc:
            raise WorkerExecutionError("worker request is not valid JSON") from exc
        if len(line) > self.max_input_bytes:
            raise WorkerExecutionError("worker input byte limit exceeded")

        try:
            process = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0,
                start_new_session=(os.name == "posix"),
                **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}),
            )
        except OSError as exc:
            raise WorkerExecutionError("worker could not be started") from exc

        chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=1)
        stop_reader = threading.Event()

        def enqueue_chunk(chunk: bytes | None) -> None:
            while not stop_reader.is_set():
                try:
                    chunks.put(chunk, timeout=0.05)
                    return
                except queue.Full:
                    continue

        def read_stdout() -> None:
            try:
                assert process.stdout is not None
                while not stop_reader.is_set():
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    enqueue_chunk(chunk)
            finally:
                enqueue_chunk(None)

        def write_stdin() -> None:
            try:
                assert process.stdin is not None
                process.stdin.write(line)
                process.stdin.close()
            except OSError:
                pass

        deadline = time.monotonic() + self.timeout_seconds
        reader = threading.Thread(target=read_stdout, daemon=True)
        writer = threading.Thread(target=write_stdin, daemon=True)
        reader.start()
        writer.start()
        try:
            output = bytearray()
            eof = False
            while not eof:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WorkerExecutionError("worker execution deadline exceeded")
                try:
                    chunk = chunks.get(timeout=remaining)
                except queue.Empty as exc:
                    raise WorkerExecutionError("worker execution deadline exceeded") from exc
                if chunk is None:
                    eof = True
                else:
                    if len(output) + len(chunk) > self.max_output_bytes:
                        raise WorkerExecutionError("worker output byte limit exceeded")
                    output.extend(chunk)
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise WorkerExecutionError("worker execution deadline exceeded") from exc
            if process.returncode != 0:
                raise WorkerExecutionError("worker exited unsuccessfully")
            if not output.endswith(b"\n") or output.count(b"\n") != 1:
                raise WorkerExecutionError("worker must return exactly one JSONL response")
            try:
                response = json.loads(output[:-1].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise WorkerExecutionError("worker returned invalid JSON") from exc
            if not isinstance(response, dict) or response.get("protocol_version") != self.PROTOCOL_VERSION or response.get("request_id") != identifier or "result" not in response:
                raise WorkerExecutionError("worker response does not match the request protocol")
            return response["result"]
        except (BrokenPipeError, OSError) as exc:
            raise WorkerExecutionError("worker communication failed") from exc
        finally:
            stop_reader.set()
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif os.name == "nt":
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=5, check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass
                if process.poll() is None:
                    process.kill()
            elif process.poll() is None:
                process.kill()
            process.wait()
            reader.join(timeout=1)
            writer.join(timeout=1)
            if process.stdout is not None:
                process.stdout.close()
