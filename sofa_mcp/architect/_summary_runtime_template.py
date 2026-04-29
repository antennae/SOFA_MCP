"""Template for the summary subprocess wrapper.

Read as TEXT by `_build_summary_wrapper`, never imported. Two unique sentinel
tokens are substituted at build time (see scene_writer.py for the exact
substitution code).
"""

import Sofa
import Sofa.Core
import Sofa.Simulation
import json
import sys
import math
import os

# Plugin attribution map, embedded at build time.
PLUGIN_FOR_CLASS = {}  # __SOFA_MCP_PLUGIN_MAP_SENTINEL__

# Classes that are part of the core build (not in any plugin) — never flagged
# as missing-plugin in Rule 1.
CORE_BUILTIN_CLASSES = {
    "Node",
    "RequiredPlugin",
    "DefaultAnimationLoop",
}

# Inverse-problem plugin name; classes from this plugin require QPInverseProblemSolver (Rule 5B).
INVERSE_PLUGIN = "SoftRobots.Inverse"

# __SOFA_MCP_USER_CREATE_SCENE_SENTINEL__


# =============================================================================
# Tree walking + introspection helpers
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


def _safe_obj_name(obj):
    try:
        if hasattr(obj, "getName"):
            return obj.getName()
    except Exception:
        pass
    return None


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


def _link_value_string(obj, name):
    """Return the link target path for a Link field, or '' if absent/empty."""
    try:
        link = obj.findLink(name) if hasattr(obj, "findLink") else None
        if link is None:
            return ""
        return str(link.getValueString() or "")
    except Exception:
        return ""


def _node_has_class(node, class_name):
    for obj in getattr(node, "objects", []):
        if _safe_class_name(obj) == class_name:
            return True
    return False


def _tree_has_class(node, class_name):
    return any(_node_has_class(n, class_name) for n, _ in _iter_nodes(node))


def _tree_classes(node):
    seen = set()
    for n, _ in _iter_nodes(node):
        for obj in getattr(n, "objects", []):
            seen.add(_safe_class_name(obj))
    return seen


def _build_parent_map(root):
    """Map child node id → parent node (None for root)."""
    parents = {id(root): None}
    stack = [root]
    while stack:
        n = stack.pop()
        for c in getattr(n, "children", []):
            parents[id(c)] = n
            stack.append(c)
    return parents


def _ancestors(node, parent_map):
    cur = node
    while cur is not None:
        yield cur
        cur = parent_map.get(id(cur))


def _plugin_of(class_name):
    return PLUGIN_FOR_CLASS.get(class_name)


# =============================================================================
# Per-rule checks (slugs match SKILL.md 1-9 numbering)
# =============================================================================


def check_rule_1_plugins(root):
    """For every used component class, the corresponding plugin must be RequiredPlugin'd."""
    out = []
    declared = set()
    for n, _path in _iter_nodes(root):
        for obj in getattr(n, "objects", []):
            if _safe_class_name(obj) == "RequiredPlugin":
                name = _data_value(obj, "name")
                if name:
                    declared.add(str(name))
                pluginName = _data_value(obj, "pluginName")
                if pluginName:
                    if isinstance(pluginName, (list, tuple)):
                        for p in pluginName:
                            declared.add(str(p))
                    else:
                        declared.add(str(pluginName))

    seen = set()
    for n, path in _iter_nodes(root):
        for obj in getattr(n, "objects", []):
            cls = _safe_class_name(obj)
            if cls in seen or cls in CORE_BUILTIN_CLASSES or cls == "RequiredPlugin":
                continue
            seen.add(cls)
            plugin = _plugin_of(cls)
            if plugin is None:
                # Class not in plugin cache and not core-builtin: unknown.
                out.append({
                    "rule": "rule_1_plugins",
                    "severity": "warning",
                    "subject": path,
                    "message": f"Class '{cls}' is not in the plugin cache; cannot verify its plugin is loaded.",
                })
                continue
            if plugin not in declared:
                out.append({
                    "rule": "rule_1_plugins",
                    "severity": "error",
                    "subject": path,
                    "message": f"Class '{cls}' requires plugin '{plugin}' but no RequiredPlugin loads it.",
                })
    if not out:
        out.append({"rule": "rule_1_plugins", "severity": "ok", "subject": "/root",
                    "message": "All used classes have their plugins declared."})
    return out


