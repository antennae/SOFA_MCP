"""Subprocess-side runner for diagnose_scene.

Argv: scene_path, steps, dt, output_json_path

Loads a user scene file via importlib, runs SOFA init + animate for `steps`
iterations, collects per-step metrics on every unmapped MechanicalObject, and
writes the payload to `output_json_path` as JSON. The parent reads the file
after the subprocess exits.

Why a fixed file (no sentinel template like _summary_runtime_template.py):
diagnose_scene always operates on a scene file on disk, so importlib loads it
directly. Keeps the runner debuggable from the shell:

    ~/venv/bin/python sofa_mcp/observer/_diagnose_runner.py \
        archiv/cantilever_beam.py 50 0.01 /tmp/out.json
"""

import importlib.util
import json
import math
import os
import sys
import traceback


# Make `sofa_mcp.architect.plugin_cache` importable regardless of CWD.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# =============================================================================
# Tree walking + introspection (mirrors _summary_runtime_template.py)
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


def _data_value(obj, field):
    try:
        d = obj.findData(field)
        if d is None:
            return None
        return d.value
    except Exception:
        return None


def _node_has_class(node, class_name):
    for obj in getattr(node, "objects", []):
        if _safe_class_name(obj) == class_name:
            return True
    return False


# =============================================================================
# Mapped-MO predicate (copied verbatim in spirit from
# check_rule_3_time_integration in _summary_runtime_template.py)
# =============================================================================


def _load_plugin_map():
    try:
        from sofa_mcp.architect.plugin_cache import load_plugin_map  # type: ignore
        return load_plugin_map()
    except Exception:
        return {}


_PLUGIN_FOR_CLASS = _load_plugin_map()


def _is_mapping_class(cls):
    plugin = _PLUGIN_FOR_CLASS.get(cls)
    return bool(plugin and plugin.startswith("Sofa.Component.Mapping."))


def _node_is_mapped(node):
    for obj in getattr(node, "objects", []):
        if _is_mapping_class(_safe_class_name(obj)):
            return True
    return False


def _plugin_cache_empty():
    """Heuristic: a healthy plugin cache contains hundreds of entries (the
    project plugin map has >500). Below the threshold means the cache file
    was missing or never built — every plugin-prefix predicate then silently
    no-ops, so callers should know.
    """
    return len(_PLUGIN_FOR_CLASS) < 100


_PRINTLOG_PLUGIN_PREFIXES = (
    "Sofa.Component.Constraint.Lagrangian.Solver",
    "Sofa.Component.Constraint.Lagrangian.Correction",
    "Sofa.Component.AnimationLoop",
    "Sofa.Component.ODESolver.",
)

_PRINTLOG_NAME_SUFFIXES = (
    "AnimationLoop",
    "Solver",
    "ConstraintCorrection",
)


def _is_printlog_target(cls):
    if cls in _PLUGIN_FOR_CLASS:
        # Class is attributed — trust plugin attribution exclusively. Avoids
        # catching e.g. SparseLDLSolver via endswith("Solver").
        return any(_PLUGIN_FOR_CLASS[cls].startswith(p) for p in _PRINTLOG_PLUGIN_PREFIXES)
    # Fallback for core-builtin classes that aren't in the plugin cache (e.g.,
    # DefaultAnimationLoop). Class-name suffix.
    return any(cls.endswith(s) for s in _PRINTLOG_NAME_SUFFIXES)


def _is_constraint_solver_class(cls):
    plugin = _PLUGIN_FOR_CLASS.get(cls, "")
    return plugin.startswith("Sofa.Component.Constraint.Lagrangian.Solver")


def _is_ode_solver_class(cls):
    plugin = _PLUGIN_FOR_CLASS.get(cls, "")
    return plugin.startswith("Sofa.Component.ODESolver.")


