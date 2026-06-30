"""Fixture for diagnose_scene env-passthrough test.

Branches on the SOFA_MCP_TEST_MARKER environment variable: when set to "on",
an extra child node is added. This lets a test assert that diagnose_scene's
`env` override actually reaches the subprocess (node_count differs), and that
the override is *merged* over the parent environment (SOFA still imports, so
the scene runs at all).
"""
import os


def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    for p in (
        "Sofa.Component.AnimationLoop",
        "Sofa.Component.ODESolver.Backward",
        "Sofa.Component.LinearSolver.Direct",
        "Sofa.Component.StateContainer",
        "Sofa.Component.Topology.Container.Grid",
        "Sofa.Component.Mass",
        "Sofa.Component.SolidMechanics.FEM.Elastic",
    ):
        rootNode.addObject("RequiredPlugin", name=p)
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("RegularGridTopology", n=[3, 3, 3], min=[0, 0, 0], max=[10, 10, 10])
    body.addObject("MechanicalObject", name="mo", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("HexahedronFEMForceField", youngModulus=1000, poissonRatio=0.3)
    # Env-driven variant: the extra node appears only when the marker is set.
    if os.environ.get("SOFA_MCP_TEST_MARKER") == "on":
        body.addChild("env_marker_node")
