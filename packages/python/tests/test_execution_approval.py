import unittest

from agentops import (
    ApprovalManager,
    ApprovalRequiredError,
    PolicyDeniedError,
    PolicyRule,
    ToolExecutor,
    ToolPolicy,
)


class ExecutionApprovalTests(unittest.TestCase):
    def setUp(self):
        self.action = {"order_id": "1042", "amount": 2500, "currency": "INR"}

    def test_approval_is_bound_to_canonical_action_and_tool_execution(self):
        manager = ApprovalManager()
        request = manager.request(
            "finance-user", "payments.refund", "Refund order 1042",
            action=self.action,
        )
        manager.approve(request.request_id, approver_id="finance-admin")
        executor = ToolExecutor(ToolPolicy(rules=(
            PolicyRule("finance-user", "payments.refund", "allow"),
        )))
        invoked = []
        result = executor.execute_approved(
            "payments.refund",
            lambda approved_action: invoked.append(approved_action) or "refunded",
            principal_id="finance-user",
            approval_manager=manager,
            approval_request_id=request.request_id,
            action=self.action,
        )
        self.assertEqual(result, "refunded")
        self.assertEqual(invoked, [self.action])
        self.assertEqual(manager.get(request.request_id).status, "consumed")

    def test_action_substitution_is_rejected_before_tool_invocation(self):
        manager = ApprovalManager()
        request = manager.request(
            "finance-user", "payments.refund", "Refund order 1042",
            action=self.action,
        )
        manager.approve(request.request_id, approver_id="finance-admin")
        executor = ToolExecutor(ToolPolicy(rules=(
            PolicyRule("finance-user", "payments.refund", "allow"),
        )))
        invoked = []
        changed_action = {**self.action, "amount": 25000}
        with self.assertRaises(ApprovalRequiredError):
            executor.execute_approved(
                "payments.refund", lambda action: invoked.append(action),
                principal_id="finance-user", approval_manager=manager,
                approval_request_id=request.request_id, action=changed_action,
            )
        self.assertEqual(invoked, [])

    def test_policy_deny_wins_and_does_not_consume_approval(self):
        manager = ApprovalManager()
        request = manager.request(
            "finance-user", "payments.refund", "Refund order 1042",
            action=self.action,
        )
        manager.approve(request.request_id, approver_id="finance-admin")
        executor = ToolExecutor(ToolPolicy(
            allowed_tools=frozenset({"payments.refund"}),
            rules=(PolicyRule("finance-user", "payments.refund", "deny"),),
        ))
        with self.assertRaises(PolicyDeniedError):
            executor.execute_approved(
                "payments.refund", lambda action: "should not run",
                principal_id="finance-user", approval_manager=manager,
                approval_request_id=request.request_id, action=self.action,
            )
        self.assertEqual(manager.get(request.request_id).status, "approved")
