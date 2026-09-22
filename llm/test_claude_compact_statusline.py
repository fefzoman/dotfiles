import unittest

from llm import claude_compact_statusline as statusline


class ClaudeCompactStatuslineTest(unittest.TestCase):
    def test_warns_for_large_context_and_nearly_exhausted_quota(self) -> None:
        output = statusline.render(
            {
                "context_window": {"total_input_tokens": 130_000, "used_percentage": 65},
                "rate_limits": {
                    "five_hour": {"used_percentage": 90},
                    "seven_day": {"used_percentage": 40},
                },
                "prompt_cache": {"caching_observed": True, "warm": False},
            }
        )

        self.assertIn("context 65% (130k)", output)
        self.assertIn("cache cold", output)
        self.assertIn("run /compact", output)

    def test_does_not_warn_without_both_signals(self) -> None:
        self.assertNotIn(
            "WARNING",
            statusline.render(
                {
                    "context_window": {"total_input_tokens": 119_999, "used_percentage": 60},
                    "rate_limits": {"five_hour": {"used_percentage": 99}},
                }
            ),
        )
        self.assertNotIn(
            "WARNING",
            statusline.render(
                {
                    "context_window": {"total_input_tokens": 130_000, "used_percentage": 65},
                    "rate_limits": {},
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
