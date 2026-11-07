# AgentOps Python SDK

Dependency-free contracts for tool authorization and execution-event recording.

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

The async executor cancels the coroutine when its timeout expires. Cancellation is cooperative; integrations must propagate cancellation and external side effects may already have occurred. The default recorder stores metadata only; tool arguments and results are excluded.
