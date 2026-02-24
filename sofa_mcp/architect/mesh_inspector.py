"""
mesh_inspector.py


Provides functionality to inspect mesh files and extract information
such as bounding boxes.
"""

import os
import math
from typing import Any, Dict, List, Optional, Tuple

import trimesh


def resolve_asset_path(path: str) -> dict:
    """Resolves a user-provided asset path.

    Expands '~', converts to an absolute path, and checks for existence.
    """

    expanded = os.path.expanduser(path)
    absolute = os.path.abspath(expanded)
    exists = os.path.exists(absolute)

    result: Dict[str, Any] = {
        "input": path,
        "path": absolute,
        "exists": exists,
        "is_file": os.path.isfile(absolute) if exists else False,
    }

    if exists and os.path.isfile(absolute):
        try:
            result["size_bytes"] = os.path.getsize(absolute)
        except Exception:
            pass

    if not exists:
        result["error"] = "Path does not exist"

    return result


def _vtk_ascii_parse_points_and_cells(mesh_path: str) -> Tuple[Optional[List[List[float]]], Optional[int], Optional[List[int]]]:
    """Parses a minimal ASCII VTK unstructured grid for POINTS/CELLS/CELL_TYPES.

    Returns (points, cell_count, cell_types) when possible.
    """

    try:
        with open(mesh_path, "r") as f:
            lines = f.read().splitlines()
    except Exception:
        return None, None, None

    points: Optional[List[List[float]]] = None
    cell_count: Optional[int] = None
    cell_types: Optional[List[int]] = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.upper().startswith("POINTS "):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    n_points = int(parts[1])
                except Exception:
                    n_points = 0

                floats: List[float] = []
                j = i + 1
                while j < len(lines) and len(floats) < n_points * 3:
                    for token in lines[j].strip().split():
                        try:
                            floats.append(float(token))
                        except Exception:
                            pass
                    j += 1

                pts: List[List[float]] = []
                for k in range(0, min(len(floats), n_points * 3), 3):
                    pts.append([floats[k], floats[k + 1], floats[k + 2]])
                points = pts
                i = j
                continue

        if line.upper().startswith("CELLS "):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    cell_count = int(parts[1])
                except Exception:
                    cell_count = None

        if line.upper().startswith("CELL_TYPES "):
            parts = line.split()
            n_types = 0
            if len(parts) >= 2:
                try:
                    n_types = int(parts[1])
                except Exception:
                    n_types = 0

            types: List[int] = []
            j = i + 1
            while j < len(lines) and len(types) < n_types:
                for token in lines[j].strip().split():
                    try:
                        types.append(int(token))
                    except Exception:
                        pass
                j += 1

            cell_types = types
            i = j
            continue

        i += 1

    return points, cell_count, cell_types


def _bounds_from_points(points: List[List[float]]) -> Dict[str, List[float]]:
    mins = [float("inf"), float("inf"), float("inf")]
    maxs = [float("-inf"), float("-inf"), float("-inf")]
    for p in points:
        for axis in range(3):
            mins[axis] = min(mins[axis], float(p[axis]))
            maxs[axis] = max(maxs[axis], float(p[axis]))
    return {"min": mins, "max": maxs}


def get_mesh_bounding_box(mesh_path: str) -> dict:
    """
    Reads a mesh file and returns its bounding box.
    """
    try:
        mesh = trimesh.load(mesh_path)

        # trimesh may return a Scene or PointCloud depending on format.
        if hasattr(mesh, "bounds") and mesh.bounds is not None:
            return {
                "min": mesh.bounds[0].tolist(),
                "max": mesh.bounds[1].tolist(),
            }

        # Fallback for simple ASCII VTK
        points, _, _ = _vtk_ascii_parse_points_and_cells(mesh_path)
        if points:
            return _bounds_from_points(points)

        return {"error": "Could not compute bounds"}
    except Exception as e:
        # Fallback for simple ASCII VTK if trimesh load fails
        points, _, _ = _vtk_ascii_parse_points_and_cells(mesh_path)
        if points:
            return _bounds_from_points(points)
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


def mesh_stats(mesh_path: str) -> dict:
    """Returns mesh statistics useful for scene generation.

    Includes bounding box, simple topology classification, and element counts when available.
    """

    resolved = resolve_asset_path(mesh_path)
    if not resolved.get("exists") or not resolved.get("is_file"):
        return {"error": resolved.get("error", "Invalid path"), **resolved}

    absolute_path = resolved["path"]
    ext = os.path.splitext(absolute_path)[1].lower()
    topo_label = inspect_mesh_topology(absolute_path)
    topo_kind = "unknown"
    if topo_label.startswith("Surface mesh"):
        topo_kind = "surface"
    elif topo_label.startswith("Volumetric mesh"):
        topo_kind = "volumetric"

    bbox = get_mesh_bounding_box(absolute_path)
    if "error" in bbox:
        return {"error": bbox["error"], **resolved}

    extent = [bbox["max"][i] - bbox["min"][i] for i in range(3)]
    diag = math.sqrt(sum(float(x) * float(x) for x in extent))

    stats: Dict[str, Any] = {
        "path": absolute_path,
        "extension": ext,
        "topology": topo_label,
        "topology_kind": topo_kind,
        "bounding_box": bbox,
        "bbox_extent": extent,
        "bbox_diagonal": diag,
    }

    # Counts
    if ext in (".vtk", ".msh"):
        points, cell_count, cell_types = _vtk_ascii_parse_points_and_cells(absolute_path)
        if points is not None:
            stats["point_count"] = len(points)
        if cell_count is not None:
            stats["cell_count"] = cell_count
        if cell_types is not None:
            counts: Dict[str, int] = {}
            for t in cell_types:
                key = str(int(t))
                counts[key] = counts.get(key, 0) + 1
            stats["cell_type_counts"] = counts
    else:
        try:
            loaded = trimesh.load(absolute_path)
            if isinstance(loaded, trimesh.Scene):
                meshes = [g for g in loaded.geometry.values() if hasattr(g, "vertices")]
                stats["vertex_count"] = int(sum(len(getattr(m, "vertices", [])) for m in meshes))
                stats["face_count"] = int(sum(len(getattr(m, "faces", [])) for m in meshes))
            else:
                stats["vertex_count"] = int(len(getattr(loaded, "vertices", [])))
                stats["face_count"] = int(len(getattr(loaded, "faces", [])))
        except Exception:
            pass

    return stats
