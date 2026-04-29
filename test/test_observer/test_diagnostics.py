"""Tests for diagnostics.diagnose_scene (Step 2).

Coverage:
  - Happy path: archiv/cantilever_beam.py runs, displacement non-zero, no NaN.
  - Anomaly lift: a Rule-4 trigger scene (implicit ODE solver, no linear solver
    in scope) shows up in `anomalies` lifted from summarize_scene.
  - Subprocess timeout: createScene does time.sleep(200); runner's 90s budget
    fires deterministically.
  - createScene raises: an explicit RuntimeError inside createScene; runner
    exits non-zero, parent returns success=False with anomalies still attached.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sofa_mcp.observer import diagnostics

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON = os.path.expanduser("~/venv/bin/python")

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
