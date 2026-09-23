import json
import tempfile
import unittest
from pathlib import Path

from llm import codex_compact_warning as compact_warning


class CompactWarningTest(unittest.TestCase):
    def test_reads_latest_codex_snapshot_and_warns(self) -> None:
        events = [
            {"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {"limit_id": "premium"}}},
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"input_tokens": 130_000}},
                    "rate_limits": {
                        "limit_id": "codex",
                        "primary": {"used_percent": 90, "resets_at": 2_000},
                    },
                },
            },
            {"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {"limit_id": "premium"}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
            snapshot = compact_warning.latest_snapshot(path)

        self.assertEqual(snapshot, (130_000, [(10.0, 2_000)]))
        self.assertIn("run /compact now", compact_warning.warning(snapshot, now=1_000))

    def test_does_not_warn_for_small_context_or_expired_window(self) -> None:
        self.assertIsNone(compact_warning.warning((119_999, [(1.0, None)]), now=1_000))
        self.assertIsNone(compact_warning.warning((130_000, [(1.0, 999)]), now=1_000))


if __name__ == "__main__":
    unittest.main()
