"""Subprocess-side runner for sofa_mcp.observer.probes.

Argv: <mode> <scene_path> <spec_json_path> <output_json_path>

Modes:
  enable_logs  — Toggle printLog=True on objects matching the spec's
                 `log_targets` list, animate for `steps` steps, capture
                 stdout. Spec keys: log_targets, steps, dt.
  perturb      — Apply field overrides from spec's `parameter_changes`
                 dict, then init + animate. Spec keys: parameter_changes,
                 steps, dt. (Implemented in Task 2.)

The parent reads the output JSON after the subprocess exits.
"""

import importlib.util
import json
import math
import os
import sys
import traceback


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# =============================================================================
# Tree walking helpers (copied from _diagnose_runner.py — same pattern there).
# =============================================================================


def _iter_nodes(node, path="/root"):
    yield node, path
    for child in getattr(node, "children", []):
        try:
            child_name = child.getName() if hasattr(child, "getName") else getattr(child, "name", "child")
        except Exception:
            child_name = "child"
        child_path = path.rstrip("/") + "/" + str(child_name)
        yield from _iter_nodes(child, child_path)


def _safe_class_name(obj):
    try:
        if hasattr(obj, "getClassName"):
            return obj.getClassName()
    except Exception:
        pass
    return obj.__class__.__name__


def _safe_obj_name(obj):
    try:
        if hasattr(obj, "getName"):
            return obj.getName()
    except Exception:
        pass
    return getattr(obj, "name", "")


def _data_value(obj, field):
    try:
        d = obj.findData(field)
        if d is None:
            return None
        return d.value
    except Exception:
        return None


# =============================================================================
# Scene load
# =============================================================================


def _load_scene(scene_path):
    """Import the scene module and return its createScene function."""
    spec = importlib.util.spec_from_file_location("user_scene", scene_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "createScene"):
        raise RuntimeError(
            f"{scene_path}: module does not define createScene(rootNode)"
        )
    return module.createScene


# =============================================================================
# Mode: enable_logs
# =============================================================================


def _activate_log_targets(root, log_targets):
    """For each target string, walk the tree and toggle printLog=True on
    every object whose class name matches OR whose node path matches
    (substring containment, case-sensitive). A target string is treated
    as a node-path-or-fragment if it contains '/', else as a class name.

    Returns (activated: list[str], not_found: list[str]).
    """
    activated = []
    not_found_set = set(log_targets)

    for node, node_path in _iter_nodes(root):
        for obj in getattr(node, "objects", []):
            cls = _safe_class_name(obj)
            obj_name = _safe_obj_name(obj)
            obj_path = f"{node_path}/{obj_name}" if obj_name else node_path
            for target in list(log_targets):
                is_path_target = "/" in target
                if is_path_target:
                    matched = target in obj_path or target in node_path
                else:
                    matched = (cls == target)
                if matched:
                    try:
                        d = obj.findData("printLog")
                        if d is not None:
                            d.value = True
                            activated.append(obj_path)
                            not_found_set.discard(target)
                    except Exception:
                        pass

    return activated, sorted(not_found_set)


def _run_enable_logs(scene_path, spec):
    import Sofa
    import Sofa.Core
    import Sofa.Simulation

    create_scene = _load_scene(scene_path)
    root = Sofa.Core.Node("root")
    create_scene(root)

    log_targets = list(spec.get("log_targets") or [])
    steps = int(spec.get("steps", 5))
    dt = float(spec.get("dt", 0.01))

    activated, not_found = _activate_log_targets(root, log_targets)

    Sofa.Simulation.init(root)
    for _ in range(steps):
        Sofa.Simulation.animate(root, dt)

    return {
        "success": True,
        "mode": "enable_logs",
        "log_targets_activated": sorted(set(activated)),
        "log_targets_not_found": not_found,
    }


# =============================================================================
# Dispatcher
# =============================================================================


def main():
    if len(sys.argv) != 5:
        sys.stderr.write(
            "usage: _probe_runner.py <mode> <scene_path> <spec_json_path> <output_json_path>\n"
        )
        sys.exit(2)
    mode, scene_path, spec_path, output_path = sys.argv[1:]

    payload = {"success": False, "mode": mode, "error": None}

    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as exc:
        payload["error"] = f"could not read spec: {exc}"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        sys.exit(1)

    try:
        if mode == "enable_logs":
            payload = _run_enable_logs(scene_path, spec)
        elif mode == "perturb":
            # Implemented in Task 2.
            raise NotImplementedError("perturb mode not yet implemented")
        else:
            payload["error"] = f"unknown mode: {mode}"
    except Exception as exc:
        payload["success"] = False
        payload["error"] = str(exc)
        payload["traceback"] = traceback.format_exc()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


if __name__ == "__main__":
    main()
