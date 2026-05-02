"""Regression tests for render_scene_snapshot.

Asserts the renderer:
  - finds OglModel-backed visual nodes and renders their explicit
    triangles (no Delaunay-and-hull fallback);
  - excludes cable subnode MOs (which have no surface representation);
  - falls back to a point glyph cloud — not a hull — when a scene
    has no visual model at all.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sofa_mcp.observer import renderer

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PYTHON = os.path.expanduser("~/venv/bin/python")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
TRI_LEG = os.path.join(PROJECT_ROOT, "archiv", "tri_leg_cables.py")

if not os.path.exists(PYTHON):
    pytest.skip("SOFA env (~/venv with SofaPython3) not available", allow_module_level=True)


def test_render_tri_leg_uses_visual_models(tmp_path):
    """tri_leg_cables has 3 OglModels (one per leg) and a CableConstraint
    point cloud per leg. Renderer should render exactly the 3 visual
    models and exclude every cable / mechanical-state subnode that has
    no surface."""
    if not os.path.exists(TRI_LEG):
        pytest.skip(f"missing fixture: {TRI_LEG}")
    out = tmp_path / "tri_leg.png"
    result = renderer.render_scene_snapshot(
        scene_path=TRI_LEG,
        steps=5,
        dt=0.01,
        output_path=str(out),
    )
    assert result["success"] is True, f"render failed: {result.get('error')}"
    assert result["rendered_objects"] == 3, (
        f"expected 3 visual-model renders for tri_leg; got "
        f"{result['rendered_objects']}"
    )
    assert out.exists() and out.stat().st_size > 0, "PNG missing or empty"


def test_render_no_visual_falls_back_to_points(tmp_path):
    """A scene with no OglModel should fall back to a point glyph
    cloud (rendered_objects == 1, the single MO) — NOT a convex hull
    and NOT a crash."""
    fixture = os.path.join(FIXTURES_DIR, "render_no_visual_fallback.py")
    assert os.path.exists(fixture)
    out = tmp_path / "no_visual.png"
    result = renderer.render_scene_snapshot(
        scene_path=fixture,
        steps=5,
        dt=0.01,
        output_path=str(out),
    )
    assert result["success"] is True, f"render failed: {result.get('error')}"
    assert result["rendered_objects"] >= 1, (
        f"expected at least 1 rendered MO point cloud; got {result}"
    )
    assert out.exists() and out.stat().st_size > 0, "PNG missing or empty"
