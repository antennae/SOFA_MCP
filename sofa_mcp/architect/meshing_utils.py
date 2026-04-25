"""
Utilities for STL-to-volume mesh conversion using GMSH.
"""

from contextlib import contextmanager
from typing import Dict, List

import gmsh  # type: ignore
import numpy as np
import pymeshlab  # type: ignore
from scipy.spatial import cKDTree  # type: ignore


@contextmanager
def gmsh_context(model_name: str, verbosity: int = 0):
    """Optimized GMSH context manager."""
    try:
        if not gmsh.isInitialized():
            # gmsh.initialize() installs SIGINT/SIGTERM handlers via signal.signal,
            # which Python forbids outside the main thread. FastMCP dispatches tool
            # calls on worker threads, so suppress signal installation during init.
            import signal as _signal
            _orig_signal = _signal.signal
            _signal.signal = lambda *a, **k: None
            try:
                gmsh.initialize()
            finally:
                _signal.signal = _orig_signal

        gmsh.model.add(model_name)
        gmsh.option.setNumber("General.Verbosity", verbosity)
        yield
    finally:
        # gmsh.finalize()
        gmsh.model.remove()


def get_vertex_and_face_matrix(file_name: str):
    """
    Read the surface mesh and return the vertex and face matrix.

    Load the surface mesh of the prostate.
    Simplify and smooth it using meshlab
    Read the vertex and face matrix

    Args:
        file_name (str): File name of the surface mesh
    """
    ms = pymeshlab.MeshSet()  # pylint: disable=no-member
    ms.load_new_mesh(file_name)
    vertex = ms.current_mesh().vertex_matrix()
    faces = ms.current_mesh().face_matrix()
    return vertex, faces


def add_vertex_to_gmsh_model(vertex_list: list):
    """
    Add vertex to the Gmsh model.

    Args:
        vertex_list (list): List of vertices
    """
    point_list = []
    for i, vertex in enumerate(vertex_list):
        x = float(vertex[0])
        y = float(vertex[1])
        z = float(vertex[2])
        try:
            point_tag = gmsh.model.occ.addPoint(x, y, z, -1)
            point_list.append(point_tag)
        except Exception as e:
            print(f"Error adding point {i} at ({x}, {y}, {z}): {e}")
            raise
    gmsh.model.occ.synchronize()
    return point_list


def add_surface_and_volume(face_matrix: list, point_list: list):
    """
    Create the surface mesh.

    Read face matrix and add curve to the Gmsh model
    keep track of the existing curve in a dictionary
    Then create curve loop and surface based on face matrix

    Args:
        face_matrix (list): List of faces with vertex index
        point_list (list): List of points in the gmsh
    """
    curved_loop_list = []
    surface_list = []
    curve_dict = {}
    skipped_faces = 0

    for face_idx, face_list in enumerate(face_matrix):
        try:
            # create curve list with direction
            curve_list = [
                (face_list[0], face_list[1]),
                (face_list[1], face_list[2]),
                (face_list[2], face_list[0]),
            ]
            surface_curve = []

            for current_curve in curve_list:
                current_curve_reverse = (current_curve[1], current_curve[0])

                # Skip if trying to create line between same points
                if current_curve[0] == current_curve[1]:
                    print(f"Skipping degenerate curve: {current_curve}")
                    break

                # check if current curve are in the dictionary
                flag_current_curve_in_dict = current_curve in curve_dict
                flag_current_curve_in_dict_reverse = (
                    current_curve_reverse in curve_dict
                )

                if (
                    not flag_current_curve_in_dict
                    and not flag_current_curve_in_dict_reverse
                ):
                    try:
                        # add new curve to the dictionary
                        curve_dict[current_curve] = gmsh.model.occ.addLine(
                            point_list[current_curve[0]],
                            point_list[current_curve[1]],
                        )
                        surface_curve.append(curve_dict[current_curve])
                    except Exception as e:
                        print(
                            f"Error creating line between points "
                            f"{current_curve[0]} "
                            f"({point_list[current_curve[0]]}) "
                            f"and {current_curve[1]} "
                            f"({point_list[current_curve[1]]}): {e}"
                        )
                        print(f"Face {face_idx}: {face_list}")
                        break

                elif flag_current_curve_in_dict:
                    surface_curve.append(curve_dict[current_curve])
                elif flag_current_curve_in_dict_reverse:
                    surface_curve.append(-curve_dict[current_curve_reverse])

            # Only create surface if we have 3 valid curves
            if len(surface_curve) == 3:
                curved_loop_id = gmsh.model.occ.addCurveLoop(surface_curve)
                curved_loop_list.append(curved_loop_id)
                surface_id = gmsh.model.occ.addPlaneSurface([curved_loop_id])
                surface_list.append(surface_id)
            else:
                skipped_faces += 1

        except Exception as e:
            print(f"Error processing face {face_idx}: {e}")
            skipped_faces += 1
            continue

    if not surface_list:
        raise Exception("No valid surfaces created")

    # Step 4: Create surface loop and volume
    volume = gmsh.model.occ.addVolume(
        [gmsh.model.occ.addSurfaceLoop(surface_list)]
    )

    gmsh.model.occ.synchronize()
    return volume