def check_rule_2_animation_loop(root):
    """FreeMotion required if any *LagrangianConstraint/*Actuator/*ConstraintCorrection."""
    out = []
    has_free = _tree_has_class(root, "FreeMotionAnimationLoop")
    has_default = _tree_has_class(root, "DefaultAnimationLoop")

    needs_free = False
    suffixes = ("LagrangianConstraint", "Actuator", "ConstraintCorrection")
    for cls in _tree_classes(root):
        if cls.endswith(suffixes):
            needs_free = True
            break
    # Also: any Inverse-plugin class implies constraint-driven scene → needs FreeMotion.
    for cls in _tree_classes(root):
        if _plugin_of(cls) == INVERSE_PLUGIN:
            needs_free = True
            break

    if not has_free and not has_default:
        out.append({
            "rule": "rule_2_animation_loop", "severity": "warning", "subject": "/root",
            "message": "No AnimationLoop declared. SOFA will silently auto-instantiate DefaultAnimationLoop, hiding constraint-related bugs.",
        })
    elif has_free and has_default:
        out.append({
            "rule": "rule_2_animation_loop", "severity": "error", "subject": "/root",
            "message": "Both FreeMotionAnimationLoop and DefaultAnimationLoop declared. Pick one.",
        })
    elif needs_free and not has_free:
        out.append({
            "rule": "rule_2_animation_loop", "severity": "error", "subject": "/root",
            "message": "Scene has constraint/actuator/correction components but uses DefaultAnimationLoop. Switch to FreeMotionAnimationLoop.",
        })
    else:
        out.append({"rule": "rule_2_animation_loop", "severity": "ok", "subject": "/root",
                    "message": "AnimationLoop choice is consistent with scene contents."})
    return out


def check_rule_3_time_integration(root):
    """Every unmapped MechanicalObject needs an ODE solver in its ancestor chain."""
    out = []
    parent_map = _build_parent_map(root)

    def is_ode_solver_class(cls):
        plugin = _plugin_of(cls)
        return bool(plugin and plugin.startswith("Sofa.Component.ODESolver."))

    def is_mapping_class(cls):
        plugin = _plugin_of(cls)
        return bool(plugin and plugin.startswith("Sofa.Component.Mapping."))

    for n, path in _iter_nodes(root):
        # Find unmapped MechanicalObjects: a node containing a MO but no mapping in the same node.
        if not _node_has_class(n, "MechanicalObject"):
            continue
        node_classes = {_safe_class_name(o) for o in getattr(n, "objects", [])}
        if any(is_mapping_class(c) for c in node_classes):
            continue  # mapped MO

        has_solver = False
        for anc in _ancestors(n, parent_map):
            for obj in getattr(anc, "objects", []):
                if is_ode_solver_class(_safe_class_name(obj)):
                    has_solver = True
                    break
            if has_solver:
                break

        if not has_solver:
            out.append({
                "rule": "rule_3_time_integration", "severity": "error", "subject": path,
                "message": "Unmapped MechanicalObject has no ODE solver in its ancestor chain.",
            })

    if not out:
        out.append({"rule": "rule_3_time_integration", "severity": "ok", "subject": "/root",
                    "message": "All unmapped mechanical objects have an integrator."})
    return out


