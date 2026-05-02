"""M5 fixture 3 — Missing collision pipeline.

Scene has a TriangleCollisionModel on a meshed body, but the root is
missing the 5-cluster collision pipeline (CollisionPipeline /
BruteForceBroadPhase / BVHNarrowPhase / MinProximityIntersection /
CollisionResponse). Rule 8 fires at error severity.

Used by test_diagnose_e2e.py and the manual M5 checklist.
"""

import Sofa
import Sofa.Core


def createScene(root_node):
    root_node.gravity = [0, -9.81, 0]
    root_node.addObject("RequiredPlugin", name="Sofa.Component.ODESolver.Backward")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Direct")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.StateContainer")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Mass")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.FEM.Elastic")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Grid")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Collision.Geometry")

    root_node.addObject("DefaultAnimationLoop")
    body = root_node.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("RegularGridTopology", min=[0, 0, 0], max=[10, 10, 10], n=[3, 3, 3])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("TetrahedronFEMForceField", poissonRatio=0.3, youngModulus=1000)
    # The bug: TriangleCollisionModel here, but no pipeline at root.
    body.addObject("TriangleCollisionModel")

    return root_node
