import os
from datetime import datetime

from sofa_mcp.architect.meshing_utils import (
    gmsh_context,
    load_stl_into_gmsh,
    mesh_3d_and_save,
)


def _results_dir() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(project_root, ".sofa_mcp_results")
    os.makedirs(path, exist_ok=True)
    return path


def generate_volume_mesh(
    stl_path: str,
    output_path: str = None,
    mesh_size_factor: float = 1.0,
    remove_duplicates: bool = True,
) -> dict:
    """
    Convert a surface STL mesh to a volumetric VTK mesh using GMSH.

    Args:
        stl_path: Absolute path to the input STL surface mesh.
        output_path: Where to save the output .vtk file.
                     Defaults to .sofa_mcp_results/volume_<timestamp>.vtk
        mesh_size_factor: GMSH mesh density control. Lower = finer mesh.
                          Defaults to 1.0.
        remove_duplicates: Whether to deduplicate vertices before meshing.
                           Recommended True for most STL files.

    Returns:
        A dictionary containing:
            - success: Boolean indicating success.
            - output_file: Absolute path to the generated .vtk file.
            - message: Hint for referencing the mesh in a SOFA scene.
            - error: Error message (if failed).
    """
    if not os.path.exists(stl_path):
        return {"success": False, "error": f"STL file not found: {stl_path}"}

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(_results_dir(), f"volume_{timestamp}.vtk")

    try:
        model_name = f"vol_{os.path.basename(stl_path)}_{id(stl_path)}"
        with gmsh_context(model_name):
            load_stl_into_gmsh(stl_path, remove_duplicates=remove_duplicates)
            mesh_3d_and_save(mesh_size_factor=mesh_size_factor, file_name=output_path)

        return {
            "success": True,
            "output_file": output_path,
            "message": f"Load in SOFA with: MeshVTKLoader(filename='{output_path}')",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