def check_rule_4_linear_solver(root):
    """Implicit ODE solver needs a linear solver in the same node or a descendant (SearchDown)."""
    out = []

    def is_implicit_ode(cls):
        # Backward = implicit family in this build.
        return _plugin_of(cls) == "Sofa.Component.ODESolver.Backward"

    def is_linear_solver(cls):
        plugin = _plugin_of(cls)
        return bool(plugin and plugin.startswith("Sofa.Component.LinearSolver."))

    for n, path in _iter_nodes(root):
        ode_classes_here = [_safe_class_name(o) for o in getattr(n, "objects", [])
                            if is_implicit_ode(_safe_class_name(o))]
        if not ode_classes_here:
            continue

        # Search self + descendants for a linear solver.
        found = False
        for sub, _ in _iter_nodes(n, path):
            for obj in getattr(sub, "objects", []):
                if is_linear_solver(_safe_class_name(obj)):
                    found = True
                    break
            if found:
                break

        if not found:
            out.append({
                "rule": "rule_4_linear_solver", "severity": "error", "subject": path,
                "message": f"Implicit ODE solver(s) {ode_classes_here} have no linear solver in the same node or descendants. Add SparseLDLSolver (or CGLinearSolver for very large systems).",
            })

    if not out:
        out.append({"rule": "rule_4_linear_solver", "severity": "ok", "subject": "/root",
                    "message": "Each implicit ODE solver has a linear solver in scope."})
    return out


def check_rule_5_constraint_handling(root):
    """3 sub-checks: constraint solver under FreeMotion; inverse plugin needs QP; correction in deformable subtree."""
    out = []
    has_free = _tree_has_class(root, "FreeMotionAnimationLoop")

    def is_constraint_solver(cls):
        return _plugin_of(cls) == "Sofa.Component.Constraint.Lagrangian.Solver"

    def is_constraint_correction(cls):
        return _plugin_of(cls) == "Sofa.Component.Constraint.Lagrangian.Correction"

    def is_ode_solver_class(cls):
        plugin = _plugin_of(cls)
        return bool(plugin and plugin.startswith("Sofa.Component.ODESolver."))

    has_qp = _tree_has_class(root, "QPInverseProblemSolver")
    has_forward_solver = any(is_constraint_solver(_safe_class_name(o)) for o in getattr(root, "objects", []))

    # 5A: FreeMotion → root needs a constraint solver (forward NNCG/etc OR inverse QP).
    if has_free and not has_forward_solver and not has_qp:
        out.append({
            "rule": "rule_5_constraint_handling", "severity": "error", "subject": "/root",
            "message": "FreeMotionAnimationLoop declared but no constraint solver at root. Add NNCGConstraintSolver (forward) or QPInverseProblemSolver (inverse).",
        })

    # 5B: Inverse-plugin classes require QPInverseProblemSolver.
    inverse_users = []
    for n, path in _iter_nodes(root):
        for obj in getattr(n, "objects", []):
            cls = _safe_class_name(obj)
            if _plugin_of(cls) == INVERSE_PLUGIN and cls != "QPInverseProblemSolver":
                inverse_users.append((cls, path))
    if inverse_users and not has_qp:
        examples = ", ".join(sorted({c for c, _ in inverse_users})[:3])
        out.append({
            "rule": "rule_5_constraint_handling", "severity": "error", "subject": "/root",
            "message": f"Scene uses SoftRobots.Inverse classes ({examples}) but no QPInverseProblemSolver at root.",
        })

    # 5C: Each subtree containing an ODE solver needs a *ConstraintCorrection somewhere in it (only when FreeMotion present).
    if has_free:
        for n, path in _iter_nodes(root):
            if path == "/root":
                continue
            has_ode_here = any(is_ode_solver_class(_safe_class_name(o)) for o in getattr(n, "objects", []))
            if not has_ode_here:
                continue
            has_correction = False
            for sub, _ in _iter_nodes(n, path):
                for obj in getattr(sub, "objects", []):
                    if is_constraint_correction(_safe_class_name(obj)):
                        has_correction = True
                        break
                if has_correction:
                    break
            if not has_correction:
                out.append({
                    "rule": "rule_5_constraint_handling", "severity": "error", "subject": path,
                    "message": "Deformable subtree (has ODE solver) under FreeMotionAnimationLoop has no *ConstraintCorrection. Add GenericConstraintCorrection.",
                })

    if not out:
        out.append({"rule": "rule_5_constraint_handling", "severity": "ok", "subject": "/root",
                    "message": "Constraint handling is consistent."})
    return out


