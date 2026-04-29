"""Tests for diagnostics.diagnose_scene (Steps 2 + 3).

Coverage:
  - Happy path: archiv/cantilever_beam.py runs, displacement non-zero, no NaN.
  - Anomaly lift: a Rule-4 trigger scene (implicit ODE solver, no linear solver
    in scope) shows up in `anomalies` lifted from summarize_scene.
  - Subprocess timeout: createScene does time.sleep(200); runner's 90s budget
    fires deterministically.
  - createScene raises: an explicit RuntimeError inside createScene; runner
    exits non-zero, parent returns success=False with anomalies still attached.
  - Step 3 runner extensions: structural §6.C check, printLog activation, and
    capture-target population — exercised via the runner subprocess directly
    (parent-side smell tests live in commit 2).
"""

import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sofa_mcp.observer import diagnostics

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON = os.path.expanduser("~/venv/bin/python")
RUNNER = os.path.join(PROJECT_ROOT, "sofa_mcp", "observer", "_diagnose_runner.py")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

if not os.path.exists(PYTHON):
    pytest.skip("SOFA env (~/venv with SofaPython3) not available", allow_module_level=True)


def test_diagnose_scene_happy_path():
    scene_path = os.path.join(PROJECT_ROOT, "archiv", "cantilever_beam.py")
    assert os.path.exists(scene_path), "cantilever_beam.py fixture missing"

    result = diagnostics.diagnose_scene(scene_path, steps=50, dt=0.01)

    assert result["success"] is True, f"diagnose failed: {result}"
    metrics = result["metrics"]
    assert metrics["nan_first_step"] is None, "unexpected NaN in cantilever beam"

    disp = metrics["max_displacement_per_mo"]
    assert disp, "expected at least one MO in displacement map"
    # The beam should deflect under gravity in 50 steps.
    assert any(v > 0.0 for v in disp.values()), (
        f"expected non-zero displacement on at least one MO; got {disp}"
    )

    summary = result["scene_summary"]
    assert summary["node_count"] >= 2  # root + beam
    assert summary["actuators_only"] is False  # no QP solver in this scene


_RULE_4_TRIGGER_SCENE = """
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Direct")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.ODESolver.Backward")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.FEM.Elastic")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.StateContainer")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Mass")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Grid")
    rootNode.addObject("DefaultAnimationLoop")
    rootNode.addObject("EulerImplicitSolver")
    rootNode.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    n = rootNode.addChild("body")
    # Implicit ODE here; no linear solver in same node or descendants. Rule 4 fires.
    n.addObject("EulerImplicitSolver")
    n.addObject("RegularGridTopology", min=[0,0,0], max=[1,1,1], n=[3,3,3])
    n.addObject("MechanicalObject")
    n.addObject("UniformMass", totalMass=1.0)
    n.addObject("TetrahedronFEMForceField", youngModulus=1e5, poissonRatio=0.3)
"""


def test_diagnose_scene_anomaly_lift_rule_4(tmp_path):
    scene_file = tmp_path / "rule_4_trigger.py"
    scene_file.write_text(_RULE_4_TRIGGER_SCENE)

    result = diagnostics.diagnose_scene(str(scene_file), steps=5, dt=0.01)

    # Whether the runner succeeds or not depends on SOFA tolerance; the anomaly
    # comes from the parent's summarize call regardless.
    rule_4 = [a for a in result["anomalies"] if a.get("rule") == "rule_4_linear_solver"]
    assert rule_4, f"expected rule_4_linear_solver in anomalies; got {result['anomalies']}"
    assert any(a.get("severity") == "error" for a in rule_4)


_TIMEOUT_SCENE = """
import time

def createScene(rootNode):
    time.sleep(200)
"""


def test_diagnose_scene_runner_timeout(tmp_path, monkeypatch):
    scene_file = tmp_path / "sleep_forever.py"
    scene_file.write_text(_TIMEOUT_SCENE)

    # Cap the runner timeout; the default 90s makes the test slow even though it
    # would still pass.
    monkeypatch.setattr(diagnostics, "RUNNER_TIMEOUT_S", 5)

    result = diagnostics.diagnose_scene(str(scene_file), steps=1, dt=0.01)

    assert result["success"] is False
    assert result.get("error") == "Timeout"
    # Anomalies still attached even on runner failure.
    assert isinstance(result.get("anomalies"), list)


_RAISE_IN_CREATE_SCENE = """
def createScene(rootNode):
    raise RuntimeError("intentionally broken for test")
"""


def test_diagnose_scene_create_scene_raises(tmp_path):
    scene_file = tmp_path / "broken_create_scene.py"
    scene_file.write_text(_RAISE_IN_CREATE_SCENE)

    result = diagnostics.diagnose_scene(str(scene_file), steps=1, dt=0.01)

    assert result["success"] is False
    # Runner wrote a payload with the traceback OR runner died before write —
    # both paths land here. anomalies must still ship.
    assert isinstance(result.get("anomalies"), list)
    err_blob = (result.get("error") or "") + (result.get("traceback") or "")
    assert "intentionally broken for test" in err_blob, (
        f"expected the RuntimeError message in error/traceback; got error={result.get('error')!r}, "
        f"traceback={result.get('traceback')!r}"
    )


