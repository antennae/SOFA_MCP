import unittest
from sofa_mcp.architect.scene_writer import (
    write_and_test_scene,
    validate_scene,
    write_scene,
    summarize_scene,
    load_scene,
    patch_scene,
)
import os
import pathlib

class TestSceneWriter(unittest.TestCase):
    def test_summarize_scene(self):
        script = """
def add_scene_content(rootNode):
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("MechanicalObject", position=[0, 0, 0])

"""
        result = summarize_scene(script)
        self.assertTrue(result["success"], f"Failed with: {result.get('error')}")
        self.assertGreaterEqual(result.get("node_count", 0), 1)
        self.assertGreaterEqual(result.get("object_count", 0), 1)
        self.assertGreaterEqual(result.get("mechanical_object_count", 0), 1)

        checks = result.get("checks", [])
        check_names = {c.get("name") for c in checks}
        self.assertIn("has_mechanical_object", check_names)
        self.assertIn("has_animation_loop", check_names)
        self.assertIn("has_constraint_solver", check_names)
        self.assertIn("baseline_components_present", check_names)

    def test_validate_scene_success(self):
        script = """
def add_scene_content(rootNode):
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("MechanicalObject", position=[0, 0, 0])

"""
        result = validate_scene(script)
        self.assertTrue(result["success"], f"Failed with: {result.get('error')}")
        self.assertIn("SUCCESS:", result.get("stdout", ""))

    def test_write_scene_writes_file(self):
        script = """
def add_scene_content(rootNode):
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("MechanicalObject", position=[0, 0, 0])

"""
        output_file = "written_scene.py"
        result = write_scene(script, output_file)
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(output_file))

        with open(output_file, "r") as f:
            contents = f.read()
        self.assertIn("def createScene", contents)
        self.assertIn("def add_scene_content", contents)

        if os.path.exists(output_file):
            os.remove(output_file)

    def test_load_scene_reads_file(self):
        script = """
def add_scene_content(rootNode):
    rootNode.addObject(\"RequiredPlugin\", pluginName=\"Sofa.Component.StateContainer\")
    rootNode.addObject(\"MechanicalObject\", position=[0, 0, 0])

"""
        output_file = "load_scene_test.py"
        try:
            write_scene(script, output_file)
            loaded = load_scene(output_file)
            self.assertTrue(loaded["success"], loaded.get("error"))
            self.assertIn("def createScene", loaded.get("content", ""))
            self.assertIn("def add_scene_content", loaded.get("content", ""))
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)

    def test_patch_scene_insert_after_anchor(self):
        script = """
def add_scene_content(rootNode):
    rootNode.addObject(\"RequiredPlugin\", pluginName=\"Sofa.Component.StateContainer\")
    rootNode.addObject(\"MechanicalObject\", position=[0, 0, 0])

"""
        output_file = "patch_scene_test.py"
        try:
            write_scene(script, output_file)

            patch = {
                "op": "insert_after",
                "anchor": "def add_scene_content(rootNode):",
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
        script = """
def add_scene_content(rootNode):
    rootNode.addObject(\"MechanicalObject\", position=[0, 0, 0])

"""
        output_file = "patch_scene_missing_anchor.py"
        try:
            write_scene(script, output_file)
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
        script = """
def add_scene_content(rootNode):
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("MechanicalObject", position=[0, 0, 0])

"""
        output_file = "test_scene.py"
        result = write_and_test_scene(script, output_file)
        
        self.assertTrue(result["success"], f"Failed with: {result.get('error')}")
        self.assertTrue(os.path.exists(output_file))
        
        if os.path.exists(output_file):
            os.remove(output_file)

    def test_failing_scene(self):
        # Missing add_scene_content
        script = """
import Sofa
"""
        output_file = "failing_scene.py"
        result = write_and_test_scene(script, output_file)
        
        self.assertFalse(result["success"])
        self.assertIn("ERROR: The provided script_content must define a function called 'add_scene_content(parent_node)'", result["error"])

if __name__ == "__main__":
    unittest.main()
