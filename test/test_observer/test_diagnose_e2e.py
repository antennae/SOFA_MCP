"""End-to-end M5 gate tests — automated half.

For each of the four M5 fixtures, assert that the diagnose toolkit
surfaces the expected signal:
  - m5_cables_unactuated: NO anomaly fires; max_displacement_per_mo
    near zero; perturb_and_run with restored cable value yields
    larger displacement (data-driven hypothesis path).
  - m5_units_mismatch: rule_9_units fires at warning severity.
  - m5_missing_collision: rule_8_collision_pipeline fires at error.
  - m5_broken_mapping: rule_7_topology fires at error.

The agent-reasoning half of M5 ((b) hypothesis, (c) probe call) is
verified manually per docs/specs/2026-05-02-m5-gate.md.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sofa_mcp.observer import diagnostics, probes

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON = os.path.expanduser("~/venv/bin/python")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

if not os.path.exists(PYTHON):
    pytest.skip("SOFA env (~/venv with SofaPython3) not available", allow_module_level=True)


def test_m5_cables_unactuated_data_driven():
    """Fixture 1: tri-leg cable scene with all CableConstraint values
    pinned to 0. No anomaly should fire — diagnose returns success=True
    with all rules ok. The agent must reason from low max_displacement.

    This test asserts the *data-driven* path: max_displacement is near
    zero, AND a perturb_and_run with restored cable values produces a
    much larger displacement (confirming the wiring is fine and the
    bug is the value field). The agent-hypothesis part of M5 is
    verified manually."""
    fixture = os.path.join(FIXTURES_DIR, "m5_cables_unactuated.py")
    assert os.path.exists(fixture), "fixture missing"

    baseline = diagnostics.diagnose_scene(fixture, steps=20, dt=0.01)
    assert baseline["success"] is True, f"diagnose failed: {baseline.get('error')}"

    # No smell-test slug should fire on a stable but unactuated scene.
    smell_slugs = {"excessive_displacement", "solver_iter_cap_hit",
                   "inverse_objective_not_decreasing", "qp_infeasible_in_log",
                   "multimapping_node_has_solver"}
    fired = [a for a in baseline["anomalies"] if a.get("rule") in smell_slugs]
    assert not fired, f"unexpected smell slug fired: {fired}"

    disps = baseline["metrics"]["max_displacement_per_mo"]
    assert disps, "expected per-MO displacement entries"
    max_disp = max(disps.values())
    # Beam fall under gravity is bounded by FixedProjectiveConstraint at base.
    # Cables at value=0 keep the rest of the leg passive; max_disp should be
    # tiny relative to the 100mm leg height.
    assert max_disp < 5.0, (
        f"expected near-zero displacement on unactuated leg; got {max_disp}"
    )

    # Now perturb: restore cable_0 to value=22; expect bigger displacement on Leg_0.
    perturbed = probes.perturb_and_run(
        scene_path=fixture,
        parameter_changes={"/root/Leg_0/cable_0": {"value": 22.0}},
        steps=20,
        dt=0.01,
    )
    assert perturbed["success"] is True, f"perturb failed: {perturbed}"
    assert perturbed["parameter_changes_applied"], (
        f"perturb didn't apply: {perturbed.get('parameter_changes_failed')}"
    )
    perturbed_disp = max(perturbed["metrics"]["max_displacement_per_mo"].values(), default=0.0)
    assert perturbed_disp > max_disp * 3, (
        f"expected restored cable to produce ~3× displacement; "
        f"baseline={max_disp}, perturbed={perturbed_disp}"
    )


def test_m5_units_mismatch_rule_9_warning():
    """Fixture 2: mm/g/s gravity with absurdly stiff youngModulus (SI-Pa
    interpreted as mm/g/s scale). Rule 9 fires at WARNING severity per
    the check at _summary_runtime_template.py: gmag≈9810 → mm/g/s →
    ym>1e9 is suspicious."""
    fixture = os.path.join(FIXTURES_DIR, "m5_units_mismatch.py")
    assert os.path.exists(fixture)

    result = diagnostics.diagnose_scene(fixture, steps=5, dt=0.01)

    rule_9 = [a for a in result["anomalies"] if a.get("rule") == "rule_9_units"]
    assert rule_9, f"expected rule_9_units; got {result['anomalies']}"
    # Severity is warning per the rule check, not error.
    assert any(a.get("severity") == "warning" for a in rule_9), (
        f"expected rule_9 warning severity; got {[a.get('severity') for a in rule_9]}"
    )


def test_m5_missing_collision_rule_8_error():
    """Fixture 3: scene with *CollisionModel components but no root-level
    pipeline (no CollisionPipeline / BroadPhase / NarrowPhase /
    Intersection / CollisionResponse). Rule 8 fires at error severity."""
    fixture = os.path.join(FIXTURES_DIR, "m5_missing_collision.py")
    assert os.path.exists(fixture)

    result = diagnostics.diagnose_scene(fixture, steps=5, dt=0.01)

    rule_8 = [a for a in result["anomalies"] if a.get("rule") == "rule_8_collision_pipeline"]
    assert rule_8, f"expected rule_8_collision_pipeline; got {result['anomalies']}"
    assert any(a.get("severity") == "error" for a in rule_8), (
        f"expected rule_8 error severity; got {[a.get('severity') for a in rule_8]}"
    )


def test_m5_broken_mapping_rule_7_error():
    """Fixture 4: BarycentricMapping in a child node whose parent has
    only a bare MeshTopology (no filename Data, no loader sibling, no
    shell FEM). Rule 7B fires at error severity per
    _summary_runtime_template.py:check_rule_7_topology."""
    fixture = os.path.join(FIXTURES_DIR, "m5_broken_mapping.py")
    assert os.path.exists(fixture)

    result = diagnostics.diagnose_scene(fixture, steps=5, dt=0.01)

    rule_7 = [a for a in result["anomalies"]
              if a.get("rule") == "rule_7_topology" and a.get("severity") == "error"]
    assert rule_7, (
        f"expected rule_7_topology error; got {result['anomalies']}"
    )
