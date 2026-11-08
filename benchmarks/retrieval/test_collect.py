import unittest

from collect_code import method_compliant, usage_totals


class NativeUsageTests(unittest.TestCase):
    def record(self, response="one", **changes):
        usage = dict(input_tokens=100, cached_input_tokens=80, cache_write_input_tokens=0,
                     output_tokens=10, reasoning_output_tokens=4)
        usage.update(changes)
        return dict(response_id=response, usage=usage)

    def test_deduplicates_responses_without_double_counting_reasoning_or_cache(self):
        record = self.record()
        result = usage_totals([record, record, self.record("two")])
        self.assertEqual(result["calls"], 2)
        self.assertEqual(result["total_tokens"], 220)
        self.assertEqual(result["uncached_input_tokens"], 40)

    def test_rejects_missing_conflicting_or_impossible_usage(self):
        cases = [[], [self.record(), self.record(output_tokens=11)],
                 [self.record(cached_input_tokens=101)],
                 [self.record(reasoning_output_tokens=11)],
                 [self.record(output_tokens=-1)], [self.record(input_tokens=True)]]
        for records in cases:
            with self.subTest(records=records), self.assertRaises(ValueError):
                usage_totals(records)

    def test_method_check_allows_manual_but_rejects_cross_arm_retrieval(self):
        manual = "mcp__serena__initial_instructions"
        symbol = "mcp__serena__find_symbol"
        docs = "mcp__context7__query_docs"
        self.assertTrue(method_compliant("skill", [manual]))
        self.assertFalse(method_compliant("skill", [manual, symbol]))
        self.assertTrue(method_compliant("serena", [manual, symbol]))
        self.assertFalse(method_compliant("serena", [manual, symbol, docs]))
        self.assertTrue(method_compliant("context7", [manual, docs]))
        self.assertFalse(method_compliant("context7", [docs, symbol]))
