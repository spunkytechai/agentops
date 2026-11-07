"""A minimal policy-protected tool call."""
from agentops import InMemoryRecorder, ToolExecutor, ToolPolicy

recorder = InMemoryRecorder()
executor = ToolExecutor(ToolPolicy(frozenset({"inventory.lookup"})), recorder)
quantity = executor.execute("inventory.lookup", lambda: 17, run_id="example-run")
print(f"Available quantity: {quantity}")
for event in recorder.events:
    print(event.event_type, event.tool_name, event.duration_ms)
