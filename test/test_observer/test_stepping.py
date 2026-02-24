import pytest
import sys
import os
# Add the sofa_mcp path to the test
# This allows running the test script from the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sofa_mcp.observer import stepping

@pytest.fixture
def scene_path(tmp_path):
    scene_file = tmp_path / "test_scene.py"
    scene_content = """
import Sofa.Core

def createScene(rootNode):
    # Add header components
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.AnimationLoop")
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.Constraint.Lagrangian.Solver")
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.ODESolver.Backward")
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.LinearSolver.Direct")
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.Constraint.Lagrangian.Correction")
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.Mass")
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.MechanicalLoad")
    rootNode.addObject("FreeMotionAnimationLoop", name="AnimationLoop")
    rootNode.addObject("NNCGConstraintSolver", name="ConstraintSolver")

    # Add solver components under a child node as per architecture reference
    solver_node = rootNode.addChild("solver_node")
    solver_node.addObject("EulerImplicitSolver", firstOrder=False)
    solver_node.addObject("SparseLDLSolver", name="Solver", template="CompressedRowSparseMatrixMat3x3d", parallelInverseProduct=True)
    solver_node.addObject("GenericConstraintCorrection", name="ConstraintCorrection")

    mechanics = solver_node.addChild('mechanics') # Changed to be a child of solver_node to match expected structure
    mo = mechanics.addObject('MechanicalObject', name='mo', template='Vec3d', position=[0, 0, 0])
    mechanics.addObject('ConstantForceField', name='force', forces=[0, 1, 0])
    mechanics.addObject('UniformMass', totalMass=1.0)
    return rootNode
"""
    scene_file.write_text(scene_content)
    yield str(scene_file)

def test_run_and_extract_success(scene_path):
    steps = 3
    dt = 0.01
    node_path = "solver_node/mechanics/mo"
    field = "position"

    result = stepping.run_and_extract(scene_path, steps, dt, node_path, field)

    assert result["success"]
    assert "data" in result
    assert len(result["data"]) == steps

    # Check that the position has changed from the initial position for each step.
    initial_pos = [[0.0, 0.0, 0.0]]
    for pos in result["data"]:
        assert pos != initial_pos
        assert len(pos[0]) == 3

def test_run_and_extract_invalid_node(scene_path):
    steps = 1
    dt = 0.01
    node_path = "invalid_node/mo"
    field = "position"

    result = stepping.run_and_extract(scene_path, steps, dt, node_path, field)
    assert not result["success"]
    assert "error" in result
    assert "Node not found" in result["error"]

def test_run_and_extract_invalid_field(scene_path):
    steps = 1
    dt = 0.01
    node_path = "solver_node/mechanics/mo"
    field = "invalid_field"

    result = stepping.run_and_extract(scene_path, steps, dt, node_path, field)
    assert not result["success"]
    assert "error" in result
    assert "Data field 'invalid_field' not found" in result["error"]