def mesh_3d_and_save(
    mesh_size_factor: float = 1, file_name: str = "volume.vtk"
):
    """
    Set up meshing options, generate the mesh and save the mesh.

    Args:
        mesh_size_factor (float, optional): Mesh size factor. Defaults to 1.
        file_name (str, optional): File name to save the mesh.
                    Defaults to "volume.vtk".
    """
    gmsh.option.setNumber("Mesh.MeshSizeFactor", mesh_size_factor)
    gmsh.option.setNumber(
        "Mesh.Algorithm3D", 4
    )  # Frontal-Delaunay, more robust
    gmsh.model.mesh.generate(2)
    gmsh.model.mesh.removeDuplicateNodes()
    gmsh.model.mesh.removeDuplicateElements()
    gmsh.model.mesh.generate(3)
    gmsh.model.mesh.optimize()
    gmsh.write(file_name)


def mesh_2d_and_save(
    mesh_size_factor: float = 1, file_name: str = "surface.stl"
):
    """
    Set up meshing options, generate the mesh and save the mesh.

    Args:
        mesh_size_factor (float, optional): Mesh size factor. Defaults to 1.
        file_name (str, optional): File name to save the mesh.
                            Defaults to "surface.stl".
    """
    gmsh.option.setNumber("Mesh.MeshSizeFactor", mesh_size_factor)
    gmsh.model.mesh.generate(2)
    gmsh.write(file_name)


def remove_duplicate_vertices(vertices, faces, tolerance=1e-3):
    """
    Remove duplicate vertices and update face indices accordingly.

    Args:
        vertices: numpy array of vertex coordinates
        faces: numpy array of face vertex indices
        tolerance: tolerance for considering vertices as duplicates

    Returns:
        unique_vertices: array of unique vertices
        updated_faces: array of faces with updated indices
    """
    # Build KDTree for efficient nearest neighbor search
    tree = cKDTree(vertices)

    # Find all pairs of vertices within tolerance
    pairs = tree.query_pairs(tolerance)

    # Create mapping from old indices to new indices
    vertex_mapping = list(range(len(vertices)))

    # Process pairs to create equivalence classes
    for i, j in pairs:
        # Map both to the smaller index
        min_idx = min(vertex_mapping[i], vertex_mapping[j])
        vertex_mapping[i] = min_idx
        vertex_mapping[j] = min_idx

    # Compress the mapping to get final indices
    unique_indices: List[int] = []
    final_mapping: Dict[int, int] = {}

    for i in range(len(vertices)):
        root = vertex_mapping[i]
        if root not in final_mapping:
            final_mapping[root] = len(unique_indices)
            unique_indices.append(i)
        vertex_mapping[i] = final_mapping[root]

    # Get unique vertices
    unique_vertices = vertices[unique_indices]

    # Update face indices
    updated_faces = []
    for face in faces:
        new_face = [vertex_mapping[old_idx] for old_idx in face]
        # Only add face if all vertices are different
        if len(set(new_face)) == 3:
            updated_faces.append(new_face)
        else:
            print(f"Skipping degenerate face: {new_face} (original: {face})")

    print(f"Removed {len(vertices) - len(unique_vertices)} duplicate vertices")
    return unique_vertices, np.array(updated_faces)


