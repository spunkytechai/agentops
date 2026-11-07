"""Explicit global and principal-scoped policy for agent tool execution."""
from dataclasses import dataclass
from typing import Literal


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
class PolicyRule:
    """An exact tool permission granted to or denied for one principal."""
    principal_id: str
    tool_name: str
    effect: Literal["allow", "deny"]

    def __post_init__(self) -> None:
        if not isinstance(self.principal_id, str) or not self.principal_id.strip():
            raise ValueError("principal_id must be a non-empty string")
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")
        if self.effect not in ("allow", "deny"):
            raise ValueError("effect must be 'allow' or 'deny'")


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """Deny-by-default policy; explicit denies always take precedence.

    Global allow/deny sets apply to every principal. Rules add exact,
    principal-scoped decisions without widening another principal's access.
    """
    allowed_tools: frozenset[str] = frozenset()
    denied_tools: frozenset[str] = frozenset()
    rules: tuple[PolicyRule, ...] = ()

    def __post_init__(self) -> None:
        for name in self.allowed_tools | self.denied_tools:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Tool names must be non-empty strings")
        if any(not isinstance(rule, PolicyRule) for rule in self.rules):
            raise TypeError("rules must contain PolicyRule instances")

    def evaluate(self, tool_name: str, principal_id: str | None = None) -> PolicyDecision:
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")
        if principal_id is not None and (
            not isinstance(principal_id, str) or not principal_id.strip()
        ):
            raise ValueError("principal_id must be a non-empty string when provided")

        scoped_effects = {
            rule.effect for rule in self.rules
            if rule.tool_name == tool_name and rule.principal_id == principal_id
        } if principal_id is not None else set()

        if tool_name in self.denied_tools or "deny" in scoped_effects:
            reason = "explicitly denied" if tool_name in self.denied_tools else "principal-scoped deny rule"
            return PolicyDecision(False, tool_name, reason)
        if tool_name in self.allowed_tools:
            return PolicyDecision(True, tool_name, "explicitly allowed")
        if "allow" in scoped_effects:
            return PolicyDecision(True, tool_name, "principal-scoped allow rule")
        return PolicyDecision(False, tool_name, "not present in allow-list")
