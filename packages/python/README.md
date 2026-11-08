# AgentOps Python SDK

Dependency-free contracts for tool authorization and execution-event recording. Durable approval and agent-registry storage use Python's standard-library `sqlite3` module.

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m unittest discover -s packages/python/tests -v
```

```python
import asyncio
from agentops import InMemoryRecorder, ToolExecutor, ToolPolicy

async def main():
    recorder = InMemoryRecorder()
    executor = ToolExecutor(ToolPolicy(frozenset({"weather.lookup"})), recorder)
    result = await executor.execute_async(
        "weather.lookup",
        fetch_weather,
        run_id="weather-run-1",
        timeout_seconds=5,
    )
    print(result, [event.event_type for event in recorder.events])

asyncio.run(main())
```

Pass a `TraceContext` to correlate lifecycle events with a parent operation:

```python
from agentops import TraceContext

parent = TraceContext.create()
child = TraceContext.create(parent)
result = executor.execute(
    "reports.read", fetch_report, run_id="report-run-1", trace_context=child
)
```

If omitted, the executor creates a trace and span ID. Export completed tool spans using an injected HTTP transport:


```python
import urllib.request
from agentops import OtlpHttpSpanExporter, ToolExecutor, ToolPolicy

def send_otlp(url, headers, body):
    request = urllib.request.Request(url, data=body.encode(), headers=dict(headers), method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"OTLP collector returned {response.status}")

exporter = OtlpHttpSpanExporter("http://localhost:4318", send_otlp, max_attribute_bytes=256)
policy = ToolPolicy(frozenset({"reports.read"}))
executor = ToolExecutor(policy, exporter)
# Flush from a worker or controlled shutdown hook.
exporter.flush()
```

Exported string attributes are limited to 256 UTF-8 bytes by default. Spans with oversized metadata or invalid trace IDs are dropped and counted in `dropped_spans`. Keep run IDs and tool names free of secrets and personal data; configure collector authentication in the injected transport, not in the URL.

Use `AgentRegistry(store=SqliteAgentRegistryStore("agentops.sqlite3"))` to persist immutable agent versions across restarts. The composite key rejects duplicate `(agent_id, version)` pairs. Close the store during application shutdown.

Use `ApprovalManager(store=SqliteApprovalStore("agentops.sqlite3"))` to persist approval requests across restarts. Close the store during application shutdown. Use a shared SQLite file only on storage with reliable SQLite locking.

The async executor cancels the coroutine when its timeout expires. Cancellation is cooperative; integrations must propagate cancellation and external side effects may already have occurred. The default recorder stores metadata only; tool arguments and results are excluded.

## Evaluation

```python
from agentops import EvaluationCase, EvaluationSuite, ExactMatchMetric, NumericToleranceMetric, compare_evaluations

suite = EvaluationSuite("answer-quality", [
    EvaluationCase("greeting", {"prompt": "hello"}, "Hello!", weight=2),
    EvaluationCase("temperature", {"prompt": "temperature"}, 21.0),
], metric=ExactMatchMetric())
report = suite.run(lambda item: "Hello!" if item["prompt"] == "hello" else 21.0)
print(report.weighted_score, report.pass_rate)

# For numeric outputs, use NumericToleranceMetric(absolute_tolerance=0.5).
# Compare a later report with a stored baseline:
# regression = compare_evaluations(baseline, report, max_score_drop=0.02)
```

Use `await suite.run_async(async_operation)` for sequential asynchronous operations. The engine does not call a model provider or persist datasets/reports.

## Persist evaluation runs and baselines

```python
from agentops import EvaluationRunStore, SqliteEvaluationRunStore

store = SqliteEvaluationRunStore("agentops-evaluations.sqlite3")
run = store.save(report, run_id="answer-quality-2026-11-08")
store.set_baseline("answer-quality", run.run_id)
baseline = store.get_baseline("answer-quality")
# Close the store during application shutdown.
store.close()
```

The SQLite store saves only reports and per-case scores, not evaluation inputs or model outputs. The in-memory implementation is available as `InMemoryEvaluationRunStore` for tests and local development.
## Isolated subprocess worker

```python
import sys
from agentops import WorkerProcess

worker = WorkerProcess(
    [sys.executable, "worker_entrypoint.py"],
    timeout_seconds=5,
    max_input_bytes=256_000,
    max_output_bytes=256_000,
)
result = worker.execute("reports.summarize", {"report_id": "r-123"})
```

The child reads one JSON line from stdin and writes one JSON line to stdout. It must echo protocol_version and request_id, and include result. The adapter launches a fresh process group per call on POSIX and terminates the group on completion, deadline, or output overflow. On Windows it attempts recursive process-tree termination with `taskkill /T /F`, then reaps the direct child. This is process separation, not a sandbox; apply OS/container filesystem, network, privilege, CPU, memory, and PID controls for untrusted code.

## Docker-isolated worker

Build the example image from the repository root:

```bash
docker build -f examples/Dockerfile.worker -t agentops-example-worker:local .
```

```python
from agentops import DockerWorker

worker = DockerWorker(
    "agentops-example-worker:local",
    timeout_seconds=10,
    memory_limit_bytes=512 * 1024 * 1024,
    cpu_limit=1.5,
    pids_limit=32,
    max_concurrent_workers=4,
)
result = worker.execute("identity.echo", {"message": "hello"})
```

The image must be preloaded locally. Each call starts a fresh non-root container with no network or host mounts, a read-only root filesystem, dropped capabilities, no-new-privileges, bounded CPU/memory/PIDs, and a restricted temporary filesystem. Protocol byte limits and deadlines remain active. The Docker daemon and host kernel remain trusted; this profile is not escape-proof.

Each DockerWorker instance limits concurrent containers to four by default. Set `max_concurrent_workers` to tune the per-instance concurrency cap; calls waiting for a slot fail when the configured execution deadline expires. This is an in-process limit, not a cluster-wide quota.