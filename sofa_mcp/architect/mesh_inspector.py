"""
mesh_inspector.py


Provides functionality to inspect mesh files and extract information
such as bounding boxes.
"""

import os
import trimesh


def get_mesh_bounding_box(mesh_path: str) -> dict:
    """
    Reads a mesh file and returns its bounding box.
    """
    try:
        mesh = trimesh.load(mesh_path)
        bounding_box = {
            "min": mesh.bounds[0].tolist(),
            "max": mesh.bounds[1].tolist(),
        }
        return bounding_box
    except Exception as e:
        return {"error": str(e)}


def inspect_mesh_topology(mesh_path: str) -> str:
    """
    Reads a mesh file and determines if it is a volumetric mesh (tetrahedra/hexahedra)
    or a surface mesh (triangles).
    """
    try:
        # Load the mesh to ensure it's a valid mesh file for trimesh
        trimesh.load(mesh_path) # We don't need the returned object for this logic

        # Heuristic based on file extension
        # Common volumetric mesh formats: VTK (unstructured grid), MSH
        # Common surface mesh formats: STL, OBJ, PLY
        file_extension = os.path.splitext(mesh_path)[1].lower()

        if file_extension == ".vtk" or file_extension == ".msh":
            return "Volumetric mesh (e.g., tetrahedra, hexahedra)"
        elif file_extension == ".stl" or file_extension == ".obj" or file_extension == ".ply":
            return "Surface mesh (e.g., triangles)"
        else:
            return "Unknown or unsupported mesh type"
    except Exception as e:
        return f"Error inspecting mesh topology: {str(e)}"