def check_rule_6_forcefield_mapping(root):
    """Every ForceField must reach a MO. PairInteraction (object1 set) is exempt."""
    out = []
    parent_map = _build_parent_map(root)

    for n, path in _iter_nodes(root):
        for obj in getattr(n, "objects", []):
            cls = _safe_class_name(obj)
            if not cls.endswith("ForceField"):
                continue
            # Pair-interaction Data fields and Link fields named object1/object2 both exempt.
            if (_data_value(obj, "object1") or _data_value(obj, "object2")
                    or _link_value_string(obj, "object1") or _link_value_string(obj, "object2")):
                continue
            # Walk ancestors (including self) for a MechanicalObject.
            found_mo = False
            for anc in _ancestors(n, parent_map):
                if _node_has_class(anc, "MechanicalObject"):
                    found_mo = True
                    break
            if not found_mo:
                out.append({
                    "rule": "rule_6_forcefield_mapping", "severity": "error", "subject": path,
                    "message": f"ForceField '{cls}' has no MechanicalObject in its ancestor chain.",
                })
    if not out:
        out.append({"rule": "rule_6_forcefield_mapping", "severity": "ok", "subject": "/root",
                    "message": "All force fields can reach a mechanical object."})
    return out


# Volumetric topology container classes.
_VOLUMETRIC_TOPO_CLASSES = {
    "TetrahedronSetTopologyContainer",
    "HexahedronSetTopologyContainer",
}
# Shell FEM classes that exempt BarycentricMapping from the volumetric-parent rule.
_SHELL_FEM_CLASSES = {"TriangularFEMForceField", "QuadBendingFEMForceField"}


def _node_is_volumetric(node):
    """Heuristic: does this node carry a topology container that supports tetra/hexa elements?"""
    for obj in getattr(node, "objects", []):
        cls = _safe_class_name(obj)
        if cls in _VOLUMETRIC_TOPO_CLASSES:
            return True
        if cls == "MeshTopology":
            fname = _data_value(obj, "filename")
            if fname and isinstance(fname, str) and fname.lower().endswith((".vtk", ".msh", ".vtu")):
                return True
        if cls in {"RegularGridTopology", "SparseGridTopology"}:
            n_data = _data_value(obj, "n")
            try:
                if n_data is not None and len(n_data) >= 3 and all(int(x) > 1 for x in n_data[:3]):
                    return True
            except Exception:
                pass
    return False


def check_rule_7_topology(root):
    """Volumetric FFs need volumetric topology; BarycentricMapping parent volumetric except shell FEM."""
    out = []
    parent_map = _build_parent_map(root)

    # 7A: Volumetric FF needs a volumetric topology in same node or ancestor chain.
    for n, path in _iter_nodes(root):
        for obj in getattr(n, "objects", []):
            cls = _safe_class_name(obj)
            if cls.startswith("Tetrahedron") and cls.endswith("ForceField"):
                pass
            elif cls.startswith("Hexahedron") and cls.endswith("ForceField"):
                pass
            else:
                continue
            has_volumetric = False
            for anc in _ancestors(n, parent_map):
                if _node_is_volumetric(anc):
                    has_volumetric = True
                    break
            if not has_volumetric:
                out.append({
                    "rule": "rule_7_topology", "severity": "error", "subject": path,
                    "message": f"'{cls}' requires a volumetric topology container (TetrahedronSetTopologyContainer / HexahedronSetTopologyContainer / MeshTopology from .vtk|.msh|.vtu / 3D RegularGridTopology) in scope.",
                })

    # 7B: BarycentricMapping → parent node must be volumetric, unless parent has a shell FEM.
    for n, path in _iter_nodes(root):
        if not _node_has_class(n, "BarycentricMapping"):
            continue
        parent = parent_map.get(id(n))
        if parent is None:
            continue
        if _node_is_volumetric(parent):
            continue
        parent_classes = {_safe_class_name(o) for o in getattr(parent, "objects", [])}
        if parent_classes & _SHELL_FEM_CLASSES:
            continue  # shell-FEM exemption
        out.append({
            "rule": "rule_7_topology", "severity": "error", "subject": path,
            "message": "BarycentricMapping's parent node is neither volumetric nor a shell FEM (TriangularFEMForceField / QuadBendingFEMForceField).",
        })

    if not out:
        out.append({"rule": "rule_7_topology", "severity": "ok", "subject": "/root",
                    "message": "Topology containers and mappings are consistent."})
    return out


