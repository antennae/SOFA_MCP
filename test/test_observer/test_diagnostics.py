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


# =============================================================================
# Step 3 commit 2: parent smell tests + truncation (pure-function unit tests)
# =============================================================================


def test_check_inverse_objective_flat_at_value_fires():
    """Last 5 steps flat at 9.1, well above the 1e-6 at-optimum guard."""
    series = {"/root::QP": [10, 9.5, 9.2, 9.1, 9.1, 9.1, 9.1, 9.1]}
    out = diagnostics._check_inverse_objective_not_decreasing(series)
    assert len(out) == 1
    assert out[0]["rule"] == "inverse_objective_not_decreasing"
    assert out[0]["subject"] == "/root::QP"
    assert out[0]["objective_tail"] == [9.1, 9.1, 9.1, 9.1, 9.1]


def test_check_inverse_objective_strictly_decreasing_does_not_fire():
    """Strictly decreasing series must not fire — even with the absolute-
    floor tolerance, big steps like 2 → 1 exceed any reasonable tol_abs.
    """
    series = {"/root::QP": [5, 4, 3, 2, 1, 0.5, 0.1, 0]}
    out = diagnostics._check_inverse_objective_not_decreasing(series)
    assert out == []


def test_check_inverse_objective_at_optimum_does_not_fire():
    """A series flat at 1e-7 is the at-optimum case the guard exists to
    handle. Without obj[-1] > 1e-6 the rule would fire here because tol_abs
    is small, but the at-optimum threshold blocks it.
    """
    series = {"/root::QP": [1e-7] * 8}
    out = diagnostics._check_inverse_objective_not_decreasing(series)
    assert out == []


def test_check_inverse_objective_slight_increase_within_tol_fires():
    """A tiny upward bump within tol_abs counts as flat. Last 5 transitions
    are all within tol_abs = max(1e-9, 1e-6 * 3) = 3e-6, and obj[-1]=3 > 1e-6."""
    series = {"/root::QP": [5, 4, 3, 3.0000001, 3, 3, 3, 3]}
    out = diagnostics._check_inverse_objective_not_decreasing(series)
    assert len(out) == 1


def test_check_inverse_objective_short_series_does_not_fire():
    """Series shorter than the window cannot fire."""
    out = diagnostics._check_inverse_objective_not_decreasing({"/root::QP": [10, 9, 8]})
    assert out == []
    assert diagnostics._check_inverse_objective_not_decreasing({}) == []


def test_check_qp_infeasible_in_log_counts_matches():
    log = "QP infeasible at step 3\nblah blah\nQP infeasible at step 7"
    out = diagnostics._check_qp_infeasible_in_log(log)
    assert len(out) == 1
    assert out[0]["rule"] == "qp_infeasible_in_log"
    assert out[0]["match_count"] == 2
    assert out[0]["severity"] == "error"


def test_check_qp_infeasible_in_log_no_matches():
    assert diagnostics._check_qp_infeasible_in_log("") == []
    assert diagnostics._check_qp_infeasible_in_log("everything fine here") == []


def test_truncate_log_under_budget_passes_through():
    short = "x" * 100
    assert diagnostics._truncate_log(short) == short


def test_truncate_log_over_budget_uses_head_tail_split():
    head_chars = 10
    tail_chars = 20
    text = "A" * head_chars + ("B\n" * 50) + "C" * tail_chars
    out = diagnostics._truncate_log(text, head_chars=head_chars, tail_chars=tail_chars)
    assert out.startswith("A" * head_chars)
    assert out.endswith("C" * tail_chars)
    assert "lines elided" in out
    # Elided segment is "B\nB\n... B\n" — 50 newlines.
    assert "<50 lines elided>" in out


def test_check_excessive_displacement_two_tier():
    metrics = {"max_displacement_per_mo": {"/a": 50.0, "/b": 500.0, "/c": 5050.0}}
    extents = {"/a": 50.0, "/b": 50.0, "/c": 50.0}
    out = diagnostics._check_excessive_displacement(metrics, extents)
    by_subject = {a["subject"]: a for a in out}
    assert "/a" not in by_subject  # ratio 1.0 — clean
    assert by_subject["/b"]["severity"] == "warning"  # ratio 10.0
    assert by_subject["/c"]["severity"] == "error"  # ratio 101.0