def _activate_printlog(root):
    """Toggle printLog=True on every constraint/ODE solver, animation loop,
    and constraint correction in the tree. Returns list of activated paths.

    Each toggle is independently wrapped in try/except — components without
    a `printLog` Data field (rare but possible) must not abort the walk.
    """
    activated = []
    for node, node_path in _iter_nodes(root):
        for obj in getattr(node, "objects", []):
            cls = _safe_class_name(obj)
            if not _is_printlog_target(cls):
                continue
            try:
                d = obj.findData("printLog")
                if d is not None:
                    d.value = True
                    activated.append(f"{node_path}::{cls}")
            except Exception:
                # Field missing or read-only on this class — don't abort the walk.
                continue
    return activated


def _check_multimapping_node_has_solver(root):
    """§6.C.1 — a node carrying a *MultiMapping in its `objects` must NOT
    also carry an ODE solver in the same node. SOFA's MechanicalIntegration
    visitor detaches output DoFs from the parent integration when a
    MultiMapping is present, so a co-located solver runs against state it
    cannot integrate.

    Predicate is strictly node-local on each side (mapping AND solver in
    the same `node.objects` list). Plugin attribution gates "is this a SOFA
    mapping at all"; the `MultiMapping` suffix is the secondary filter
    within the mapping plugin.
    """
    anomalies = []
    for node, node_path in _iter_nodes(root):
        class_names = [_safe_class_name(obj) for obj in getattr(node, "objects", [])]
        has_multimapping = any(
            _is_mapping_class(cls) and cls.endswith("MultiMapping")
            for cls in class_names
        )
        if not has_multimapping:
            continue
        has_ode_solver = any(_is_ode_solver_class(cls) for cls in class_names)
        if not has_ode_solver:
            continue
        anomalies.append({
            "rule": "multimapping_node_has_solver",
            "severity": "error",
            "subject": node_path,
            "message": (
                "Node carries a *MultiMapping and an ODE solver in the same "
                "node. The MultiMapping detaches output DoFs from the parent "
                "integration; the solver here runs against state it cannot "
                "integrate."
            ),
        })
    return anomalies


# =============================================================================
# Numeric helpers (no numpy: keeps payload light and avoids the import in the
# critical path; SOFA's MechanicalObject already returns numpy arrays which we
# convert via .tolist()).
# =============================================================================


def _row_max_norm(rows):
    best = 0.0
    for row in rows:
        try:
            s = 0.0
            for v in row:
                s += float(v) * float(v)
            n = math.sqrt(s)
            if n > best:
                best = n
        except Exception:
            return float("nan")
    return best


def _has_nan_or_inf(rows):
    for row in rows:
        try:
            for v in row:
                vf = float(v)
                if math.isnan(vf) or math.isinf(vf):
                    return True
        except Exception:
            return True
    return False


def _displacement_max(pos_now, pos_initial):
    n = min(len(pos_now), len(pos_initial))
    if n == 0:
        return 0.0
    best = 0.0
    for i in range(n):
        try:
            r = pos_now[i]
            r0 = pos_initial[i]
            s = 0.0
            for k in range(min(len(r), len(r0))):
                d = float(r[k]) - float(r0[k])
                s += d * d
            d = math.sqrt(s)
            if d > best:
                best = d
        except Exception:
            return float("nan")
    return best


# =============================================================================
# MechanicalObject readers
# =============================================================================


def _read_field_as_rows(mo, field):
    try:
        d = mo.findData(field)
        if d is None:
            return []
        v = d.value
        if hasattr(v, "tolist"):
            v = v.tolist()
        return list(v)
    except Exception:
        return []


def _collect_unmapped_mos(root):
    """One entry per node containing a MechanicalObject and no mapping in the same node."""
    found = []
    for node, path in _iter_nodes(root):
        if not _node_has_class(node, "MechanicalObject"):
            continue
        if _node_is_mapped(node):
            continue
        for obj in getattr(node, "objects", []):
            if _safe_class_name(obj) == "MechanicalObject":
                found.append((path, obj))
                break
    return found