def load_stl_into_gmsh(file_name, remove_duplicates=False):
    """
    Load STL file into gmsh by creating new model with all conectivities.

    Args:
        file_name (str): The name of the STL file to load
        remove_duplicates (bool): Whether to remove duplicate vertices.
                            Defaults to True.
    """
    mesh_vertex_matrix, mesh_face_matrix = get_vertex_and_face_matrix(
        file_name
    )

    if remove_duplicates:
        # Remove duplicate vertices and update face indices
        unique_vertices, face_mapping = remove_duplicate_vertices(
            mesh_vertex_matrix, mesh_face_matrix
        )

        print(
            f"Original vertices: {len(mesh_vertex_matrix)}, "
            f"Unique vertices: {len(unique_vertices)}"
        )

        gmsh_point_list = add_vertex_to_gmsh_model(unique_vertices)
        volume_tag = add_surface_and_volume(face_mapping, gmsh_point_list)
    else:
        gmsh_point_list = add_vertex_to_gmsh_model(mesh_vertex_matrix)
        volume_tag = add_surface_and_volume(mesh_face_matrix, gmsh_point_list)

    return volume_tag


def gmsh_cut(
    mesh_tag: int,
    cut_mesh_tag: int,
):
    """
    Cut the mesh with the cut mesh.

    Args:
        mesh_tag (int): The tag of the mesh to cut.
        cut_mesh_tag (int): The tag of the mesh to cut with.

    Returns:
        cut_mesh_tag (int): The tag of the cut mesh.
    """
    gmsh.model.occ.synchronize()
    # Cut the mesh with the cut mesh
    dim_tag_cut_output = gmsh.model.occ.cut(
        [(3, mesh_tag)], [(3, cut_mesh_tag)]
    )
    output_volume_tag = dim_tag_cut_output[0][0][1]
    gmsh.model.occ.synchronize()
    return output_volume_tag


def gmsh_fuse(
    mesh_tag: int,
    fuse_mesh_tag: int,
):
    """
    Fuse the mesh with the fuse mesh.

    Args:
        mesh_tag (int): The tag of the mesh to fuse.
        fuse_mesh_tag (int): The tag of the mesh to fuse with.\

    Returns:
        fused_mesh_tag (int): The tag of the fused mesh.
    """
    gmsh.model.occ.synchronize()
    # Fuse the mesh with the fuse mesh
    dim_tag_fuse_output = gmsh.model.occ.fuse(
        [(3, mesh_tag)], [(3, fuse_mesh_tag)]
    )
    output_volume_tag = dim_tag_fuse_output[0][0][1]
    gmsh.model.occ.synchronize()
    return output_volume_tag


def gmsh_intersect(
    mesh_tag: int,
    intersect_mesh_tag: int,
):
    """
    Intersect the mesh with the intersect mesh.

    Args:
        mesh_tag (int): The tag of the mesh to intersect.
        intersect_mesh_tag (int): The tag of the mesh to intersect with.

    Returns:
        intersected_mesh_tag (int): The tag of the intersected mesh.
    """
    gmsh.model.occ.synchronize()
    # Intersect the mesh with the intersect mesh
    dim_tag_intersect_output = gmsh.model.occ.intersect(
        [(3, mesh_tag)], [(3, intersect_mesh_tag)]
    )
    output_volume_tag = dim_tag_intersect_output[0][0][1]
    gmsh.model.occ.synchronize()
    return output_volume_tag
