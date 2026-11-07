import json
from pathlib import Path
import unittest

from agentops import action_fingerprint


FIXTURE = json.loads(
    (Path(__file__).resolve().parents[3] / "conformance/fixtures/action-fingerprint.json").read_text()
)


class ActionFingerprintTests(unittest.TestCase):
    def test_shared_action_fingerprint_matches_reference(self):
        self.assertEqual(action_fingerprint(FIXTURE["action"]), FIXTURE["sha256"])

    def test_object_key_order_does_not_change_fingerprint(self):
        action = FIXTURE["action"]
        reordered = dict(reversed(list(action.items())))
        self.assertEqual(action_fingerprint(action), action_fingerprint(reordered))

    def test_unsupported_floats_are_rejected(self):
        with self.assertRaises(TypeError):
            action_fingerprint({"amount": 2.5})

    def test_unpaired_surrogate_is_rejected(self):
        with self.assertRaises(UnicodeEncodeError):
            action_fingerprint({"invalid": "\ud800"})
