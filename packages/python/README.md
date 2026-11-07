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
from agentops import InMemoryRecorder, ToolExecutor, ToolPolicy

recorder = InMemoryRecorder()
executor = ToolExecutor(ToolPolicy(allowed_tools=frozenset({"weather.lookup"})), recorder)
value = executor.execute("weather.lookup", lambda: 22, run_id="demo")
print(value, [event.event_type for event in recorder.events])
```

The default recorder stores metadata only; tool arguments and results are excluded.
