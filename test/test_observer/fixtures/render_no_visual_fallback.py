"""Renderer fallback fixture — deformable body with NO OglModel.

A 5x3x3 grid cantilever. Has a MechanicalObject and topology but no
OglModel/VisualModelImpl. The renderer should fall back to a point
glyph cloud, not a hull or a crash.
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
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Projective")

    root_node.addObject("DefaultAnimationLoop")
    body = root_node.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("RegularGridTopology", min=[0, 0, 0], max=[10, 5, 5], n=[5, 3, 3])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=0.5)
    body.addObject("TetrahedronFEMForceField", poissonRatio=0.3, youngModulus=3000)
    body.addObject("FixedProjectiveConstraint", indices=[0, 1, 2, 3, 4, 5, 6, 7, 8])

    return root_node