# =============================================================================
# Step 3 commit 1: runner extensions
# =============================================================================


def _run_runner_directly(scene_path, steps=0, dt=0.01):
    """Spawn the runner subprocess and return the parsed JSON payload.

    Used to exercise runner-side state (structural anomalies, printLog
    activation, capture targets) without going through the parent
    orchestrator — the parent's smell-test consumers ship in commit 2.
    """
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
        out_path = tmp.name
    try:
        subprocess.run(
            [PYTHON, RUNNER, scene_path, str(steps), str(dt), out_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


def test_runner_structural_anomaly_multimapping_node_has_solver():
    """§6.C.1 trigger: a node with both *MultiMapping and an ODE solver lifts
    a structural anomaly from the runner. steps=0 keeps the run inside init
    only — animate is unsafe with a SubsetMultiMapping that shares a node
    with an ODE solver (SOFA segfaults during integration).
    """
    fixture = os.path.join(FIXTURES_DIR, "multimapping_with_solver.py")
    assert os.path.exists(fixture)

    payload = _run_runner_directly(fixture, steps=0)

    structural = payload["structural_anomalies"]
    assert isinstance(structural, list) and structural, (
        f"expected at least one structural anomaly; got {structural}"
    )
    rule_hits = [a for a in structural if a.get("rule") == "multimapping_node_has_solver"]
    assert rule_hits, f"missing multimapping_node_has_solver; saw rules {[a.get('rule') for a in structural]}"
    assert rule_hits[0]["severity"] == "error"
    assert rule_hits[0]["subject"] == "/root/combined"
    assert {"rule", "severity", "subject", "message"} <= set(rule_hits[0])


def test_runner_printlog_activation_targets():
    """Cantilever beam exercises the four printLog target categories
    (animation loop, constraint solver, ODE solver, constraint correction)
    plus negative cases (linear solver should NOT activate, MechanicalObject
    should NOT activate).
    """
    scene = os.path.join(PROJECT_ROOT, "archiv", "cantilever_beam.py")
    payload = _run_runner_directly(scene, steps=0)

    activated = payload["printLog_activated"]
    assert payload["plugin_cache_empty"] is False, (
        "test environment should have a populated plugin cache"
    )
    # Positive cases.
    assert any("FreeMotionAnimationLoop" in p for p in activated)
    assert any("NNCGConstraintSolver" in p for p in activated)
    assert any("EulerImplicitSolver" in p for p in activated)
    assert any("GenericConstraintCorrection" in p for p in activated)
    # Negative cases: linear solvers + MechanicalObjects must not be touched.
    assert not any("SparseLDLSolver" in p for p in activated), (
        f"SparseLDLSolver should not be a printLog target; got {activated}"
    )
    assert not any("MechanicalObject" in p for p in activated)


def test_runner_capture_targets_extents_and_iterations():
    """Cantilever beam: extents_per_mo populated for the unmapped beam MO;
    solver_iterations + solver_max_iterations populated for NNCGConstraintSolver.
    """
    scene = os.path.join(PROJECT_ROOT, "archiv", "cantilever_beam.py")
    payload = _run_runner_directly(scene, steps=3, dt=0.01)

    extents = payload["extents_per_mo"]
    assert "/root/beam" in extents, f"expected /root/beam extent; got {extents}"
    # Beam grid is min=[-2,-2,0] max=[2,2,50] — max axis extent is 50.
    assert extents["/root/beam"] == pytest.approx(50.0, abs=0.01)

    iters_map = payload["solver_iterations"]
    max_iters_map = payload["solver_max_iterations"]
    nncg_keys = [k for k in iters_map if "NNCGConstraintSolver" in k]
    assert nncg_keys, f"expected an NNCGConstraintSolver key; got {list(iters_map.keys())}"
    nncg_key = nncg_keys[0]
    # 3 steps → 3 currentIterations samples.
    assert len(iters_map[nncg_key]) == 3
    assert all(isinstance(i, int) for i in iters_map[nncg_key])
    assert nncg_key in max_iters_map
    assert max_iters_map[nncg_key] > 0


def test_runner_objective_series_for_qp_solver():
    """The QP-infeasible fixture has a QPInverseProblemSolver — objective
    series should populate (one float per step) even though the QP is
    actually infeasible (the solver still reports an objective each step).
    """
    fixture = os.path.join(FIXTURES_DIR, "qp_infeasible.py")
    assert os.path.exists(fixture)

    payload = _run_runner_directly(fixture, steps=4, dt=0.01)

    series_map = payload["objective_series"]
    qp_keys = [k for k in series_map if "QPInverseProblemSolver" in k]
    assert qp_keys, f"expected a QPInverseProblemSolver objective series; got {list(series_map.keys())}"
    series = series_map[qp_keys[0]]
    assert len(series) == 4, f"expected 4 samples for 4 steps; got {series}"
    assert all(isinstance(v, float) for v in series)