def _collect_capture_targets(root):
    """Find constraint solvers and QP solvers anywhere in the tree.

    Returns (constraint_solvers, qp_solvers) where each is a list of
    (path, obj) tuples. The path uses the parent-node path (where the
    solver was added), matching the keying convention used elsewhere.
    """
    constraint_solvers = []
    qp_solvers = []
    for node, path in _iter_nodes(root):
        for obj in getattr(node, "objects", []):
            cls = _safe_class_name(obj)
            if _is_constraint_solver_class(cls):
                # Distinct path so multiple solvers on the same node don't collide.
                constraint_solvers.append((f"{path}::{cls}", obj))
            if cls == "QPInverseProblemSolver":
                qp_solvers.append((f"{path}::{cls}", obj))
    return constraint_solvers, qp_solvers


def _initial_extent(rows):
    """Max axis extent of a position list. Returns 0.0 for empty/degenerate input."""
    if not rows:
        return 0.0
    try:
        first = list(rows[0])
    except Exception:
        return 0.0
    dims = len(first)
    if dims == 0:
        return 0.0
    mins = [float("inf")] * dims
    maxs = [float("-inf")] * dims
    for row in rows:
        try:
            for k in range(dims):
                v = float(row[k])
                if v < mins[k]:
                    mins[k] = v
                if v > maxs[k]:
                    maxs[k] = v
        except Exception:
            return 0.0
    extents = [maxs[k] - mins[k] for k in range(dims)]
    return max(extents) if extents else 0.0


# =============================================================================
# Scene summary
# =============================================================================


def _read_actuators_only(root):
    """Look up `actuatorsOnly` on a QPInverseProblemSolver if present.

    Field name verified against QPInverseProblemSolver.cpp:141 — Python name is
    "actuatorsOnly" (no d_ prefix). If no QP solver exists, return False.
    """
    for node, _ in _iter_nodes(root):
        for obj in getattr(node, "objects", []):
            if _safe_class_name(obj) != "QPInverseProblemSolver":
                continue
            v = _data_value(obj, "actuatorsOnly")
            if v is None:
                return False
            try:
                return bool(v)
            except Exception:
                return False
    return False


def _scene_summary(root):
    node_count = 0
    class_counts = {}
    for node, _ in _iter_nodes(root):
        node_count += 1
        for obj in getattr(node, "objects", []):
            cls = _safe_class_name(obj)
            class_counts[cls] = class_counts.get(cls, 0) + 1
    return {
        "node_count": node_count,
        "class_counts": class_counts,
        "actuators_only": _read_actuators_only(root),
    }


# =============================================================================
# Driver
# =============================================================================


