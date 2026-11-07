# AgentOps TypeScript SDK

The TypeScript SDK provides deny-by-default tool authorization, versioned agent registration, and metadata-only execution recording.

## Development
```bash
npm install
npm test
```

## Example
```ts
import { InMemoryRecorder, ToolExecutor, ToolPolicy } from "@spunkytech/agentops";

const recorder = new InMemoryRecorder();
const executor = new ToolExecutor(
  new ToolPolicy({ allowedTools: ["weather.lookup"] }),
  recorder,
);

const result = await executor.execute(
  "weather.lookup",
  async (signal) => {
    const response = await fetch("https://api.example.test/weather", { signal });
    if (!response.ok) throw new Error("Weather service failed");
    return response.json();
  },
  "weather-run-1",
  { timeoutMs: 5000 },
);

console.log(result, recorder.events.map((event) => event.type));
```

The operation receives an `AbortSignal`. Propagate it to cancellable APIs; otherwise, timed-out work may continue in the background. The default recorder excludes arguments, results, prompts, and credentials.
