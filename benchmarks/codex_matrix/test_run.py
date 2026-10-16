import unittest

from run import summarize_usage


class UsageTest(unittest.TestCase):
    def test_prices_cached_written_and_output_tokens_without_double_billing_reasoning(self):
        result = summarize_usage([
            {'input_tokens': 1000, 'cached_input_tokens': 800, 'cache_write_input_tokens': 100,
             'output_tokens': 100, 'reasoning_output_tokens': 40},
            {'input_tokens': 500, 'cached_input_tokens': 400, 'cache_write_input_tokens': 0,
             'output_tokens': 50, 'reasoning_output_tokens': 10},
        ], 'gpt-6.1-sol')
        self.assertEqual(result['calls'], 2)
        self.assertEqual(result['fresh_input_per_call'], 150)
        self.assertEqual(result['reasoning_per_call'], 25)
        self.assertEqual(result['cache_hit_percent'], 80)
        self.assertAlmostEqual(result['api_equivalent_cost_usd'], 0.00227)

    def test_rejects_impossible_usage(self):
        with self.assertRaises(ValueError):
            summarize_usage([{'input_tokens': 100, 'cached_input_tokens': 101,
                              'output_tokens': 2, 'reasoning_output_tokens': 1}], 'gpt-6.1-sol')


if __name__ == '__main__':
    unittest.main()
