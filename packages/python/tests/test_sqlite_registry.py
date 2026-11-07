import tempfile
import unittest
from pathlib import Path

from agentops import (
    AgentAlreadyRegisteredError,
    AgentDefinition,
    AgentNotFoundError,
    AgentRegistry,
    SqliteAgentRegistryStore,
)


class SqliteAgentRegistryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "agents.sqlite3")

    def tearDown(self):
        self.directory.cleanup()

    def test_agent_versions_survive_registry_restart(self):
        first = AgentRegistry(store=SqliteAgentRegistryStore(self.path))
        agent = AgentDefinition(
            "support.assistant", "1.0.0", "Support agent",
            ("knowledge.search", "ticket.create"),
        )
        first.register(agent)
        first.store.close()

        restarted = AgentRegistry(store=SqliteAgentRegistryStore(self.path))
        self.assertEqual(restarted.get("support.assistant", "1.0.0"), agent)
        self.assertEqual(restarted.list(), (agent,))
        restarted.store.close()

    def test_duplicate_version_is_rejected_across_registry_instances(self):
        first_store = SqliteAgentRegistryStore(self.path)
        second_store = SqliteAgentRegistryStore(self.path)
        first = AgentRegistry(store=first_store)
        second = AgentRegistry(store=second_store)
        agent = AgentDefinition("support.assistant", "1.0.0")
        first.register(agent)
        with self.assertRaises(AgentAlreadyRegisteredError):
            second.register(agent)
        first_store.close()
        second_store.close()

    def test_list_is_filtered_and_sorted_by_exact_agent_id_and_version(self):
        registry = AgentRegistry(store=SqliteAgentRegistryStore(self.path))
        registry.register(AgentDefinition("zeta.agent", "1.0.0"))
        registry.register(AgentDefinition("alpha.agent", "2.0.0"))
        registry.register(AgentDefinition("alpha.agent", "1.0.0"))
        self.assertEqual(
            [(item.agent_id, item.version) for item in registry.list()],
            [("alpha.agent", "1.0.0"), ("alpha.agent", "2.0.0"), ("zeta.agent", "1.0.0")],
        )
        self.assertEqual(
            [item.version for item in registry.list("alpha.agent")],
            ["1.0.0", "2.0.0"],
        )
        registry.store.close()

    def test_missing_persisted_agent_raises_not_found(self):
        registry = AgentRegistry(store=SqliteAgentRegistryStore(self.path))
        with self.assertRaises(AgentNotFoundError):
            registry.get("missing.agent", "1.0.0")
        registry.store.close()


if __name__ == "__main__":
    unittest.main()
