"""
math_sandbox.py

Provides a sandbox environment to execute arbitrary math scripts
and capture their output.
"""

import io
import contextlib


def run_math_script(script: str) -> str:
    """
    Executes a python script and returns the output.
    """
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            exec(script)
        except Exception as e:
            return str(e)
    return output.getvalue()