def _load_scene_module(scene_path):
    spec = importlib.util.spec_from_file_location("diagnose_runner_scene", scene_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load scene from {scene_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["diagnose_runner_scene"] = mod
    spec.loader.exec_module(mod)
    if not hasattr(mod, "createScene"):
        raise AttributeError("Scene file must define createScene(rootNode)")
    return mod


def _empty_payload():
    """Skeleton payload — every key the parent reads must be present so that
    failure-path responses share the same shape as success ones."""
    return {
        "success": False,
        "metrics": {
            "nan_first_step": None,
            "max_displacement_per_mo": {},
            "max_force_per_mo": {},
        },
        "init_stdout_findings": [],
        "scene_summary": {
            "node_count": 0,
            "class_counts": {},
            "actuators_only": False,
        },
        "extents_per_mo": {},
        "solver_iterations": {},
        "solver_max_iterations": {},
        "objective_series": {},
        "structural_anomalies": [],
        "printLog_activated": [],
        "plugin_cache_empty": False,
    }


def _run(scene_path, steps, dt, payload):
    """Populate `payload` in-place. Re-raises on failure so main() can attach
    the error/traceback to whatever partial state was already filled in.
    """
    import Sofa.Core
    import Sofa.Simulation

    mod = _load_scene_module(scene_path)
    root = Sofa.Core.Node("root")
    mod.createScene(root)

    # Pre-init walk: structural smell tests and printLog activation. Both are
    # safe to do post-construction but pre-init.
    payload["structural_anomalies"] = _check_multimapping_node_has_solver(root)
    payload["printLog_activated"] = _activate_printlog(root)
    payload["plugin_cache_empty"] = _plugin_cache_empty()

    Sofa.Simulation.init(root)

    payload["scene_summary"] = _scene_summary(root)

    mos = _collect_unmapped_mos(root)
    initial_positions = {path: _read_field_as_rows(mo, "position") for path, mo in mos}
    extents_per_mo = {}
    for path, _ in mos:
        ext = _initial_extent(initial_positions.get(path, []))
        if ext > 0:
            extents_per_mo[path] = ext
    payload["extents_per_mo"] = extents_per_mo

    constraint_solvers, qp_solvers = _collect_capture_targets(root)
    solver_max_iterations = {}
    for path, obj in constraint_solvers:
        v = _data_value(obj, "maxIterations")
        if v is not None:
            try:
                solver_max_iterations[path] = int(v)
            except Exception:
                pass
    payload["solver_max_iterations"] = solver_max_iterations

    solver_iterations = {path: [] for path, _ in constraint_solvers}
    objective_series = {path: [] for path, _ in qp_solvers}
    payload["solver_iterations"] = solver_iterations
    payload["objective_series"] = objective_series

    max_displacement = {path: 0.0 for path, _ in mos}
    max_force = {path: 0.0 for path, _ in mos}
    metrics = payload["metrics"]
    metrics["max_displacement_per_mo"] = max_displacement
    metrics["max_force_per_mo"] = max_force

    for step_idx in range(int(steps)):
        Sofa.Simulation.animate(root, float(dt))
        for path, mo in mos:
            pos = _read_field_as_rows(mo, "position")
            force = _read_field_as_rows(mo, "force")
            if _has_nan_or_inf(pos) or _has_nan_or_inf(force):
                if metrics["nan_first_step"] is None:
                    metrics["nan_first_step"] = step_idx
                continue
            disp = _displacement_max(pos, initial_positions.get(path, []))
            if disp > max_displacement[path]:
                max_displacement[path] = disp
            fmag = _row_max_norm(force)
            if fmag > max_force[path]:
                max_force[path] = fmag

        for path, obj in constraint_solvers:
            v = _data_value(obj, "currentIterations")
            if v is None:
                continue
            try:
                solver_iterations[path].append(int(v))
            except Exception:
                pass

        for path, obj in qp_solvers:
            v = _data_value(obj, "objective")
            if v is None:
                continue
            try:
                objective_series[path].append(float(v))
            except Exception:
                pass

    payload["success"] = True


def _write_payload(output_json_path, payload):
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def main():
    if len(sys.argv) != 5:
        print(
            "Usage: _diagnose_runner.py <scene_path> <steps> <dt> <output_json_path>",
            file=sys.stderr,
        )
        sys.exit(2)

    scene_path = sys.argv[1]
    try:
        steps = int(sys.argv[2])
    except ValueError:
        print(f"steps must be int; got {sys.argv[2]!r}", file=sys.stderr)
        sys.exit(2)
    try:
        dt = float(sys.argv[3])
    except ValueError:
        print(f"dt must be float; got {sys.argv[3]!r}", file=sys.stderr)
        sys.exit(2)
    output_json_path = sys.argv[4]

    payload = _empty_payload()
    try:
        _run(scene_path, steps, dt, payload)
    except Exception as exc:
        payload["success"] = False
        payload["error"] = str(exc)
        payload["traceback"] = traceback.format_exc()
        try:
            _write_payload(output_json_path, payload)
        except Exception:
            pass
        traceback.print_exc()
        sys.exit(1)

    _write_payload(output_json_path, payload)


if __name__ == "__main__":
    main()
