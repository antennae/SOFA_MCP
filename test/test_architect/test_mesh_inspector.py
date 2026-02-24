import os
import unittest
import os
import shutil
import numpy as np
import trimesh
import sys

# Add the sofa_mcp path to the test
sys.path.insert(0, '.')

from sofa_mcp.architect.mesh_inspector import (
    get_mesh_bounding_box,
    inspect_mesh_topology,
    resolve_asset_path,
    mesh_stats,
)

class TestMeshInspector(unittest.TestCase):

    def setUp(self):
        """Set up a temporary directory with mesh files for testing."""
        self.test_dir = "temp_test_meshes"
        os.makedirs(self.test_dir, exist_ok=True)

        # 1. Create a surface mesh (STL file with a single triangle)
        self.surface_mesh_path = os.path.join(self.test_dir, "surface_mesh.stl")
        tri_vertices = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        tri_faces = np.array([[0, 1, 2]])
        tri_mesh = trimesh.Trimesh(vertices=tri_vertices, faces=tri_faces)
        tri_mesh.export(self.surface_mesh_path)

        # 2. Create a volumetric mesh (VTK file with a single tetrahedron)
        self.volume_mesh_path = os.path.join(self.test_dir, "volume_mesh.vtk")
        vtk_content = """# vtk DataFile Version 2.0
My Tetrahedron
ASCII
DATASET UNSTRUCTURED_GRID
POINTS 4 float
0 0 0
1 0 0
0 1 0
0 0 1
CELLS 1 5
4 0 1 2 3
CELL_TYPES 1
10
"""
        with open(self.volume_mesh_path, "w") as f:
            f.write(vtk_content)

    def tearDown(self):
        """Remove the temporary directory."""
        shutil.rmtree(self.test_dir)

    def test_get_mesh_bounding_box_surface(self):
        """Test bounding box calculation for a surface mesh."""
        bbox = get_mesh_bounding_box(self.surface_mesh_path)
        self.assertNotIn("error", bbox)
        self.assertEqual(bbox["min"], [0.0, 0.0, 0.0])
        self.assertEqual(bbox["max"], [1.0, 1.0, 0.0])

    def test_get_mesh_bounding_box_volume(self):
        """Test bounding box calculation for a volumetric mesh."""
        bbox = get_mesh_bounding_box(self.volume_mesh_path)
        self.assertNotIn("error", bbox)
        self.assertEqual(bbox["min"], [0.0, 0.0, 0.0])
        self.assertEqual(bbox["max"], [1.0, 1.0, 1.0])
        
    def test_get_mesh_bounding_box_file_not_found(self):
        """Test bounding box calculation with a non-existent file."""
        result = get_mesh_bounding_box("non_existent_file.stl")
        self.assertIn("error", result)

    def test_inspect_mesh_topology_surface(self):
        """Test topology inspection for a surface mesh."""
        result = inspect_mesh_topology(self.surface_mesh_path)
        self.assertEqual(result, "Surface mesh (e.g., triangles)")

    def test_inspect_mesh_topology_volume(self):
        """Test topology inspection for a volumetric mesh."""
        result = inspect_mesh_topology(self.volume_mesh_path)
        self.assertEqual(result, "Volumetric mesh (e.g., tetrahedra, hexahedra)")

    def test_inspect_mesh_topology_file_not_found(self):
        """Test topology inspection with a non-existent file."""
        result = inspect_mesh_topology("non_existent_file.vtk")
        self.assertTrue(result.startswith("Error inspecting mesh topology:"))

    def test_resolve_asset_path_exists(self):
        result = resolve_asset_path(self.surface_mesh_path)
        self.assertTrue(result["exists"])
        self.assertTrue(result["is_file"])
        self.assertIn("path", result)

    def test_resolve_asset_path_missing(self):
        result = resolve_asset_path("does_not_exist.stl")
        self.assertFalse(result["exists"])
        self.assertIn("error", result)

    def test_mesh_stats_surface(self):
        stats = mesh_stats(self.surface_mesh_path)
        self.assertNotIn("error", stats)
        self.assertEqual(stats.get("topology_kind"), "surface")
        self.assertEqual(stats.get("vertex_count"), 3)
        self.assertEqual(stats.get("face_count"), 1)
        self.assertIn("bounding_box", stats)

    def test_mesh_stats_volume_vtk(self):
        stats = mesh_stats(self.volume_mesh_path)
        self.assertNotIn("error", stats)
        self.assertEqual(stats.get("topology_kind"), "volumetric")
        self.assertEqual(stats.get("point_count"), 4)
        self.assertEqual(stats.get("cell_count"), 1)
        self.assertIn("bounding_box", stats)

if __name__ == '__main__':
    unittest.main()
