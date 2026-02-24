import unittest
import os
import shutil
import tempfile
import sys

# Add the sofa_mcp path to the test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sofa_mcp.optimizer.patcher import update_data_field

class TestPatcher(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_update_existing_field(self):
        scene_content = """
def createScene(root):
    root.addObject("MechanicalObject", name="mo", position=[0, 0, 0])
"""
        scene_path = os.path.join(self.test_dir, "scene_update.py")
        with open(scene_path, "w") as f:
            f.write(scene_content)
            
        result = update_data_field(scene_path, "mo", "position", [1, 2, 3])
        self.assertTrue(result["success"], f"Update failed: {result.get('error')}")
        
        with open(scene_path, "r") as f:
            content = f.read()
        
        self.assertIn("position=[1, 2, 3]", content)

    def test_add_new_field(self):
        scene_content = """
def createScene(root):
    root.addObject("MechanicalObject", name="mo")
"""
        scene_path = os.path.join(self.test_dir, "scene_add.py")
        with open(scene_path, "w") as f:
            f.write(scene_content)
            
        result = update_data_field(scene_path, "mo", "totalMass", 10.0)
        self.assertTrue(result["success"], f"Add failed: {result.get('error')}")
        
        with open(scene_path, "r") as f:
            content = f.read()
            
        self.assertIn("totalMass=10.0", content)

    def test_add_new_field_append(self):
        scene_content = """
def createScene(root):
    root.addObject("MechanicalObject", name="mo", position=[0,0,0])
"""
        scene_path = os.path.join(self.test_dir, "scene_append.py")
        with open(scene_path, "w") as f:
            f.write(scene_content)
            
        result = update_data_field(scene_path, "mo", "showObject", True)
        self.assertTrue(result["success"], f"Append failed: {result.get('error')}")
        
        with open(scene_path, "r") as f:
            content = f.read()
            
        self.assertIn("showObject=True", content)
        self.assertIn("position=[0,0,0]", content)

    def test_object_not_found(self):
        scene_content = """
def createScene(root):
    root.addObject("MechanicalObject", name="other")
"""
        scene_path = os.path.join(self.test_dir, "scene_not_found.py")
        with open(scene_path, "w") as f:
            f.write(scene_content)
            
        result = update_data_field(scene_path, "mo", "position", [1, 1, 1])
        self.assertFalse(result["success"])
        self.assertIn("Object 'mo' not found", result["error"])

    def test_file_not_found(self):
        result = update_data_field("non_existent_file.py", "mo", "field", 1)
        self.assertFalse(result["success"])
        self.assertIn("File not found", result["error"])

    def test_syntax_error(self):
        scene_content = """
def createScene(root):
    root.addObject("MechanicalObject", name="mo", position=[0, 0, 0] # Missing closing parenthesis
"""
        scene_path = os.path.join(self.test_dir, "scene_syntax_error.py")
        with open(scene_path, "w") as f:
            f.write(scene_content)
            
        result = update_data_field(scene_path, "mo", "position", [1, 1, 1])
        self.assertFalse(result["success"])
        self.assertIn("Syntax error", result["error"])