#!/usr/bin/env python3
"""Regression tests for exact inner-session accounting."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("token-profiler")
LOADER = importlib.machinery.SourceFileLoader("token_profiler", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
token_profiler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = token_profiler
LOADER.exec_module(token_profiler)


def usage(input_tokens: int, cached: int, output: int, reasoning: int) -> dict[str, int]:
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": output,
        "reasoning_output_tokens": reasoning,
        "total_tokens": input_tokens + output,
    }


class InnerSessionTest(unittest.TestCase):
    def analyze(self, records: list[dict[str, object]]):
        with tempfile.TemporaryDirectory() as directory:
            rollout = Path(directory) / "rollout-test-session.jsonl"
            rollout.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            return token_profiler.analyze_session(rollout)

    def test_latest_window_resets_after_gap_over_30_minutes(self) -> None:
        records = [
            {
                "timestamp": "2026-09-20T10:00:00Z",
                "type": "session_meta",
                "payload": {"id": "test-session", "cwd": "/tmp/project"},
            },
            {
                "timestamp": "2026-09-20T10:05:00Z",
                "type": "token_usage_record",
                "payload": {
                    "response_id": "one",
                    "usage": usage(100, 80, 10, 2),
                    "thread_token_usage": usage(100, 80, 10, 2),
                },
            },
            {
                "timestamp": "2026-09-20T10:20:00Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "first window"},
            },
            {
                "timestamp": "2026-09-20T11:00:00Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "second window"},
            },
            {
                "timestamp": "2026-09-20T11:01:00Z",
                "type": "token_usage_record",
                "payload": {
                    "response_id": "two",
                    "usage": usage(200, 150, 20, 3),
                    "thread_token_usage": usage(300, 230, 30, 5),
                },
            },
            {
                "timestamp": "2026-09-20T11:15:00Z",
                "type": "token_usage_record",
                "payload": {
                    "response_id": "three",
                    "usage": usage(300, 250, 30, 4),
                    "thread_token_usage": usage(600, 480, 60, 9),
                },
            },
        ]

        report = self.analyze(records)

        self.assertEqual(report.total.input_tokens, 600)
        self.assertEqual(report.total.cached_input_tokens, 480)
        self.assertEqual(report.total.output_tokens, 60)
        self.assertEqual(report.model_calls, 3)
        self.assertEqual(report.inner_started_at, "2026-09-20T11:00:00Z")
        self.assertEqual(report.inner_ended_at, "2026-09-20T11:15:00Z")
        self.assertEqual(token_profiler.duration_seconds(report.inner_started_at, report.inner_ended_at), 900)
        self.assertEqual(report.inner_usage.input_tokens, 500)
        self.assertEqual(report.inner_usage.cached_input_tokens, 400)
        self.assertEqual(report.inner_usage.output_tokens, 50)
        self.assertEqual(report.inner_usage.reasoning_output_tokens, 7)
        self.assertEqual(report.inner_model_calls, 2)

    def test_gap_of_exactly_30_minutes_stays_in_current_window(self) -> None:
        report = self.analyze(
            [
                {
                    "timestamp": "2026-09-20T10:00:00Z",
                    "type": "session_meta",
                    "payload": {"id": "test-session"},
                },
                {
                    "timestamp": "2026-09-20T10:30:00Z",
                    "type": "token_usage_record",
                    "payload": {
                        "response_id": "one",
                        "usage": usage(100, 80, 10, 2),
                    },
                },
            ]
        )

        self.assertEqual(report.inner_started_at, "2026-09-20T10:00:00Z")
        self.assertEqual(report.inner_model_calls, 1)
        self.assertEqual(report.inner_usage.input_tokens, 100)


class ClaudeSessionTest(unittest.TestCase):
    def test_exact_usage_tools_compaction_and_inner_session(self) -> None:
        records = [
            {
                "timestamp": "2026-09-20T10:00:00Z",
                "type": "user",
                "sessionId": "claude-session",
                "cwd": "/tmp/project",
                "version": "2.1.0",
                "message": {"role": "user", "content": "Fix the parser"},
            },
            {
                "timestamp": "2026-09-20T10:01:00Z",
                "type": "assistant",
                "sessionId": "claude-session",
                "message": {
                    "id": "message-one",
                    "role": "assistant",
                    "model": "claude-sonnet-test",
                    "usage": {
                        "input_tokens": 100,
                        "cache_creation_input_tokens": 50,
                        "cache_read_input_tokens": 200,
                        "output_tokens": 20,
                        "output_tokens_details": {"thinking_tokens": 5},
                    },
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "bash-one",
                            "name": "Bash",
                            "input": {"command": "pytest -q"},
                        },
                        {
                            "type": "tool_use",
                            "id": "serena-one",
                            "name": "mcp__serena__find_symbol",
                            "input": {"name_path_pattern": "Parser"},
                        },
                    ],
                },
            },
            {
                "timestamp": "2026-09-20T10:02:00Z",
                "type": "user",
                "sessionId": "claude-session",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "bash-one",
                            "content": "2 passed",
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "serena-one",
                            "content": "Parser at src/parser.py:10",
                        },
                    ],
                },
            },
            {
                "timestamp": "2026-09-20T10:20:00Z",
                "type": "assistant",
                "sessionId": "claude-session",
                "message": {
                    "id": "message-two",
                    "role": "assistant",
                    "model": "claude-sonnet-test",
                    "usage": {
                        "input_tokens": 120,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 300,
                        "output_tokens": 30,
                    },
                    "content": [{"type": "text", "text": "First period complete."}],
                },
            },
            {
                "timestamp": "2026-09-20T11:00:01Z",
                "type": "user",
                "sessionId": "claude-session",
                "message": {"role": "user", "content": "Continue"},
            },
            {
                "timestamp": "2026-09-20T11:01:00Z",
                "type": "assistant",
                "sessionId": "claude-session",
                "message": {
                    "id": "message-three",
                    "role": "assistant",
                    "model": "claude-sonnet-test",
                    "usage": {
                        "input_tokens": 50,
                        "cache_creation_input_tokens": 25,
                        "cache_read_input_tokens": 100,
                        "output_tokens": 10,
                    },
                    "content": [{"type": "text", "text": "Continued."}],
                },
            },
            {
                "timestamp": "2026-09-20T11:02:00Z",
                "type": "system",
                "subtype": "compact_boundary",
                "sessionId": "claude-session",
            },
        ]

        with tempfile.TemporaryDirectory() as directory:
            transcript = Path(directory) / "claude-session.jsonl"
            transcript.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            report = token_profiler.analyze_claude_session(transcript)

        self.assertEqual(report.agent, "claude")
        self.assertEqual(report.session_id, "claude-session")
        self.assertEqual(report.total.input_tokens, 945)
        self.assertEqual(report.total.cached_input_tokens, 600)
        self.assertEqual(report.total.cache_creation_input_tokens, 75)
        self.assertEqual(report.total.output_tokens, 60)
        self.assertEqual(report.total.reasoning_output_tokens, 5)
        self.assertEqual(report.model_calls, 3)
        self.assertEqual(report.compactions, 1)
        self.assertEqual(report.inner_started_at, "2026-09-20T11:00:01Z")
        self.assertEqual(report.inner_usage.input_tokens, 175)
        self.assertEqual(report.inner_usage.cached_input_tokens, 100)
        self.assertEqual(report.inner_usage.cache_creation_input_tokens, 25)
        self.assertEqual(report.inner_model_calls, 1)
        self.assertEqual(report.inner_compactions, 1)
        self.assertEqual(report.tool_calls["Bash"], 1)
        self.assertEqual(report.tool_calls["mcp__serena__find_symbol"], 1)
        self.assertGreater(report.tool_payloads["mcp__serena__find_symbol"], 0)

    def test_profile_subcommands_map_to_distinct_homes(self) -> None:
        personal = token_profiler.profile_for("claude")
        work = token_profiler.profile_for("claude-work")

        self.assertEqual(personal.agent, "claude")
        self.assertEqual(personal.home, Path.home() / ".claude")
        self.assertEqual(work.agent, "claude")
        self.assertEqual(work.home, Path.home() / ".claude-work")

    def test_claude_parent_includes_companion_subagent_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            project = home / "projects" / "project"
            transcript = project / "parent-session.jsonl"
            subagent = project / "parent-session" / "subagents" / "agent-one.jsonl"
            subagent.parent.mkdir(parents=True)
            transcript.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-09-20T10:00:00Z",
                        "type": "assistant",
                        "sessionId": "parent-session",
                        "message": {
                            "id": "parent-message",
                            "model": "claude-test",
                            "usage": {
                                "input_tokens": 100,
                                "cache_read_input_tokens": 50,
                                "output_tokens": 10,
                            },
                            "content": [],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            subagent.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-09-20T10:05:00Z",
                        "type": "assistant",
                        "sessionId": "parent-session",
                        "message": {
                            "id": "subagent-message",
                            "model": "claude-test",
                            "usage": {
                                "input_tokens": 40,
                                "cache_creation_input_tokens": 10,
                                "cache_read_input_tokens": 20,
                                "output_tokens": 5,
                            },
                            "content": [],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            profile = token_profiler.profile_for("claude", home)
            discovered = token_profiler.discover_sessions(profile)
            report = token_profiler.analyze_profile_session(discovered[0], profile)

        self.assertEqual(discovered, [transcript])
        self.assertEqual(report.subagent_sessions, 1)
        self.assertEqual(report.total.input_tokens, 220)
        self.assertEqual(report.total.cached_input_tokens, 70)
        self.assertEqual(report.total.cache_creation_input_tokens, 10)
        self.assertEqual(report.total.output_tokens, 15)
        self.assertEqual(report.model_calls, 2)
        self.assertEqual(report.inner_model_calls, 2)


if __name__ == "__main__":
    unittest.main()
