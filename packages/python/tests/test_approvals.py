import unittest

from agentops import ApprovalDeniedError, ApprovalManager, ApprovalRequiredError


class ApprovalManagerTests(unittest.TestCase):
    def test_approved_request_can_be_consumed_once_by_bound_principal_and_tool(self):
        manager = ApprovalManager()
        request = manager.request(
            principal_id="user-17",
            tool_name="payments.refund",
            summary="Refund order 1042",
        )
        manager.approve(request.request_id, approver_id="admin-1")

        grant = manager.consume(
            request.request_id,
            principal_id="user-17",
            tool_name="payments.refund",
        )
        self.assertEqual(grant.request_id, request.request_id)
        self.assertEqual(grant.approver_id, "admin-1")
        with self.assertRaises(ApprovalRequiredError):
            manager.consume(
                request.request_id,
                principal_id="user-17",
                tool_name="payments.refund",
            )

    def test_pending_request_cannot_be_consumed(self):
        manager = ApprovalManager()
        request = manager.request("user-17", "files.delete", "Delete archive")
        with self.assertRaises(ApprovalRequiredError):
            manager.consume(request.request_id, "user-17", "files.delete")

    def test_denied_request_cannot_be_consumed(self):
        manager = ApprovalManager()
        request = manager.request("user-17", "files.delete", "Delete archive")
        manager.deny(request.request_id, approver_id="admin-1", reason="Retention policy")
        with self.assertRaises(ApprovalDeniedError):
            manager.consume(request.request_id, "user-17", "files.delete")

    def test_approval_is_bound_to_principal_and_tool(self):
        manager = ApprovalManager()
        request = manager.request("user-17", "payments.refund", "Refund order 1042")
        manager.approve(request.request_id, approver_id="admin-1")
        with self.assertRaises(ApprovalRequiredError):
            manager.consume(request.request_id, "user-18", "payments.refund")
        with self.assertRaises(ApprovalRequiredError):
            manager.consume(request.request_id, "user-17", "payments.capture")

    def test_expired_request_cannot_be_consumed(self):
        now = [100.0]
        manager = ApprovalManager(clock=lambda: now[0])
        request = manager.request(
            "user-17", "payments.refund", "Refund order 1042", ttl_seconds=10
        )
        manager.approve(request.request_id, approver_id="admin-1")
        now[0] = 111.0
        with self.assertRaises(ApprovalRequiredError):
            manager.consume(request.request_id, "user-17", "payments.refund")

    def test_cannot_approve_or_deny_a_non_pending_request(self):
        manager = ApprovalManager()
        request = manager.request("user-17", "files.delete", "Delete archive")
        manager.deny(request.request_id, approver_id="admin-1", reason="No")
        with self.assertRaises(ApprovalDeniedError):
            manager.approve(request.request_id, approver_id="admin-2")

    def test_invalid_request_is_rejected(self):
        manager = ApprovalManager()
        with self.assertRaises(ValueError):
            manager.request(" ", "files.delete", "Delete archive")
        with self.assertRaises(ValueError):
            manager.request("user-17", "files.delete", " ", ttl_seconds=10)
        with self.assertRaises(ValueError):
            manager.request("user-17", "files.delete", "Delete archive", ttl_seconds=0)
