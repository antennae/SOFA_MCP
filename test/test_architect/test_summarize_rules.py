"""Tests for the 9 SKILL.md Health Rule checks emitted by summarize_scene.

Plan: 21 synthetic fixtures (9 happy + 9 trigger + 3 targeted edges) plus
2 upstream-SOFA smoke tests. See spec §1.5.2.
"""
from __future__ import annotations

import os
import pytest

from sofa_mcp.architect.scene_writer import summarize_scene


# Plugin lists used across fixtures.
P_BASE = (
    "Sofa.Component.AnimationLoop",
    "Sofa.Component.Constraint.Lagrangian.Solver",
    "Sofa.Component.Constraint.Lagrangian.Correction",
    "Sofa.Component.Constraint.Projective",
    "Sofa.Component.LinearSolver.Direct",
    "Sofa.Component.ODESolver.Backward",
    "Sofa.Component.SolidMechanics.FEM.Elastic",
    "Sofa.Component.StateContainer",
    "Sofa.Component.Topology.Container.Grid",
    "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.Mass",
    "Sofa.Component.Mapping.Linear",
)


def _plugins_block(plugins) -> str:
    return "\n    ".join(f'rootNode.addObject("RequiredPlugin", name="{p}")' for p in plugins)


def _summarize(script: str) -> dict:
    result = summarize_scene(script)
    assert result.get("success"), f"summarize_scene failed: {result}"
    return result


def _checks(result: dict) -> list:
    return result["checks"]


def _has(checks, rule: str, severity: str) -> bool:
    return any(c["rule"] == rule and c["severity"] == severity for c in checks)


def _has_with_subject(checks, rule: str, severity: str, subject_substr: str) -> bool:
    return any(
        c["rule"] == rule and c["severity"] == severity and subject_substr in c["subject"]
        for c in checks
    )


# =============================================================================
# Rule 1 — Plugins
# =============================================================================


def test_rule_1_happy_all_plugins_declared():
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("NNCGConstraintSolver", maxIterations=50, tolerance=1e-5)
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("RegularGridTopology", n=[3,3,3], min=[0,0,0], max=[10,10,10])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("HexahedronFEMForceField", youngModulus=1000, poissonRatio=0.3)
    body.addObject("GenericConstraintCorrection")
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_1_plugins", "ok")
    assert not _has(checks, "rule_1_plugins", "error")


def test_rule_1_trigger_missing_plugin():
    # Bypass RequiredPlugin via SofaRuntime.importPlugin so the class exists in the factory
    # but isn't declared via RequiredPlugin → Rule 1 should flag it.
    missing = [p for p in P_BASE if p != "Sofa.Component.StateContainer"]
    script = f'''
def createScene(rootNode):
    import SofaRuntime
    SofaRuntime.importPlugin("Sofa.Component.StateContainer")
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(missing)}
    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("NNCGConstraintSolver")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("RegularGridTopology", n=[3,3,3], min=[0,0,0], max=[10,10,10])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("HexahedronFEMForceField", youngModulus=1000, poissonRatio=0.3)
    body.addObject("GenericConstraintCorrection")
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_1_plugins", "error")


# =============================================================================
# Rule 2 — Animation Loop
# =============================================================================


def test_rule_2_happy_freemotion_with_constraint():
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("NNCGConstraintSolver")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("GenericConstraintCorrection")
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_2_animation_loop", "ok")


def test_rule_2_trigger_silent_default_loop():
    # No animation loop declared at all.
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
'''
    checks = _checks(_summarize(script))
    # Either "warning" (no loop) or "error" (FreeMotion needed but Default present) is acceptable.
    assert _has(checks, "rule_2_animation_loop", "warning") or _has(checks, "rule_2_animation_loop", "error")


# =============================================================================
# Rule 3 — Time Integration
# =============================================================================


def test_rule_3_happy_solver_in_ancestor():
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_3_time_integration", "ok")


def test_rule_3_trigger_unmapped_mo_no_solver():
    # MO in body, no ODE solver in ancestor chain.
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_3_time_integration", "error")


# =============================================================================
# Rule 4 — Linear Solver (SearchDown scope)
# =============================================================================


def test_rule_4_happy_solver_same_node():
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_4_linear_solver", "ok")


def test_rule_4_trigger_only_ancestor_solver():
    # Implicit ODE in body, linear solver only at root → SearchDown fails.
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("DefaultAnimationLoop")
    rootNode.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_4_linear_solver", "error")


# =============================================================================
# Rule 5 — Constraint Handling (3 sub-checks)
# =============================================================================


def test_rule_5_happy_freemotion_with_correction():
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("NNCGConstraintSolver")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("GenericConstraintCorrection")
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_5_constraint_handling", "ok")


