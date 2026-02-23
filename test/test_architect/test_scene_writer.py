import unittest
from sofa_mcp.architect.scene_writer import write_and_test_scene
import os
import pathlib

class TestSceneWriter(unittest.TestCase):
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
