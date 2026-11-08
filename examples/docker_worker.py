"""Minimal example JSONL worker for the AgentOps Docker image."""
import json
import sys


def main() -> int:
    line = sys.stdin.readline()
    if not line:
        return 2
    try:
        request = json.loads(line)
        if request.get("protocol_version") != 1 or request.get("tool_name") != "identity.echo":
            return 2
        response = {
            "protocol_version": 1,
            "request_id": request["request_id"],
            "result": {"echo": request.get("input")},
        }
        sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        sys.stdout.flush()
        return 0
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
