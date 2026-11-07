import tempfile
import threading
import unittest
from pathlib import Path

from agentops import ApprovalManager, ApprovalRequiredError, SqliteApprovalStore


class SqliteApprovalStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "approvals.sqlite3")

    def tearDown(self):
        self.directory.cleanup()

    def test_approved_action_survives_manager_restart_and_is_consumed_once(self):
        first = ApprovalManager(store=SqliteApprovalStore(self.path))
        request = first.request(
            "finance-user", "payments.refund", "Refund order 1042",
            action={"order_id": "1042", "amount": 2500, "currency": "INR"},
        )
        first.approve(request.request_id, approver_id="finance-admin")
        first.store.close()

        second = ApprovalManager(store=SqliteApprovalStore(self.path))
        grant = second.consume(
            request.request_id, "finance-user", "payments.refund",
            action={"currency": "INR", "amount": 2500, "order_id": "1042"},
        )
        self.assertEqual(grant.approver_id, "finance-admin")
        with self.assertRaises(ApprovalRequiredError):
            ApprovalManager(store=SqliteApprovalStore(self.path)).consume(
                request.request_id, "finance-user", "payments.refund",
                action={"order_id": "1042", "amount": 2500, "currency": "INR"},
            )

    def test_two_managers_cannot_consume_the_same_approval(self):
        manager = ApprovalManager(store=SqliteApprovalStore(self.path))
        request = manager.request("user-17", "files.delete", "Delete archive")
        manager.approve(request.request_id, approver_id="admin-1")
        managers = [
            ApprovalManager(store=SqliteApprovalStore(self.path))
            for _ in range(2)
        ]
        barrier = threading.Barrier(2)
        outcomes = []

        def consume(candidate):
            barrier.wait()
            try:
                candidate.consume(request.request_id, "user-17", "files.delete")
                outcomes.append("consumed")
            except ApprovalRequiredError:
                outcomes.append("rejected")

        threads = [threading.Thread(target=consume, args=(candidate,)) for candidate in managers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertCountEqual(outcomes, ["consumed", "rejected"])

    def test_expiry_is_enforced_after_reopening_store(self):
        now = [100.0]
        store = SqliteApprovalStore(self.path)
        manager = ApprovalManager(clock=lambda: now[0], store=store)
        request = manager.request("user-17", "files.delete", "Delete archive", ttl_seconds=5)
        store.close()
        now[0] = 106.0

        reopened = ApprovalManager(clock=lambda: now[0], store=SqliteApprovalStore(self.path))
        self.assertEqual(reopened.get(request.request_id).status, "expired")


if __name__ == "__main__":
    unittest.main()
