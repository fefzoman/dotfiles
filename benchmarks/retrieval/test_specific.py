import unittest

from specific import SCOPES, oracle, uses_ast_query


class SpecificOracleTests(unittest.TestCase):
    def test_ast_method_requires_query_not_just_help(self):
        self.assertTrue(uses_ast_query("ast-grep scan --inline-rules '{}' PATH"))
        self.assertTrue(uses_ast_query("['ast-grep','run','--kind','call']"))
        self.assertFalse(uses_ast_query("ast-grep run --help; ast-grep scan --help"))
        self.assertFalse(uses_ast_query("ast-grep run   --help"))
        self.assertFalse(uses_ast_query("['ast-grep','run','--help']"))

    def test_keyword_order_multiline_and_nested_ownership(self):
        source = '''text = "f(shell=True)"
# f(shell=True)
f(other=1,
  shell=True, last=2)
f(shell=False)
outer(inner(shell=True))
'''
        self.assertEqual(oracle(source, "shell_true"),
                         [dict(file=SCOPES["shell_true"], line=line) for line in (3, 6)])

    def test_first_argument_is_exact_name_including_context_manager(self):
        source = '''self.assertRaises(ValueError)
self.assertRaises(TypeError)
self.assertRaises((ValueError, TypeError))
with self.assertRaises(ValueError): pass
text = "self.assertRaises(ValueError)"
'''
        self.assertEqual(oracle(source, "raises_value"),
                         [dict(file=SCOPES["raises_value"], line=line) for line in (1, 4)])


if __name__ == "__main__":
    unittest.main()
