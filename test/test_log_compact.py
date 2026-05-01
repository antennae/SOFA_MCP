"""Pure-function unit tests for `sofa_mcp._log_compact.compact_log`."""

import unittest

from sofa_mcp._log_compact import compact_log


class TestCompactLog(unittest.TestCase):

    def test_empty_input(self):
        out, dropped = compact_log("")
        self.assertEqual(out, "")
        self.assertEqual(dropped, 0)

    def test_shorter_than_tail_returned_verbatim(self):
        text = "line1\nline2\nline3\n"
        out, dropped = compact_log(text, tail_lines=20)
        self.assertEqual(out, text)
        self.assertEqual(dropped, 0)

    def test_all_noise_keeps_only_tail(self):
        noise = ["[INFO] [EulerImplicitSolver(odesolver)] initial f = [1, 2, 3]"] * 100
        text = "\n".join(noise)
        out, dropped = compact_log(text, tail_lines=20)
        self.assertEqual(out.count("\n"), 19)  # 20 lines, 19 internal newlines
        self.assertEqual(dropped, 80)

    def test_allowlist_hits_kept_with_tail(self):
        lines = []
        for i in range(50):
            lines.append(f"[INFO] [Solver] noise iteration_text_{i}")  # not a keep pattern
        lines.insert(10, "[ERROR] something is wrong")
        lines.insert(25, "[WARNING] something else")
        lines.insert(40, '[INFO] [PluginManager]: Loaded plugin "Sofa.Component.X"')
        text = "\n".join(lines)
        out, dropped = compact_log(text, tail_lines=5)
        self.assertIn("[ERROR] something is wrong", out)
        self.assertIn("[WARNING] something else", out)
        self.assertIn('Loaded plugin "Sofa.Component.X"', out)
        # Tail anchor preserved last 5 lines.
        for tail in lines[-5:]:
            self.assertIn(tail, out)
        self.assertGreater(dropped, 0)

    def test_no_duplicate_lines_when_tail_overlaps_signal(self):
        lines = (
            ["[INFO] noise"] * 30
            + ["[ERROR] late error in tail"]
            + ["[INFO] noise"] * 4
        )
        text = "\n".join(lines)
        out, _ = compact_log(text, tail_lines=10)
        # The error line is in the last 10 (tail anchor) AND a signal hit.
        # Must appear exactly once.
        self.assertEqual(out.count("[ERROR] late error in tail"), 1)

    def test_multiline_traceback_preserved(self):
        body = ["[INFO] noise"] * 30
        body.extend([
            "Traceback (most recent call last):",
            '  File "/path/to/scene.py", line 42, in createScene',
            "    rootNode.addObject(\"Bogus\")",
            "  File \"/sofa/Core.py\", line 99, in addObject",
            "    raise FactoryError(...)",
            "FactoryError: Bogus is not a registered class",
        ])
        body.extend(["[INFO] noise"] * 30)  # tail far away from traceback
        text = "\n".join(body)
        out, _ = compact_log(text, tail_lines=5)
        self.assertIn("Traceback (most recent call last):", out)
        self.assertIn("rootNode.addObject(\"Bogus\")", out)
        self.assertIn("FactoryError: Bogus is not a registered class", out)
        self.assertIn('File "/path/to/scene.py", line 42', out)

    def test_traceback_state_closes_on_blank_line(self):
        body = ["[INFO] noise"] * 30
        body.extend([
            "Traceback (most recent call last):",
            '  File "/path/scene.py", line 1, in <module>',
            "    boom",
            "RuntimeError: boom",
            "",
            "  this is now stray indented text after blank line",
        ])
        body.extend(["[INFO] noise"] * 30)
        text = "\n".join(body)
        out, _ = compact_log(text, tail_lines=5)
        self.assertIn("RuntimeError: boom", out)
        # The stray indented line after the blank should NOT be in output.
        self.assertNotIn("this is now stray indented text after blank line", out)

    def test_f_vector_dump_dropped(self):
        lines = ["[INFO] [EulerImplicitSolver(odesolver)] initial f = [1.0, 2.0, 3.0]"] * 50
        lines.append("[INFO] [PluginManager]: Loaded plugin \"Sofa.Component.X\"")
        lines.extend(["[INFO] noise"] * 30)
        text = "\n".join(lines)
        out, dropped = compact_log(text, tail_lines=5)
        # The f-vector dump lines have no allowlist hit and are not in the tail.
        # Should be heavily dropped.
        self.assertNotIn("initial f = [1.0, 2.0, 3.0]", out)
        self.assertIn('Loaded plugin "Sofa.Component.X"', out)
        self.assertGreater(dropped, 40)

    def test_plugin_load_kept(self):
        text = "\n".join([
            "[INFO]    [PluginManager]: loaded plugin \"Sofa.Component.Engine.Select\"",
            *(["[INFO] f-vector noise"] * 100),
        ])
        out, _ = compact_log(text, tail_lines=5)
        self.assertIn("Loaded plugin", out.replace("loaded plugin", "Loaded plugin"))

    def test_iterations_pattern_keeps_solver_print(self):
        text = "\n".join([
            *(["[INFO] noise"] * 50),
            "CGLinearSolver(default) : 25 iterations",
            *(["[INFO] noise"] * 50),
        ])
        out, _ = compact_log(text, tail_lines=5)
        self.assertIn("CGLinearSolver(default) : 25 iterations", out)

    def test_qp_infeasible_kept(self):
        text = "\n".join([
            *(["[INFO] noise"] * 30),
            "[WARNING] [QPInverseProblemSolver] QP infeasible at step 3",
            *(["[INFO] noise"] * 30),
        ])
        out, _ = compact_log(text, tail_lines=5)
        self.assertIn("QP infeasible at step 3", out)

    def test_iterations_word_alone_does_not_match(self):
        # The pattern requires `\d+ iterations` — a bare word "Iteration" in a
        # plugin name should not trigger.
        text = "\n".join([
            *(["[INFO] noise"] * 50),
            "[INFO] Plugin Sofa.Component.Engine.Iteration was loaded",
            *(["[INFO] noise"] * 50),
        ])
        out, _ = compact_log(text, tail_lines=5)
        # "Plugin ... loaded" hits the `Loaded plugin` pattern? No — the pattern
        # is "Loaded plugin" (case-insensitive); the line says "was loaded",
        # different word order. So it should NOT be kept.
        self.assertNotIn("Engine.Iteration was loaded", out)

    def test_preserves_trailing_newline(self):
        body = ["[INFO] noise"] * 100
        text = "\n".join(body) + "\n"
        out, _ = compact_log(text, tail_lines=5)
        self.assertTrue(out.endswith("\n"))

    def test_omits_trailing_newline_when_input_lacks_it(self):
        body = ["[INFO] noise"] * 100
        text = "\n".join(body)  # no trailing newline
        out, _ = compact_log(text, tail_lines=5)
        self.assertFalse(out.endswith("\n"))

    def test_dropped_count_accurate(self):
        # 100 noise lines, 1 signal, tail=5. Kept = 1 signal + 5 tail = 6
        # (but the signal is somewhere in the middle, no overlap with tail).
        # Dropped = 101 - 6 = 95.
        lines = ["[INFO] noise"] * 100
        lines.insert(50, "[ERROR] middle error")
        text = "\n".join(lines)
        out, dropped = compact_log(text, tail_lines=5)
        kept_count = out.count("\n") + 1
        self.assertEqual(kept_count + dropped, 101)


if __name__ == "__main__":
    unittest.main()
