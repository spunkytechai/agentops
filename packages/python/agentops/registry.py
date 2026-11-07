"""Versioned in-memory registry for agent definitions."""
from dataclasses import dataclass
from typing import Sequence


class AgentAlreadyRegisteredError(ValueError):
    """Raised when an agent ID/version pair is already registered."""


class AgentNotFoundError(LookupError):
    """Raised when an agent ID/version pair cannot be found."""


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Immutable, provider-neutral description of one agent version."""
    agent_id: str
    version: str
    description: str = ""
    tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string")
        if not isinstance(self.description, str):
            raise TypeError("description must be a string")
        normalized_tools = tuple(self.tools)
        if any(not isinstance(name, str) or not name.strip() for name in normalized_tools):
            raise ValueError("tool names must be non-empty strings")
        if len(set(normalized_tools)) != len(normalized_tools):
            raise ValueError("tool names must be unique")
        object.__setattr__(self, "tools", normalized_tools)


class AgentRegistry:
    """Process-local registry keyed by immutable (agent_id, version) pairs.

    This registry is intentionally in-memory; it is not a distributed store.
    """
    def __init__(self) -> None:
        self._agents: dict[tuple[str, str], AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> AgentDefinition:
        if not isinstance(agent, AgentDefinition):
            raise TypeError("agent must be an AgentDefinition")
        key = (agent.agent_id, agent.version)
        if key in self._agents:
            raise AgentAlreadyRegisteredError(
                f"Agent {agent.agent_id!r} version {agent.version!r} is already registered"
            )
        self._agents[key] = agent
        return agent

    def get(self, agent_id: str, version: str) -> AgentDefinition:
        try:
            return self._agents[(agent_id, version)]
        except KeyError as exc:
            raise AgentNotFoundError(
                f"Agent {agent_id!r} version {version!r} was not found"
            ) from exc

    def list(self, agent_id: str | None = None) -> tuple[AgentDefinition, ...]:
        """Return a stable snapshot ordered lexicographically by ID and version."""
        agents = (
            agent for (registered_id, _), agent in self._agents.items()
            if agent_id is None or registered_id == agent_id
        )
        return tuple(sorted(agents, key=lambda item: (item.agent_id, item.version)))
