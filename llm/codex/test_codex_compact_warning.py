import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from llm.codex import codex_compact_warning as compact_warning


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

        self.assertEqual(snapshot, (130_000, [(10.0, 2_000)], 0.0))
        self.assertIn("run /compact now", compact_warning.warning(snapshot, now=1_000))

    def test_does_not_warn_for_small_context_or_expired_window(self) -> None:
        self.assertIsNone(compact_warning.warning((119_999, [(1.0, None)], 0.0), now=1_000))
        self.assertIsNone(compact_warning.warning((130_000, [(1.0, 999)], 0.0), now=1_000))

    def test_leaves_long_gaps_to_the_idle_hint(self) -> None:
        def run(hours_ago: float, session: str) -> str:
            stamp = datetime.fromtimestamp(time.time() - hours_ago * 3600, timezone.utc).isoformat()
            event = {"type": "event_msg", "timestamp": stamp, "payload": {
                "type": "token_count", "info": {"last_token_usage": {"input_tokens": 130_000}},
                "rate_limits": {"limit_id": "codex", "primary": {"used_percent": 90, "resets_at": None}}}}
            path = Path(directory) / f"{session}.jsonl"
            path.write_text(json.dumps(event) + "\n")
            hook = io.StringIO(json.dumps({"transcript_path": str(path), "session_id": session}))
            out = io.StringIO()
            with mock.patch("sys.stdin", hook), contextlib.redirect_stdout(out):
                compact_warning.main()
            return out.getvalue()

        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"XDG_STATE_HOME": directory}):
            self.assertIn("run /compact now", run(0.1, "fresh"))
            self.assertEqual(run(4, "idle"), "")


if __name__ == "__main__":
    unittest.main()