def test_check_excessive_displacement_skips_missing_extent():
    """A MO that has displacement but no recorded extent (degenerate or
    single-point) is skipped — no anomaly fires, but caller still has the
    raw displacement available in the metrics dict."""
    metrics = {"max_displacement_per_mo": {"/a": 1000.0}}
    extents = {}  # No extent recorded.
    assert diagnostics._check_excessive_displacement(metrics, extents) == []


def test_check_solver_iter_cap_hit_records_step_indices():
    iters = {"/root::NNCG": [10, 10, 5, 10, 10]}
    caps = {"/root::NNCG": 10}
    out = diagnostics._check_solver_iter_cap_hit(iters, caps)
    assert len(out) == 1
    assert out[0]["rule"] == "solver_iter_cap_hit"
    assert out[0]["steps_hit_cap"] == [0, 1, 3, 4]
    assert out[0]["max_iterations"] == 10


def test_check_solver_iter_cap_hit_no_hits():
    iters = {"/root::NNCG": [3, 5, 7, 4, 9]}
    caps = {"/root::NNCG": 10}
    assert diagnostics._check_solver_iter_cap_hit(iters, caps) == []


# =============================================================================
# Step 3 commit 2: integration tests (full diagnose_scene round-trip)
# =============================================================================


def test_diagnose_scene_excessive_displacement_fixture():
    fixture = os.path.join(FIXTURES_DIR, "excessive_displacement.py")
    assert os.path.exists(fixture)
    result = diagnostics.diagnose_scene(fixture, steps=5, dt=0.1)
    assert result["success"] is True, f"fixture should run cleanly: {result.get('error')}"
    hits = [a for a in result["anomalies"] if a.get("rule") == "excessive_displacement"]
    assert hits, f"expected excessive_displacement anomaly; got {result['anomalies']}"
    # Free-fall fixture lands in the warning band (10× ≤ ratio < 100×).
    assert hits[0]["severity"] == "warning"
    assert hits[0]["ratio"] >= 10.0


def test_diagnose_scene_iter_cap_hit_fixture():
    fixture = os.path.join(FIXTURES_DIR, "iter_cap_hit.py")
    assert os.path.exists(fixture)
    result = diagnostics.diagnose_scene(fixture, steps=5, dt=0.01)
    assert result["success"] is True, f"fixture should run cleanly: {result.get('error')}"
    hits = [a for a in result["anomalies"] if a.get("rule") == "solver_iter_cap_hit"]
    assert hits, f"expected solver_iter_cap_hit anomaly; got {result['anomalies']}"
    assert hits[0]["max_iterations"] == 2
    # Cap is 2; we ran 5 steps; every step should hit the cap.
    assert len(hits[0]["steps_hit_cap"]) == 5


def test_diagnose_scene_qp_infeasible_fixture():
    fixture = os.path.join(FIXTURES_DIR, "qp_infeasible.py")
    assert os.path.exists(fixture)
    result = diagnostics.diagnose_scene(fixture, steps=5, dt=0.01)
    # `success` may be true (SOFA reports the infeasibility but doesn't crash).
    hits = [a for a in result["anomalies"] if a.get("rule") == "qp_infeasible_in_log"]
    assert hits, f"expected qp_infeasible_in_log anomaly; got {result['anomalies']}"
    assert hits[0]["severity"] == "error"
    assert hits[0]["match_count"] >= 1


def test_diagnose_scene_multimapping_lifts_structural_anomaly():
    """Runner produces structural_anomalies; orchestrator lifts them into
    the response's `anomalies` list. steps=0 to keep init-only (animate
    segfaults on this scene)."""
    fixture = os.path.join(FIXTURES_DIR, "multimapping_with_solver.py")
    assert os.path.exists(fixture)
    result = diagnostics.diagnose_scene(fixture, steps=0, dt=0.01)
    hits = [a for a in result["anomalies"] if a.get("rule") == "multimapping_node_has_solver"]
    assert hits, f"expected multimapping_node_has_solver anomaly; got {result['anomalies']}"
    assert hits[0]["subject"] == "/root/combined"
