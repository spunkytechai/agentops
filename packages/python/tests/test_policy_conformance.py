"""Shared policy conformance fixtures consumed by both SDK test suites."""
import json
from pathlib import Path
import unittest

from agentops import PolicyRule, ToolPolicy


FIXTURE = json.loads(
    (Path(__file__).resolve().parents[3] / "conformance/fixtures/policy.json").read_text()
)


class PolicyConformanceTests(unittest.TestCase):
    def test_policy_snapshots_mutable_constructor_inputs(self):
        initial = FIXTURE["initial"]
        allowed = set(initial["allowedTools"])
        denied = set(initial["deniedTools"])
        rules = [
            PolicyRule(rule["principalId"], rule["toolName"], rule["effect"])
            for rule in initial["rules"]
        ]
        policy = ToolPolicy(
            allowed_tools=allowed,
            denied_tools=denied,
            rules=rules,
        )

        allowed.add(FIXTURE["mutations"]["addAllowedTool"])
        denied.remove(FIXTURE["mutations"]["removeDeniedTool"])
        rules.append(PolicyRule(**{
            "principal_id": FIXTURE["mutations"]["addRule"]["principalId"],
            "tool_name": FIXTURE["mutations"]["addRule"]["toolName"],
            "effect": FIXTURE["mutations"]["addRule"]["effect"],
        }))

        actual = [
            policy.evaluate(case["toolName"], principal_id=case["principalId"])
            for case in FIXTURE["expected"]
        ]
        self.assertEqual(
            [(item.allowed, item.reason) for item in actual],
            [(case["allowed"], case["reason"]) for case in FIXTURE["expected"]],
        )


if __name__ == "__main__":
    unittest.main()
