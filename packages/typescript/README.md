# AgentOps TypeScript SDK

The TypeScript SDK provides deny-by-default tool authorization and metadata-only execution recording.

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
const result = await executor.execute("weather.lookup", async () => ({ celsius: 22 }));
console.log(result, recorder.events.map((event) => event.type));
```

The default recorder excludes arguments, results, prompts, and credentials.
