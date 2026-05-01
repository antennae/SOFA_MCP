"""Tests for sofa_mcp.observer.probes — high-leverage pair from Step 4."""

import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sofa_mcp.observer import probes

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON = os.path.expanduser("~/venv/bin/python")

if not os.path.exists(PYTHON):
    pytest.skip("SOFA env (~/venv with SofaPython3) not available", allow_module_level=True)


def test_enable_logs_and_run_activates_targets_by_class_name():
    """When the user passes a class name like 'EulerImplicitSolver',
    every matching object in the scene gets printLog=True. The captured
    logs include the resulting solver output."""
    scene_path = os.path.join(PROJECT_ROOT, "archiv", "cantilever_beam.py")
    assert os.path.exists(scene_path), "fixture missing"

    result = probes.enable_logs_and_run(
        scene_path=scene_path,
        log_targets=["EulerImplicitSolver"],
        steps=3,
        dt=0.01,
    )

    assert result["success"] is True, f"probe failed: {result}"
    assert result["log_targets_activated"], "expected at least one solver to be activated"
    # Activated paths are full node-paths to the matched objects; verify target was found.
    assert "EulerImplicitSolver" not in result.get("log_targets_not_found", [])
    # The captured logs must be non-empty (printLog produced output).
    assert result["logs"], "expected non-empty logs after printLog activation"


def test_enable_logs_and_run_reports_unmatched_targets():
    """A target that doesn't match anything in the scene is reported in
    log_targets_not_found; this lets the agent self-correct."""
    scene_path = os.path.join(PROJECT_ROOT, "archiv", "cantilever_beam.py")
    result = probes.enable_logs_and_run(
        scene_path=scene_path,
        log_targets=["EulerImplicitSolver", "DoesNotExistClassName"],
        steps=2,
    )
    assert result["success"] is True
    assert "DoesNotExistClassName" in result["log_targets_not_found"]


def test_enable_logs_and_run_compacts_logs_by_default():
    """Default verbose=False compacts via _log_compact; the response carries
    log_lines_dropped: int when filtering happened."""
    scene_path = os.path.join(PROJECT_ROOT, "archiv", "cantilever_beam.py")
    result = probes.enable_logs_and_run(
        scene_path=scene_path,
        log_targets=["EulerImplicitSolver"],
        steps=3,
    )
    assert result["success"] is True
    # printLog generates lots of lines; expect non-trivial drop count
    assert result.get("log_lines_dropped", 0) > 0, (
        "expected compact_log to filter at least one line of printLog output"
    )
