"""
Headless renderer for SOFA scenes.

Runs a scene for N steps and produces a PNG of the final state by auto-discovering
MechanicalObject positions and reusing the visual-color hint from sibling OglModel
nodes when present.
"""
import os
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import sys
import importlib.util
from datetime import datetime

import numpy as np
import pyvista as pv

import Sofa.Core
import Sofa.Simulation


_DEFAULT_PALETTE = [
    (0.85, 0.30, 0.30),
    (0.30, 0.75, 0.30),
    (0.30, 0.45, 0.85),
    (0.85, 0.65, 0.20),
    (0.55, 0.40, 0.75),
    (0.40, 0.70, 0.70),
]


def _load_scene_module(scene_path: str):
    module_name = f"render_scene_{os.path.basename(scene_path).replace('.', '_')}_{id(scene_path)}"
    spec = importlib.util.spec_from_file_location(module_name, scene_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load scene from {scene_path}")
    scene_module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = scene_module
    try:
        spec.loader.exec_module(scene_module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return scene_module, module_name


def _walk_nodes(node, path="/"):
    yield path, node
    for child in getattr(node, "children", []):
        try:
            child_name = child.getName() if hasattr(child, "getName") else "child"
        except Exception:
            child_name = "child"
        child_path = path.rstrip("/") + "/" + str(child_name)
        yield from _walk_nodes(child, child_path)


def _try_get_color(node) -> list | None:
    """Heuristic: check this node and its children for an OglModel color."""
    candidates = [node] + list(getattr(node, "children", []))
    for cand in candidates:
        for obj in getattr(cand, "objects", []):
            try:
                if hasattr(obj, "getClassName") and obj.getClassName() in ("OglModel", "VisualModel"):
                    cd = obj.findData("color")
                    if cd is not None:
                        val = cd.value
                        if hasattr(val, "tolist"):
                            val = val.tolist()
                        if isinstance(val, (list, tuple)) and len(val) >= 3:
                            return [float(c) for c in val[:3]]
            except Exception:
                continue
    return None


def _find_mechanical_objects(root):
    found = []
    for path, node in _walk_nodes(root):
        for obj in getattr(node, "objects", []):
            try:
                if hasattr(obj, "getClassName") and obj.getClassName() == "MechanicalObject":
                    color = _try_get_color(node)
                    found.append((path, obj, color))
            except Exception:
                continue
    return found


_VISUAL_CLASSES = {"OglModel", "VisualModelImpl", "VisualModel"}


def _read_position_array(obj):
    """Read a `position` Data field as an (N, 3) float array, or None."""
    pdata = obj.findData("position") if hasattr(obj, "findData") else None
    if pdata is None:
        return None
    try:
        arr = np.array(pdata.value, dtype=float)
    except Exception:
        return None
    if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] < 3:
        return None
    return arr[:, :3]


def _extract_faces(obj):
    """Read `triangles` from `obj`; if empty, decompose `quads` into
    triangle pairs. Returns an (M, 3) int array or None.
    """
    tdata = obj.findData("triangles") if hasattr(obj, "findData") else None
    if tdata is not None:
        try:
            tris = np.array(tdata.value, dtype=np.int64)
            if tris.ndim == 2 and tris.shape[0] > 0 and tris.shape[1] == 3:
                return tris
        except Exception:
            pass
    qdata = obj.findData("quads") if hasattr(obj, "findData") else None
    if qdata is not None:
        try:
            quads = np.array(qdata.value, dtype=np.int64)
            if quads.ndim == 2 and quads.shape[0] > 0 and quads.shape[1] == 4:
                tri_a = quads[:, [0, 1, 2]]
                tri_b = quads[:, [0, 2, 3]]
                return np.vstack([tri_a, tri_b])
        except Exception:
            pass
    return None


def _read_color(obj):
    """Read RGBA color from a Data field; return RGB tuple or None."""
    cd = obj.findData("color") if hasattr(obj, "findData") else None
    if cd is None:
        return None
    try:
        val = cd.value
        if hasattr(val, "tolist"):
            val = val.tolist()
        if isinstance(val, (list, tuple)) and len(val) >= 3:
            return tuple(float(c) for c in val[:3])
    except Exception:
        return None
    return None


def _find_visual_targets(root):
    """Walk the tree; return (path, points, faces, color, owning_node)
    for every OglModel/VisualModelImpl that exposes both a position
    array and triangles (or decomposable quads)."""
    targets = []
    for path, node in _walk_nodes(root):
        for obj in getattr(node, "objects", []):
            try:
                cls = obj.getClassName() if hasattr(obj, "getClassName") else ""
            except Exception:
                continue
            if cls not in _VISUAL_CLASSES:
                continue
            pts = _read_position_array(obj)
            faces = _extract_faces(obj)
            if pts is None or faces is None:
                continue
            color = _read_color(obj)
            targets.append((path, pts, faces, color, node))
    return targets


def _find_topology_fallback_targets(root, covered_nodes):
    """For each unmapped MechanicalObject in a node NOT already covered
    by a visual target, look for a sibling topology container exposing
    triangles/quads. Return (path, points, faces, color)."""
    targets = []
    for path, node in _walk_nodes(root):
        if node in covered_nodes:
            continue
        if any(child in covered_nodes for _, child in _walk_nodes(node)):
            continue
        mo = None
        topo_faces = None
        for obj in getattr(node, "objects", []):
            try:
                cls = obj.getClassName() if hasattr(obj, "getClassName") else ""
            except Exception:
                continue
            if cls == "MechanicalObject" and mo is None:
                mo = obj
            elif "Topology" in cls and topo_faces is None:
                tri_or_quad = _extract_faces(obj)
                if tri_or_quad is not None:
                    topo_faces = tri_or_quad
        if mo is None or topo_faces is None:
            continue
        pts = _read_position_array(mo)
        if pts is None:
            continue
        targets.append((path, pts, topo_faces, None))
    return targets


def _polydata_from(points, faces):
    """Build a PyVista PolyData from explicit points + triangle indices."""
    n = faces.shape[0]
    flat = np.empty((n, 4), dtype=np.int64)
    flat[:, 0] = 3
    flat[:, 1:] = faces
    return pv.PolyData(points, flat.flatten())


def render_scene_snapshot(
    scene_path: str,
    steps: int = 50,
    dt: float = 0.01,
    output_path: str = None,
    image_size: tuple = (1024, 768),
    background: str = "white",
    show_edges: bool = False,
) -> dict:
    """
    Run a SOFA scene for `steps` simulation steps and render the final state to a PNG.

    Discovery is two-pass:
      1. Visual models (OglModel / VisualModelImpl) — render their explicit
         `position` + `triangles` (decomposing `quads` if needed). Color
         comes from the model's own `color` Data when present.
      2. Mechanical objects on nodes not covered by a visual model — fall
         back to a sibling topology container's triangles, if any.
      3. If neither path produces geometry, every MO is drawn as a point
         glyph cloud. The renderer never builds convex hulls.

    Args:
        scene_path: Path to the SOFA scene Python file (must define createScene).
        steps: Number of animate steps to run before rendering.
        dt: Time step.
        output_path: Optional PNG output path. Defaults to .sofa_mcp_results/snapshot_<timestamp>.png.
        image_size: (width, height) in pixels.
        background: PyVista-recognized background color name or hex.
        show_edges: Whether to draw mesh edges.

    Returns:
        On success: {success, output_file, rendered_objects, steps, message}
        On failure: {success: false, error}
    """
    if not os.path.exists(scene_path):
        return {"success": False, "error": f"Scene file not found: {scene_path}"}

    try:
        scene_module, module_name = _load_scene_module(scene_path)
    except Exception as e:
        return {"success": False, "error": f"Failed to load scene: {e}"}

    if not hasattr(scene_module, "createScene"):
        sys.modules.pop(module_name, None)
        return {"success": False, "error": "Scene file must contain a 'createScene' function."}

    try:
        root = Sofa.Core.Node("root")
        scene_module.createScene(root)
        Sofa.Simulation.init(root)
        for _ in range(steps):
            Sofa.Simulation.animate(root, dt)
    except Exception as e:
        sys.modules.pop(module_name, None)
        return {"success": False, "error": f"Simulation failed: {e}"}

    try:
        visual_targets = _find_visual_targets(root)
        covered_nodes = {node for _, _, _, _, node in visual_targets}
        topology_targets = _find_topology_fallback_targets(root, covered_nodes)

        plotter = pv.Plotter(off_screen=True, window_size=list(image_size))
        plotter.background_color = background

        rendered = 0

        for idx, (path, pts, faces, color, _node) in enumerate(visual_targets):
            try:
                mesh = _polydata_from(pts, faces)
                rgb = color if color else _DEFAULT_PALETTE[idx % len(_DEFAULT_PALETTE)]
                plotter.add_mesh(mesh, color=rgb, opacity=1.0, show_edges=show_edges)
                rendered += 1
            except Exception:
                continue

        for idx, (path, pts, faces, _color) in enumerate(topology_targets):
            try:
                mesh = _polydata_from(pts, faces)
                rgb = _DEFAULT_PALETTE[(len(visual_targets) + idx) % len(_DEFAULT_PALETTE)]
                plotter.add_mesh(mesh, color=rgb, opacity=1.0, show_edges=show_edges)
                rendered += 1
            except Exception:
                continue

        if rendered == 0:
            for idx, (path, mo, _color_unused) in enumerate(_find_mechanical_objects(root)):
                pts = _read_position_array(mo)
                if pts is None:
                    continue
                cloud = pv.PolyData(pts)
                rgb = _DEFAULT_PALETTE[idx % len(_DEFAULT_PALETTE)]
                plotter.add_mesh(cloud, color=rgb, point_size=8, render_points_as_spheres=True)
                rendered += 1

        if rendered == 0:
            plotter.close()
            return {"success": False, "error": "No renderable geometry found in scene."}

        plotter.show_axes()
        plotter.camera_position = "iso"
        plotter.reset_camera()

        if output_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            results_dir = os.path.join(project_root, ".sofa_mcp_results")
            os.makedirs(results_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(results_dir, f"snapshot_{timestamp}.png")
        else:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

        plotter.screenshot(output_path)
        plotter.close()
    except Exception as e:
        return {"success": False, "error": f"Render failed: {e}"}
    finally:
        sys.modules.pop(module_name, None)

    return {
        "success": True,
        "output_file": output_path,
        "rendered_objects": rendered,
        "steps": steps,
        "message": f"Rendered final frame to {output_path} after {steps} steps.",
    }