def test_rule_5_trigger_no_correction_in_subtree():
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("NNCGConstraintSolver")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
'''
    checks = _checks(_summarize(script))
    assert _has_with_subject(checks, "rule_5_constraint_handling", "error", "/root/body")


def test_rule_5_edge_inverse_class_without_qp():
    """Targeted edge: SoftRobots.Inverse class detected via plugin attribution requires QPInverseProblemSolver."""
    plugins = list(P_BASE) + ["SoftRobots", "SoftRobots.Inverse"]
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(plugins)}
    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("NNCGConstraintSolver")  # forward solver — wrong for inverse classes
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("GenericConstraintCorrection")
    # Inverse-plugin class without QP solver:
    body.addObject("PositionEffector", indices=[0], effectorGoal=[1, 0, 0])
'''
    checks = _checks(_summarize(script))
    inverse_msgs = [c for c in checks if c["rule"] == "rule_5_constraint_handling" and c["severity"] == "error"
                    and "QPInverseProblemSolver" in c["message"]]
    assert inverse_msgs, f"expected an inverse-plugin error; got {checks}"


# =============================================================================
# Rule 6 — ForceField Mapping
# =============================================================================


def test_rule_6_happy_ff_with_mo_in_node():
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("RegularGridTopology", n=[3,3,3], min=[0,0,0], max=[10,10,10])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("HexahedronFEMForceField", youngModulus=1000, poissonRatio=0.3)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_6_forcefield_mapping", "ok")


def test_rule_6_pair_interaction_exempt():
    """Pair-interaction force fields with object1/object2 set are exempt from Rule 6.

    Note: Rule 6's "ForceField without MechanicalObject in ancestor chain" trigger is preempted
    at SOFA's factory level — SOFA refuses to construct such an FF, so the static check would
    only ever fire if SOFA's runtime check were bypassed (in practice: never). The rule's
    real testable value is the exemption logic for pair/mixed-interaction force fields, which
    is what this test exercises.
    """
    plugins = list(P_BASE) + ["Sofa.Component.SolidMechanics.Spring"]
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(plugins)}
    rootNode.addObject("DefaultAnimationLoop")
    body1 = rootNode.addChild("body1")
    body1.addObject("EulerImplicitSolver")
    body1.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body1.addObject("MechanicalObject", template="Vec3d", position=[[0,0,0],[1,0,0]])
    body1.addObject("UniformMass", totalMass=1.0)
    body2 = rootNode.addChild("body2")
    body2.addObject("EulerImplicitSolver")
    body2.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body2.addObject("MechanicalObject", template="Vec3d", position=[[0,1,0],[1,1,0]])
    body2.addObject("UniformMass", totalMass=1.0)
    # Pair-interaction with explicit object1/object2 — should NOT trigger Rule 6.
    rootNode.addObject("SpringForceField",
        object1="@body1/MechanicalObject", object2="@body2/MechanicalObject",
        spring=[[0, 0, 100, 0.1, 1.0]])
'''
    checks = _checks(_summarize(script))
    rule_6_errors = [c for c in checks if c["rule"] == "rule_6_forcefield_mapping" and c["severity"] == "error"]
    assert not rule_6_errors, f"Pair-interaction FF false-positive: {rule_6_errors}"


# =============================================================================
# Rule 7 — Topology
# =============================================================================


def test_rule_7_happy_tetra_ff_with_volumetric_topo():
    plugins = list(P_BASE) + ["Sofa.Component.Topology.Container.Dynamic"]
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(plugins)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("TetrahedronSetTopologyContainer",
        position=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]], tetrahedra=[[0,1,2,3]])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("TetrahedronFEMForceField", youngModulus=1000, poissonRatio=0.3)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_7_topology", "ok")


def test_rule_7_trigger_tetra_ff_with_surface_topo():
    plugins = list(P_BASE) + ["Sofa.Component.Topology.Container.Dynamic"]
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(plugins)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("TriangleSetTopologyContainer",
        position=[[0,0,0],[1,0,0],[0,1,0]], triangles=[[0,1,2]])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("TetrahedronFEMForceField", youngModulus=1000, poissonRatio=0.3)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_7_topology", "error")


def test_rule_7_edge_barycentric_with_shell_fem_parent():
    """Targeted edge: BarycentricMapping with TriangularFEMForceField parent should NOT trigger (shell exemption)."""
    plugins = list(P_BASE) + ["Sofa.GL.Component.Rendering3D"]
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(plugins)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("TriangleSetTopologyContainer",
        position=[[0,0,0],[1,0,0],[0,1,0]], triangles=[[0,1,2]])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("TriangularFEMForceField", youngModulus=1000, poissonRatio=0.3)
    visual = body.addChild("visual")
    visual.addObject("OglModel")
    visual.addObject("BarycentricMapping")
'''
    checks = _checks(_summarize(script))
    # Rule 7 should NOT emit error on the BarycentricMapping under shell FEM.
    rule_7_errors = [c for c in checks if c["rule"] == "rule_7_topology" and c["severity"] == "error"]
    assert not rule_7_errors, f"Shell-FEM exemption failed: {rule_7_errors}"


