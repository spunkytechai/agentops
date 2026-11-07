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

If omitted, the executor creates a trace and span ID. The context is W3C Trace Context identifier-compatible, but the SDK does not currently parse or emit `traceparent` headers or export OTLP.

Use `AgentRegistry(store=SqliteAgentRegistryStore("agentops.sqlite3"))` to persist immutable agent versions across restarts. The composite key rejects duplicate `(agent_id, version)` pairs. Close the store during application shutdown.

Use `ApprovalManager(store=SqliteApprovalStore("agentops.sqlite3"))` to persist approval requests across restarts. Close the store during application shutdown. Use a shared SQLite file only on storage with reliable SQLite locking.

The async executor cancels the coroutine when its timeout expires. Cancellation is cooperative; integrations must propagate cancellation and external side effects may already have occurred. The default recorder stores metadata only; tool arguments and results are excluded.
