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

    def test_cold_calls_distinguish_idle_and_compaction(self) -> None:
        report = self.analyze(
            [
                {
                    "timestamp": "2026-09-20T10:00:00Z",
                    "type": "token_usage_record",
                    "payload": {"response_id": "one", "usage": usage(100, 0, 1, 0)},
                },
                {
                    "timestamp": "2026-09-20T10:31:00Z",
                    "type": "token_usage_record",
                    "payload": {"response_id": "two", "usage": usage(200, 10, 1, 0)},
                },
                {
                    "timestamp": "2026-09-20T10:31:01Z",
                    "type": "compacted",
                    "payload": {"replacement_history": "summary"},
                },
                {
                    "timestamp": "2026-09-20T10:31:05Z",
                    "type": "token_usage_record",
                    "payload": {"response_id": "three", "usage": usage(50, 0, 1, 0)},
                },
            ]
        )

        self.assertEqual(report.calls[0].cold_reason, "session start")
        self.assertEqual(report.calls[1].gap_seconds, 1860)
        self.assertEqual(report.calls[1].cold_reason, "resume after idle")
        self.assertEqual(report.calls[2].gap_seconds, 5)
        self.assertEqual(report.calls[2].cold_reason, "post-compaction")
        windows = token_profiler.model_call_windows(report)
        self.assertEqual([window["calls"] for window in windows], [1, 2])
        self.assertEqual(windows[1]["first_call_fresh_tokens"], 190)
        self.assertEqual(windows[1]["later_call_average_fresh_tokens"], 50)


class CodexProgrammaticToolTest(unittest.TestCase):
    def test_tool_outliers_include_arguments_and_duplicate_occurrence(self) -> None:
        report = token_profiler.SessionReport(Path("rollout.jsonl"))
        arguments = '{"query":"same query"}'
        token_profiler.record_tool_result(
            report, ["web__run"], 2501, "2026-09-20T10:00:00Z", arguments
        )
        token_profiler.record_tool_result(
            report, ["web__run"], 2502, "2026-09-20T10:01:00Z", arguments
        )
        token_profiler.record_tool_result(
            report,
            ["tool_inventory"],
            2101,
            "2026-09-20T10:02:00Z",
            'const matches = ALL_TOOLS.filter(x => /serena|context7/i.test(x.name));',
        )
        token_profiler.record_tool_result(
            report,
            ["tool_inventory"],
            2102,
            "2026-09-20T10:03:00Z",
            'const hits = ALL_TOOLS.filter(x => /serena|context7/i.test(x.name));',
        )

        outliers = token_profiler.tool_result_outliers(report)
        self.assertEqual(outliers[0]["arguments"], arguments)
        self.assertTrue(outliers[0]["repeated"])
        inventory = [row for row in outliers if row["tool"] == "tool_inventory"]
        self.assertEqual({row["occurrence"] for row in inventory}, {1, 2})
        self.assertTrue(all(row["repeated"] for row in inventory))

    def test_programmatic_shell_command_and_quoted_file_are_extracted(self) -> None:
        script = (
            'const r = await tools.exec_command({cmd: "sed -n \'1,20p\' \'Phase 3.md\'", '
            'workdir: "/tmp/project"}); text(r.output);'
        )
        command = token_profiler.extract_command(script)

        self.assertEqual(command, "sed -n '1,20p' 'Phase 3.md'")
        self.assertEqual(
            token_profiler.extract_files_from_command(command),
            ["Phase 3.md"],
        )
        self.assertIsNone(
            token_profiler.extract_command(
                'text(await tools.apply_patch("*** Add File: test.py\\n+python"));'
            )
        )

    def test_nested_mcp_tools_are_visible_in_optimization_report(self) -> None:
        records = [
            {
                "timestamp": "2026-09-20T10:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "exec-one",
                    "name": "exec",
                    "input": (
                        "const a = await tools.mcp__serena__find_symbol({});\n"
                        "const b = await tools.mcp__context7__query_docs({});"
                    ),
                },
            },
            {
                "timestamp": "2026-09-20T10:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "exec-one",
                    "output": "Serena result\nContext7 result",
                },
            },
        ]

        with tempfile.TemporaryDirectory() as directory:
            rollout = Path(directory) / "rollout-test-session.jsonl"
            rollout.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            report = token_profiler.analyze_session(rollout)

        serena = token_profiler.observed_tool(report, "serena")
        context7 = token_profiler.observed_tool(report, "context7")
        self.assertEqual(serena["calls_observed"], 1)
        self.assertTrue(serena["calls_are_lower_bound"])
        self.assertGreater(serena["result_tokens_estimate"], 0)
        self.assertEqual(context7["calls_observed"], 1)
        self.assertTrue(context7["calls_are_lower_bound"])
        self.assertGreater(context7["result_tokens_estimate"], 0)
        self.assertGreater(report.observed_payload["MCP/tool results"], 0)
        self.assertNotIn("Shell command output", report.observed_payload)
        stats = {
            row["name"]: row for row in token_profiler.tool_statistics(report)
        }
        self.assertIn("mcp__serena__find_symbol", stats)
        self.assertIn("mcp__context7__query_docs", stats)
        self.assertNotIn("exec", stats)

    def test_payload_lifecycle_and_instruction_sources_survive_compaction(self) -> None:
        records = [
            {
                "timestamp": "2026-09-20T10:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [
                        {"type": "input_text", "text": "PONYTAIL MODE ACTIVE — level: full"}
                    ],
                },
            },
            {
                "timestamp": "2026-09-20T10:00:01Z",
                "type": "compacted",
                "payload": {"replacement_history": "short summary"},
            },
            {
                "timestamp": "2026-09-20T10:00:02Z",
                "type": "token_usage_record",
                "payload": {
                    "response_id": "one",
                    "usage": usage(100, 80, 10, 2),
                },
            },
            {
                "timestamp": "2026-09-20T10:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Continue"}],
                },
            },
        ]

        with tempfile.TemporaryDirectory() as directory:
            rollout = Path(directory) / "rollout-test-session.jsonl"
            rollout.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            report = token_profiler.analyze_session(rollout)

        removed = token_profiler.payload_difference(
            report.observed_payload, report.active_payload
        )
        self.assertGreater(report.instruction_payloads["Ponytail"], 0)
        self.assertGreater(removed["AGENTS.md/instructions"], 0)
        self.assertGreater(report.active_payload["Compacted history"], 0)
        self.assertGreater(report.active_payload["Conversation/history"], 0)


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
