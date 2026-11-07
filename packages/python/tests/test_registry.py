import unittest

from agentops import (
    AgentAlreadyRegisteredError,
    AgentDefinition,
    AgentNotFoundError,
    AgentRegistry,
)


class AgentRegistryTests(unittest.TestCase):
    def test_register_and_retrieve_versioned_agent(self):
        registry = AgentRegistry()
        agent = AgentDefinition(
            agent_id="support.assistant",
            version="1.0.0",
            description="Customer support agent",
            tools=("knowledge.search", "ticket.create"),
        )
        registry.register(agent)
        self.assertEqual(registry.get("support.assistant", "1.0.0"), agent)

    def test_duplicate_version_is_rejected(self):
        registry = AgentRegistry()
        agent = AgentDefinition("research.agent", "1.0.0")
        registry.register(agent)
        with self.assertRaises(AgentAlreadyRegisteredError):
            registry.register(agent)

    def test_multiple_versions_are_listed_deterministically(self):
        registry = AgentRegistry()
        registry.register(AgentDefinition("research.agent", "2.0.0"))
        registry.register(AgentDefinition("research.agent", "1.0.0"))
        self.assertEqual(
            [agent.version for agent in registry.list("research.agent")],
            ["1.0.0", "2.0.0"],
        )

    def test_unknown_agent_version_raises(self):
        with self.assertRaises(AgentNotFoundError):
            AgentRegistry().get("missing.agent", "1.0.0")

    def test_invalid_agent_definition_is_rejected(self):
        with self.assertRaises(ValueError):
            AgentDefinition(" ", "1.0.0")
        with self.assertRaises(ValueError):
            AgentDefinition("valid.agent", "1.0.0", tools=("search", "search"))


if __name__ == "__main__":
    unittest.main()
