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


def _build_surface(positions: np.ndarray):
    """Try delaunay_3d → extract surface; fall back to a glyph cloud if it fails."""
    cloud = pv.PolyData(positions)
    try:
        vol = cloud.delaunay_3d(alpha=0)
        surf = vol.extract_surface()
        if surf.n_points > 0 and surf.n_cells > 0:
            return surf, "surface"
    except Exception:
        pass
    return cloud, "points"


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

    The renderer auto-discovers every MechanicalObject in the scene tree, builds a
    surface mesh from each (delaunay_3d → extract_surface; falls back to a point
    cloud if delaunay fails), and uses any sibling OglModel color when present.

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
        mos = _find_mechanical_objects(root)
        if not mos:
            return {"success": False, "error": "No MechanicalObject found in scene."}

        plotter = pv.Plotter(off_screen=True, window_size=list(image_size))
        plotter.background_color = background

        rendered = 0
        for idx, (path, mo, color) in enumerate(mos):
            pos_data = mo.findData("position")
            if pos_data is None:
                continue
            try:
                positions = np.array(pos_data.value, dtype=float)
            except Exception:
                continue
            if positions.ndim != 2 or positions.shape[0] == 0 or positions.shape[1] < 3:
                continue
            pts = positions[:, :3]

            surf, _kind = _build_surface(pts)
            rgb = color if (color and len(color) >= 3) else _DEFAULT_PALETTE[idx % len(_DEFAULT_PALETTE)]

            if surf.n_cells > 0:
                plotter.add_mesh(surf, color=rgb, opacity=1.0, show_edges=show_edges)
            else:
                plotter.add_mesh(surf, color=rgb, point_size=8, render_points_as_spheres=True)
            rendered += 1

        if rendered == 0:
            plotter.close()
            return {"success": False, "error": "No renderable MechanicalObject positions found."}

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
