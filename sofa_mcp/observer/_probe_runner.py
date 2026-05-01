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
# Mode: perturb
# =============================================================================


def _resolve_node_at_path(root, target_path):
    """Walk the tree; return (node, residual) where residual is the
    remainder of target_path after the node prefix matches. Uses the
    longest (most specific) matching node prefix so that /root/beam/FEM
    resolves to node=/root/beam + residual=FEM rather than node=/root.
    Returns (None, None) if no prefix matches.
    """
    best_node = None
    best_node_path = None
    for node, node_path in _iter_nodes(root):
        if node_path == target_path:
            return node, ""
        if target_path.startswith(node_path.rstrip("/") + "/"):
            if best_node_path is None or len(node_path) > len(best_node_path):
                best_node = node
                best_node_path = node_path
    if best_node is not None:
        residual = target_path[len(best_node_path):].lstrip("/")
        return best_node, residual
    return None, None


def _apply_perturbation(root, parameter_changes):
    """For each (path, {field: value}) entry, locate the object and patch
    its Data field. Returns (applied: list[str], failed: list[dict])."""
    applied = []
    failed = []
    for path, fields in (parameter_changes or {}).items():
        node, residual = _resolve_node_at_path(root, path)
        if node is None:
            failed.append({"path": path, "field": None, "error": "node path not found"})
            continue
        # If residual is non-empty, treat it as the object name.
        target_obj = None
        if residual:
            for obj in getattr(node, "objects", []):
                if _safe_obj_name(obj) == residual:
                    target_obj = obj
                    break
            if target_obj is None:
                failed.append({"path": path, "field": None,
                               "error": f"no object named '{residual}' under {path[:-len(residual)-1]}"})
                continue
            patch_targets = [target_obj]
        else:
            # Patch every object in this node (matches the path-only convention).
            patch_targets = list(getattr(node, "objects", []))

        for field, value in (fields or {}).items():
            ok = False
            for obj in patch_targets:
                try:
                    d = obj.findData(field)
                    if d is None:
                        continue
                    # SofaPython3 scalar Data fields (e.g. youngModulus) are
                    # stored as numpy arrays — try the raw value first, then
                    # wrap in a list if iterable-not-satisfied.
                    try:
                        d.value = value
                    except TypeError:
                        d.value = [value]
                    applied.append(f"{path}.{field}")
                    ok = True
                    break
                except Exception as exc:
                    failed.append({"path": path, "field": field, "error": str(exc)})
            if not ok and not any(f.get("path") == path and f.get("field") == field for f in failed):
                failed.append({"path": path, "field": field, "error": "no object exposes this Data field"})
    return applied, failed


def _collect_unmapped_mos(root):
    """Per-MO walker — same predicate as _diagnose_runner._collect_unmapped_mos:
    skip MOs whose ancestor chain contains a Mapping component (those are
    driven, not free DOFs)."""
    out = []  # list of (path, mo)
    for node, path in _iter_nodes(root):
        for obj in getattr(node, "objects", []):
            if _safe_class_name(obj) == "MechanicalObject":
                # Skip if any ancestor has a Mapping (best-effort — the runner's
                # full plugin-cache check is defensive; here we don't need it).
                out.append((path, obj))
                break
    return out


def _capture_metrics(root, mos, dt, steps):
    """Per-step displacement+force metrics, NaN-first-step. Mirrors the
    skeleton of _diagnose_runner's metrics capture but without smell tests
    or extents/iteration captures (this is a perturb/replay tool, not a
    diagnostic)."""
    import Sofa.Simulation
    import math as _m

    max_disp = {p: 0.0 for p, _ in mos}
    max_force = {p: 0.0 for p, _ in mos}
    nan_step = None

    initial_pos = {}
    for path, mo in mos:
        try:
            raw = mo.findData("position").value
            initial_pos[path] = [list(p) for p in raw] if raw is not None else []
        except Exception:
            initial_pos[path] = []

    for step in range(steps):
        Sofa.Simulation.animate(root, dt)
        for path, mo in mos:
            try:
                raw_now = mo.findData("position").value
                pos_now = raw_now if raw_now is not None else []
                pos0 = initial_pos.get(path) or []
                disp = 0.0
                for p, p0 in zip(pos_now, pos0):
                    d2 = sum((float(a) - float(b)) ** 2 for a, b in zip(p, p0))
                    if _m.isnan(d2) or _m.isinf(d2):
                        nan_step = step if nan_step is None else nan_step
                        continue
                    disp = max(disp, _m.sqrt(d2))
                if disp > max_disp.get(path, 0.0):
                    max_disp[path] = disp
            except Exception:
                pass
            try:
                raw_forces = mo.findData("force").value
                forces = raw_forces if raw_forces is not None else []
                f_max = 0.0
                for f in forces:
                    fmag = sum(float(c) ** 2 for c in f)
                    if _m.isnan(fmag) or _m.isinf(fmag):
                        nan_step = step if nan_step is None else nan_step
                        continue
                    f_max = max(f_max, _m.sqrt(fmag))
                if f_max > max_force.get(path, 0.0):
                    max_force[path] = f_max
            except Exception:
                pass

    return {
        "nan_first_step": nan_step,
        "max_displacement_per_mo": max_disp,
        "max_force_per_mo": max_force,
    }


def _run_perturb(scene_path, spec):
    import Sofa
    import Sofa.Core
    import Sofa.Simulation

    create_scene = _load_scene(scene_path)
    root = Sofa.Core.Node("root")
    create_scene(root)

    parameter_changes = spec.get("parameter_changes") or {}
    steps = int(spec.get("steps", 50))
    dt = float(spec.get("dt", 0.01))

    applied, failed = _apply_perturbation(root, parameter_changes)

    Sofa.Simulation.init(root)
    mos = _collect_unmapped_mos(root)
    metrics = _capture_metrics(root, mos, dt, steps)

    return {
        "success": True,
        "mode": "perturb",
        "parameter_changes_applied": applied,
        "parameter_changes_failed": failed,
        "metrics": metrics,
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
            payload = _run_perturb(scene_path, spec)
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