def check_rule_8_collision_pipeline(root):
    """If any node has a *CollisionModel, root needs the 5-cluster collision pipeline."""
    out = []
    has_any_collision_model = False
    for n, _ in _iter_nodes(root):
        for obj in getattr(n, "objects", []):
            if _safe_class_name(obj).endswith("CollisionModel"):
                has_any_collision_model = True
                break
        if has_any_collision_model:
            break
    if not has_any_collision_model:
        out.append({"rule": "rule_8_collision_pipeline", "severity": "ok", "subject": "/root",
                    "message": "No collision models in scene; pipeline not required."})
        return out

    # Check root for the 5 clusters. Bullet plugin replaces broad+narrow.
    root_classes = {_safe_class_name(o) for o in getattr(root, "objects", [])}
    bullet_loaded = False
    for obj in getattr(root, "objects", []):
        if _safe_class_name(obj) == "RequiredPlugin":
            name = _data_value(obj, "name") or _data_value(obj, "pluginName")
            if name and "BulletCollisionDetection" in str(name):
                bullet_loaded = True

    pipeline = any(c == "CollisionPipeline" for c in root_classes)
    broad = any(("BroadPhase" in c) or c in {"IncrSAP", "DirectSAP"} for c in root_classes)
    narrow = any("NarrowPhase" in c for c in root_classes)
    intersection = any(("Intersection" in c) or (c == "LocalMinDistance") for c in root_classes)
    contact = any(c in {"CollisionResponse", "RuleBasedContactManager"} for c in root_classes)

    missing = []
    if not pipeline:
        missing.append("CollisionPipeline")
    if not broad and not bullet_loaded:
        missing.append("BroadPhase (e.g., BruteForceBroadPhase)")
    if not narrow and not bullet_loaded:
        missing.append("NarrowPhase (e.g., BVHNarrowPhase)")
    if not intersection:
        missing.append("Intersection (e.g., MinProximityIntersection)")
    if not contact:
        missing.append("ContactManager (e.g., CollisionResponse)")

    if missing:
        out.append({
            "rule": "rule_8_collision_pipeline", "severity": "error", "subject": "/root",
            "message": "Scene has collision models but root is missing: " + ", ".join(missing),
        })
    else:
        out.append({"rule": "rule_8_collision_pipeline", "severity": "ok", "subject": "/root",
                    "message": "Collision pipeline complete."})
    return out


def check_rule_9_units(root):
    """Detect unit system from gravity magnitude; flag suspicious YM thresholds and the -9180 typo."""
    out = []
    g = _data_value(root, "gravity")
    if g is None:
        return [{"rule": "rule_9_units", "severity": "info", "subject": "/root",
                 "message": "Root has no gravity field; cannot infer unit system."}]
    try:
        gx, gy, gz = float(g[0]), float(g[1]), float(g[2])
        gmag = math.sqrt(gx * gx + gy * gy + gz * gz)
    except Exception:
        return [{"rule": "rule_9_units", "severity": "info", "subject": "/root",
                 "message": "Could not parse root.gravity."}]

    # Typo discriminator: |g| close to 9180 but not 9810.
    if 9100 < gmag < 9260:
        out.append({
            "rule": "rule_9_units", "severity": "error", "subject": "/root",
            "message": f"Gravity magnitude is {gmag:.1f}; this looks like a -9180 typo of -9810 (mm/g/s).",
        })
        unit_system = None
    elif 9.0 < gmag < 11.0:
        unit_system = "SI"
    elif 9000 < gmag < 11000:
        unit_system = "mm/g/s"
    else:
        out.append({
            "rule": "rule_9_units", "severity": "warning", "subject": "/root",
            "message": f"Gravity magnitude {gmag:.3f} matches neither SI (~9.81) nor mm/g/s (~9810).",
        })
        unit_system = None

    if unit_system is not None:
        # Collect youngModulus values from any force field exposing the field.
        ym_outliers = []
        for n, path in _iter_nodes(root):
            for obj in getattr(n, "objects", []):
                ym = _data_value(obj, "youngModulus")
                if ym is None:
                    continue
                try:
                    # SOFA returns youngModulus as a length-1 numpy array; future numpy
                    # makes float(array) on >0-D a hard error. Index first, then cast.
                    ym_val = float(ym[0]) if hasattr(ym, "__len__") else float(ym)
                except Exception:
                    continue
                if unit_system == "SI" and ym_val < 100:
                    ym_outliers.append((path, _safe_class_name(obj), ym_val, "SI", "< 100 Pa"))
                elif unit_system == "mm/g/s" and ym_val > 1e9:
                    ym_outliers.append((path, _safe_class_name(obj), ym_val, "mm/g/s", "> 1e9"))
        for path, cls, ym_val, system, threshold in ym_outliers:
            out.append({
                "rule": "rule_9_units", "severity": "warning", "subject": path,
                "message": f"In {system} scene, '{cls}' has youngModulus={ym_val} ({threshold}) — likely a units mismatch.",
            })
        if not out:
            out.append({"rule": "rule_9_units", "severity": "ok", "subject": "/root",
                        "message": f"Detected {unit_system} unit system; Young's moduli are within plausible range."})

    return out


