import os
import unittest

from sofa_mcp.architect.scene_writer import (
    load_scene,
    patch_scene,
    summarize_scene,
    validate_scene,
    write_and_test_scene,
    write_scene,
)


MINIMAL_SCENE = """
def createScene(rootNode):
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("MechanicalObject", position=[0, 0, 0])
"""


class TestSceneWriter(unittest.TestCase):
    def test_summarize_scene(self):
        result = summarize_scene(MINIMAL_SCENE)
        self.assertTrue(result["success"], f"Failed with: {result.get('error')}")
        self.assertGreaterEqual(result.get("node_count", 0), 1)
        self.assertGreaterEqual(result.get("object_count", 0), 1)
        self.assertGreaterEqual(result.get("mechanical_object_count", 0), 1)

        rule_slugs = {c.get("rule") for c in result.get("checks", [])}
        # Each Health Rule emits one entry per scene (with severity ok / warning / error).
        for slug in (
            "rule_1_plugins",
            "rule_2_animation_loop",
            "rule_3_time_integration",
            "rule_4_linear_solver",
            "rule_5_constraint_handling",
            "rule_6_forcefield_mapping",
            "rule_7_topology",
            "rule_8_collision_pipeline",
            "rule_9_units",
        ):
            self.assertIn(slug, rule_slugs)

    def test_validate_scene_success(self):
        result = validate_scene(MINIMAL_SCENE)
        self.assertTrue(result["success"], f"Failed with: {result.get('error')}")
        # The SUCCESS: sentinel is internal to the validation wrapper and is
        # extracted before the stdout field is exposed to the caller.
        self.assertNotIn("SUCCESS: Scene initialized", result.get("stdout", ""))

    def test_write_scene_writes_file(self):
        output_file = "written_scene.py"
        try:
            result = write_scene(MINIMAL_SCENE, output_file)
            self.assertTrue(result["success"])
            self.assertTrue(os.path.exists(output_file))

            with open(output_file, "r", encoding="utf-8") as f:
                contents = f.read()
            self.assertIn("def createScene", contents)
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_write_scene_handles_utf8_in_docstring(self):
        # Em-dash (U+2014) used to crash write_scene with 'ascii' codec
        # can't encode... — see docs/feedback_2026-04-30.
        script = '''
def createScene(rootNode):
    """Soft trunk scene — uses cable actuators."""
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("MechanicalObject", position=[0, 0, 0])
'''
        output_file = "utf8_scene.py"
        try:
            result = write_scene(script, output_file)
            self.assertTrue(result["success"], f"Failed with: {result.get('error')}")
            with open(output_file, "r", encoding="utf-8") as f:
                contents = f.read()
            self.assertIn("Soft trunk scene — uses cable actuators.", contents)
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_load_scene_reads_file(self):
        output_file = "load_scene_test.py"
        try:
            write_scene(MINIMAL_SCENE, output_file)
            loaded = load_scene(output_file)
            self.assertTrue(loaded["success"], loaded.get("error"))
            self.assertIn("def createScene", loaded.get("content", ""))
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_patch_scene_insert_after_anchor(self):
        output_file = "patch_scene_test.py"
        try:
            write_scene(MINIMAL_SCENE, output_file)

            patch = {
                "op": "insert_after",
                "anchor": "def createScene(rootNode):",
                "text": "\n    # patched\n",
                "occurrence": 1,
            }
            patched = patch_scene(output_file, patch)
            self.assertTrue(patched["success"], patched.get("error"))

            loaded = load_scene(output_file)
            self.assertIn("# patched", loaded.get("content", ""))
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_patch_scene_fails_when_anchor_missing(self):
        output_file = "patch_scene_missing_anchor.py"
        try:
            write_scene(MINIMAL_SCENE, output_file)
            patch = {
                "op": "insert_after",
                "anchor": "THIS_ANCHOR_DOES_NOT_EXIST",
                "text": "\n# no-op\n",
            }
            patched = patch_scene(output_file, patch)
            self.assertFalse(patched["success"])
            self.assertIn("anchor", patched.get("error", ""))
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_basic_scene(self):
        output_file = "test_scene.py"
        try:
            result = write_and_test_scene(MINIMAL_SCENE, output_file)
            self.assertTrue(result["success"], f"Failed with: {result.get('error')}")
            self.assertTrue(os.path.exists(output_file))
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_failing_scene(self):
        # No createScene defined → validation must fail loudly.
        script = """
import Sofa
"""
        output_file = "failing_scene.py"
        try:
            result = write_and_test_scene(script, output_file)
            self.assertFalse(result["success"])
            self.assertIn("createScene", result.get("error", ""))
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_validate_scene_demotes_promoted_warning(self):
        # FixedProjectiveConstraint with an out-of-range index triggers
        # SOFA's "Index N not valid" + "Constraint will be removed" warnings.
        # Before the fix, validate_scene returned success=true; now it must
        # demote to success=false and populate init_warnings.
        script = """
def createScene(rootNode):
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.Constraint.Projective")
    rootNode.addObject("MechanicalObject", template="Vec3d",
                       position=[[0, 0, 0], [1, 0, 0]])
    rootNode.addObject("FixedProjectiveConstraint", indices=[42])
"""
        result = validate_scene(script)
        self.assertFalse(
            result["success"],
            f"Expected demoted failure but got success. stdout: {result.get('stdout','')}",
        )
        slugs = {w["pattern"] for w in result.get("init_warnings", [])}
        # At least one of these must fire for this scene.
        self.assertTrue(
            slugs & {"invalid_index", "constraint_removed"},
            f"Expected init_warnings to include invalid_index or constraint_removed; got {slugs}",
        )

    def test_validate_scene_uses_output_dir_for_file_relative_paths(self):
        # When output_filename is passed, the validator subprocess must run
        # with cwd set to the file's eventual directory so that
        # __file__-relative paths resolve correctly. We probe this by
        # writing a marker file next to output_filename and checking that
        # the scene script can see it via __file__-relative lookup.
        import tempfile as _tempfile
        with _tempfile.TemporaryDirectory() as workdir:
            marker = os.path.join(workdir, "marker.txt")
            with open(marker, "w") as f:
                f.write("hello")
            output_file = os.path.join(workdir, "scene.py")
            script = """
import os
def createScene(rootNode):
    here = os.path.dirname(os.path.abspath(__file__))
    marker = os.path.join(here, "marker.txt")
    if not os.path.exists(marker):
        raise RuntimeError(f"marker not found relative to __file__={__file__}")
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("MechanicalObject", position=[0, 0, 0])
"""
            result = validate_scene(script, output_filename=output_file)
            self.assertTrue(
                result["success"],
                f"Expected success when cwd resolves __file__; error: {result.get('error')}",
            )


if __name__ == "__main__":
    unittest.main()
