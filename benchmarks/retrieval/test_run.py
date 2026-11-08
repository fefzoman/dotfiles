import unittest

from run import completed_usage


class UsageTests(unittest.TestCase):
    def test_cached_input_is_not_added_twice(self):
        usage = completed_usage([{"type": "turn.completed", "usage": {
            "input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10,
            "reasoning_output_tokens": 4}}])
        self.assertEqual(usage["total_tokens"], 110)
        self.assertEqual(usage["uncached_input_tokens"], 20)

    def test_incomplete_or_invalid_usage_is_not_a_saving(self):
        for events in ([], [{"type": "turn.completed", "usage": {}}],
                       [{"type": "turn.completed", "usage": {
                           "input_tokens": 1, "cached_input_tokens": 2, "output_tokens": 0}}]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                completed_usage(events)


if __name__ == "__main__":
    unittest.main()
