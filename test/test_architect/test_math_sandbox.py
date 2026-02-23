import unittest
import sys

# Add the sofa_mcp path to the test
sys.path.insert(0, '.')

from sofa_mcp.architect.math_sandbox import run_math_script

class TestMathSandbox(unittest.TestCase):

    def test_run_simple_script(self):
        """Test running a simple script that prints a value."""
        script = "print(2 + 2)"
        result = run_math_script(script)
        self.assertEqual(result.strip(), "4")

    def test_run_script_with_exception(self):
        """Test a script that raises an exception."""
        script = "print(1 / 0)"
        result = run_math_script(script)
        self.assertIn("division by zero", result)

    def test_run_script_with_multiple_lines(self):
        """Test a script with multiple lines and print statements."""
        script = """
a = 5
b = 10
print(a * b)
print('Hello, world!')
"""
        result = run_math_script(script)
        self.assertEqual(result, "50\nHello, world!\n")

    def test_run_empty_script(self):
        """Test running an empty script."""
        script = ""
        result = run_math_script(script)
        self.assertEqual(result, "")

    def test_run_script_with_no_output(self):
        """Test a script that runs but produces no stdout."""
        script = "a = 1"
        result = run_math_script(script)
        self.assertEqual(result, "")
        
    def test_syntax_error(self):
        """Test a script with a syntax error."""
        script = "print('hello"
        result = run_math_script(script)
        self.assertIn("unterminated string literal", result)

if __name__ == '__main__':
    unittest.main()
