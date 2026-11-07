"""Explicit allow/deny policy for agent tool execution."""
from dataclasses import dataclass


class PolicyDeniedError(PermissionError):
    """Raised when a tool call is not authorized."""
    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Tool {tool_name!r} denied: {reason}")


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    tool_name: str
    reason: str


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """Deny-by-default policy; explicit deny rules take precedence."""
    allowed_tools: frozenset[str] = frozenset()
    denied_tools: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for name in self.allowed_tools | self.denied_tools:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Tool names must be non-empty strings")

    def evaluate(self, tool_name: str) -> PolicyDecision:
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")
        if tool_name in self.denied_tools:
            return PolicyDecision(False, tool_name, "explicitly denied")
        if tool_name in self.allowed_tools:
            return PolicyDecision(True, tool_name, "explicitly allowed")
        return PolicyDecision(False, tool_name, "not present in allow-list")
