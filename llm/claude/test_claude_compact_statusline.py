import re
import unittest

from llm.claude import claude_compact_statusline as statusline


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

        plain = re.sub(r"\033\[[0-9;]*m", "", output)
        self.assertIn("Context 130k/65% used | 5h 90% | 7d 40% | cache cold | WARNING", plain)
        self.assertIn(statusline.color("65%", "F0ED24"), output)
        self.assertIn(statusline.color("90%", "E53B12"), output)
        self.assertIn(statusline.color("cache cold", "4CBFD4"), output)
        self.assertTrue(output.startswith(statusline.BOLD))
        self.assertIn(statusline.RESET + " | " + statusline.color("WARNING", "D4CB24")[:-5], output)

    def test_percent_colors(self) -> None:
        self.assertEqual(statusline.percent(39), statusline.color("39%", "21C23E"))
        self.assertEqual(statusline.percent(40), statusline.color("40%", "F0ED24"))
        self.assertEqual(statusline.percent(75), statusline.color("75%", "F0ED24"))
        self.assertEqual(statusline.percent(76), statusline.color("76%", "E53B12"))

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
