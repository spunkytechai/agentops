"""Versioned agent registry with pluggable in-memory and SQLite storage."""
from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Protocol


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


class AgentRegistryStore(Protocol):
    """Storage contract; create must atomically reject duplicate ID/version pairs."""

    def create(self, agent: AgentDefinition) -> bool: ...
    def get(self, agent_id: str, version: str) -> AgentDefinition | None: ...
    def list(self, agent_id: str | None = None) -> tuple[AgentDefinition, ...]: ...


class InMemoryAgentRegistryStore:
    """Thread-safe process-local registry store."""

    def __init__(self) -> None:
        self._agents: dict[tuple[str, str], AgentDefinition] = {}
        self._lock = RLock()

    def create(self, agent: AgentDefinition) -> bool:
        key = (agent.agent_id, agent.version)
        with self._lock:
            if key in self._agents:
                return False
            self._agents[key] = agent
            return True

    def get(self, agent_id: str, version: str) -> AgentDefinition | None:
        with self._lock:
            return self._agents.get((agent_id, version))

    def list(self, agent_id: str | None = None) -> tuple[AgentDefinition, ...]:
        with self._lock:
            agents = (
                agent for (registered_id, _), agent in self._agents.items()
                if agent_id is None or registered_id == agent_id
            )
            return tuple(sorted(agents, key=lambda item: (item.agent_id, item.version)))


class SqliteAgentRegistryStore:
    """SQLite-backed persistent registry with an immutable composite key.

    Python and TypeScript share the `agentops_agents` table and JSON tool-list
    representation. Use a database file on storage with reliable SQLite locking.
    """

    def __init__(self, database: str | Path, *, timeout_seconds: float = 30.0) -> None:
        import math

        if (
            isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")
        self._connection = sqlite3.connect(
            str(database), timeout=timeout_seconds, isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._connection.execute(f"PRAGMA busy_timeout = {int(timeout_seconds * 1000)}")
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS agentops_agents (
                agent_id TEXT NOT NULL,
                version TEXT NOT NULL,
                description TEXT NOT NULL,
                tools_json TEXT NOT NULL,
                PRIMARY KEY (agent_id, version)
            )
        """)

    def create(self, agent: AgentDefinition) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                """INSERT OR IGNORE INTO agentops_agents
                (agent_id, version, description, tools_json) VALUES (?, ?, ?, ?)""",
                (
                    agent.agent_id, agent.version, agent.description,
                    json.dumps(agent.tools, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            return cursor.rowcount == 1

    def get(self, agent_id: str, version: str) -> AgentDefinition | None:
        with self._lock:
            row = self._connection.execute(
                """SELECT agent_id, version, description, tools_json
                FROM agentops_agents WHERE agent_id = ? AND version = ?""",
                (agent_id, version),
            ).fetchone()
            return self._from_row(row) if row is not None else None

    def list(self, agent_id: str | None = None) -> tuple[AgentDefinition, ...]:
        with self._lock:
            if agent_id is None:
                rows = self._connection.execute(
                    """SELECT agent_id, version, description, tools_json
                    FROM agentops_agents ORDER BY agent_id COLLATE BINARY, version COLLATE BINARY"""
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """SELECT agent_id, version, description, tools_json
                    FROM agentops_agents WHERE agent_id = ?
                    ORDER BY agent_id COLLATE BINARY, version COLLATE BINARY""",
                    (agent_id,),
                ).fetchall()
            return tuple(self._from_row(row) for row in rows)

    def close(self) -> None:
        """Close the SQLite connection owned by this store."""
        with self._lock:
            self._connection.close()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AgentDefinition:
        try:
            tools = json.loads(row["tools_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("stored agent tools_json is invalid JSON") from exc
        if not isinstance(tools, list) or any(not isinstance(item, str) for item in tools):
            raise ValueError("stored agent tools_json must be a JSON array of strings")
        return AgentDefinition(
            agent_id=row["agent_id"], version=row["version"],
            description=row["description"], tools=tuple(tools),
        )


class AgentRegistry:
    """Registry keyed by immutable (agent_id, version) pairs.

    The default store is process-local. Inject SqliteAgentRegistryStore for
    durable registration across process restarts and SQLite connections.
    """

    def __init__(self, *, store: AgentRegistryStore | None = None) -> None:
        self.store: AgentRegistryStore = store if store is not None else InMemoryAgentRegistryStore()

    def register(self, agent: AgentDefinition) -> AgentDefinition:
        if not isinstance(agent, AgentDefinition):
            raise TypeError("agent must be an AgentDefinition")
        if not self.store.create(agent):
            raise AgentAlreadyRegisteredError(
                f"Agent {agent.agent_id!r} version {agent.version!r} is already registered"
            )
        return agent

    def get(self, agent_id: str, version: str) -> AgentDefinition:
        agent = self.store.get(agent_id, version)
        if agent is None:
            raise AgentNotFoundError(
                f"Agent {agent_id!r} version {version!r} was not found"
            )
        return agent

    def list(self, agent_id: str | None = None) -> tuple[AgentDefinition, ...]:
        return self.store.list(agent_id)