# =============================================================================
# Rule 8 — Collision pipeline
# =============================================================================


def test_rule_8_happy_full_pipeline():
    plugins = list(P_BASE) + [
        "Sofa.Component.Collision.Detection.Algorithm",
        "Sofa.Component.Collision.Detection.Intersection",
        "Sofa.Component.Collision.Geometry",
        "Sofa.Component.Collision.Response.Contact",
    ]
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(plugins)}
    rootNode.addObject("DefaultAnimationLoop")
    rootNode.addObject("CollisionPipeline")
    rootNode.addObject("BruteForceBroadPhase")
    rootNode.addObject("BVHNarrowPhase")
    rootNode.addObject("MinProximityIntersection")
    rootNode.addObject("CollisionResponse")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d", position=[[0,0,0],[1,0,0]])
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("PointCollisionModel")
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_8_collision_pipeline", "ok")


def test_rule_8_trigger_collision_model_no_pipeline():
    plugins = list(P_BASE) + ["Sofa.Component.Collision.Geometry"]
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(plugins)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d", position=[[0,0,0],[1,0,0]])
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("PointCollisionModel")
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_8_collision_pipeline", "error")


# =============================================================================
# Rule 9 — Units
# =============================================================================


def test_rule_9_happy_si_consistent():
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("RegularGridTopology", n=[3,3,3], min=[0,0,0], max=[1,1,1])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("HexahedronFEMForceField", youngModulus=1e6, poissonRatio=0.3)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_9_units", "ok")


def test_rule_9_trigger_si_with_mm_ym():
    """SI gravity but a force field with an mm/g/s-magnitude YM is suspicious in only one direction:
    SI-low (<100). To cleanly trigger, set a tiny YM in an SI scene."""
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("RegularGridTopology", n=[3,3,3], min=[0,0,0], max=[1,1,1])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("HexahedronFEMForceField", youngModulus=10, poissonRatio=0.3)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_9_units", "warning")


def test_rule_9_edge_gravity_typo():
    """Targeted edge: -9180 typo discriminator."""
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9180, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
'''
    checks = _checks(_summarize(script))
    assert _has(checks, "rule_9_units", "error")
    typo = [c for c in checks if c["rule"] == "rule_9_units" and "typo" in c["message"]]
    assert typo


# =============================================================================
# Legacy boolean back-compat
# =============================================================================


def test_legacy_booleans_still_present():
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(P_BASE)}
    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("NNCGConstraintSolver")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("GenericConstraintCorrection")
'''
    result = _summarize(script)
    assert result["has_animation_loop"] is True
    assert result["has_constraint_solver"] is True
    assert result["has_time_integration"] is True


# =============================================================================
# Upstream SOFA smoke tests — assert no error-severity check fires.
# Skipped if the upstream tree isn't present (e.g., portable environments).
# =============================================================================


def _strip_main_block(content: str) -> str:
    """Strip `if __name__ == '__main__'` blocks so the wrapper's _main runs, not the script's."""
    import re
    parts = re.split(r"\nif\s+__name__\s*==", content, maxsplit=1)
    return parts[0]


_UPSTREAM_LIVER = "/home/sizhe/workspace/sofa/src/applications/plugins/SofaPython3/examples/liver.py"


@pytest.mark.skipif(not os.path.exists(_UPSTREAM_LIVER), reason="upstream liver.py not available")
def test_upstream_smoke_liver():
    """liver.py — full real-world scene: DefaultAnimationLoop, collision pipeline, Tetra FEM,
    BarycentricMapping. None of our 9 rules should fire `error` severity."""
    with open(_UPSTREAM_LIVER) as f:
        content = _strip_main_block(f.read())
    result = _summarize(content)
    errors = [c for c in result["checks"] if c["severity"] == "error"]
    assert not errors, "Upstream liver.py false-positives:\n" + "\n".join(
        f"  [{c['rule']}] {c['subject']}: {c['message']}" for c in errors
    )


# Pick a second upstream that uses different patterns. caduceus example via SimpleAPI is a good target,
# but most SimpleAPI scenes are .py. Use emptyForceField.py (minimalist scaffolding test).
_UPSTREAM_EMPTY_FF = "/home/sizhe/workspace/sofa/src/applications/plugins/SofaPython3/examples/emptyForceField.py"


@pytest.mark.skipif(not os.path.exists(_UPSTREAM_EMPTY_FF), reason="upstream emptyForceField.py not available")
def test_upstream_smoke_empty_forcefield():
    with open(_UPSTREAM_EMPTY_FF) as f:
        content = _strip_main_block(f.read())
    result = _summarize(content)
    errors = [c for c in result["checks"] if c["severity"] == "error"]
    assert not errors, "Upstream emptyForceField.py false-positives:\n" + "\n".join(
        f"  [{c['rule']}] {c['subject']}: {c['message']}" for c in errors
    )
