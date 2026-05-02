"""Regression for the tri-leg-inverse authoring demo.

Asserts:
  - the example scene at archiv/tri_leg_inverse.py initializes and
    animates one step cleanly via validate_scene;
  - diagnose_scene over 80 steps reports success with no
    inverse_objective_not_decreasing warning (the QP objective
    converges) and no qp_infeasible_in_log warning (actuator bounds
    are valid).

The visual M6 sign-off (open the rendered PNG, see the robot reaching
the target) is manual and not part of pytest."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sofa_mcp.architect import scene_writer
from sofa_mcp.observer import diagnostics

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON = os.path.expanduser("~/venv/bin/python")
FIXTURE = os.path.join(PROJECT_ROOT, "archiv", "tri_leg_inverse.py")

if not os.path.exists(PYTHON):
    pytest.skip("SOFA env (~/venv with SofaPython3) not available", allow_module_level=True)


def _read_fixture_text():
    assert os.path.exists(FIXTURE), f"missing fixture: {FIXTURE}"
    with open(FIXTURE, "r", encoding="utf-8") as f:
        return f.read()


def test_tri_leg_inverse_validates():
    """validate_scene should succeed (init + 1 animate step)."""
    text = _read_fixture_text()
    result = scene_writer.validate_scene(text)
    assert result["success"] is True, f"validate failed: {result.get('error')}"


def test_tri_leg_inverse_converges():
    """diagnose_scene over 80 steps: no convergence stall, no QP
    infeasibility. The fixture is the convergence regression net for M6."""
    result = diagnostics.diagnose_scene(FIXTURE, steps=80, dt=0.01)
    assert result["success"] is True, f"diagnose failed: {result.get('error')}"

    bad_slugs = {"inverse_objective_not_decreasing", "qp_infeasible_in_log"}
    fired = [a for a in result["anomalies"] if a.get("rule") in bad_slugs]
    assert not fired, (
        f"expected clean convergence; got smell warnings: {fired}\n"
        f"full anomalies: {result['anomalies']}"
    )