# =============================================================================
# Aggregator
# =============================================================================


def summarize(root):
    nodes = []
    class_counts = {}
    object_count = 0
    mechanical_object_count = 0
    for node, path in _iter_nodes(root, "/root"):
        try:
            node_name = node.getName() if hasattr(node, "getName") else getattr(node, "name", None)
        except Exception:
            node_name = None
        objects = []
        for obj in getattr(node, "objects", []):
            cls = _safe_class_name(obj)
            obj_name = _safe_obj_name(obj)
            try:
                template = str(obj.findData("template").value) if obj.findData("template") else None
            except Exception:
                template = None
            objects.append({"class": cls, "name": obj_name, "template": template})
            object_count += 1
            class_counts[cls] = class_counts.get(cls, 0) + 1
            if cls == "MechanicalObject":
                mechanical_object_count += 1
        nodes.append({"path": path, "name": node_name, "objectCount": len(objects), "objects": objects})

    checks = []
    for fn in (
        check_rule_1_plugins,
        check_rule_2_animation_loop,
        check_rule_3_time_integration,
        check_rule_4_linear_solver,
        check_rule_5_constraint_handling,
        check_rule_6_forcefield_mapping,
        check_rule_7_topology,
        check_rule_8_collision_pipeline,
        check_rule_9_units,
    ):
        try:
            checks.extend(fn(root))
        except Exception as e:
            checks.append({
                "rule": fn.__name__.replace("check_", ""),
                "severity": "error",
                "subject": "/root",
                "message": f"Internal check error: {e}",
            })

    # Legacy boolean back-compat aggregated from new checks.
    has_animation_loop = _tree_has_class(root, "FreeMotionAnimationLoop") or _tree_has_class(root, "DefaultAnimationLoop")
    has_constraint_solver = _tree_has_class(root, "NNCGConstraintSolver") or _tree_has_class(root, "QPInverseProblemSolver")
    has_time_integration = any(
        (_plugin_of(_safe_class_name(o)) or "").startswith("Sofa.Component.ODESolver.")
        for n, _ in _iter_nodes(root) for o in getattr(n, "objects", [])
    )

    return {
        "success": True,
        "node_count": len(nodes),
        "object_count": object_count,
        "class_counts": class_counts,
        "mechanical_object_count": mechanical_object_count,
        "checks": checks,
        "has_animation_loop": has_animation_loop,
        "has_constraint_solver": has_constraint_solver,
        "has_time_integration": has_time_integration,
        "nodes": nodes,
    }


# =============================================================================
# Entry
# =============================================================================


def _main():
    if "createScene" not in globals():
        print("ERROR: createScene function missing", file=sys.stderr)
        sys.exit(1)
    root = Sofa.Core.Node("root")
    try:
        createScene(root)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
    summary = summarize(root)
    print("SCENE_SUMMARY_JSON:" + json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    _main()
