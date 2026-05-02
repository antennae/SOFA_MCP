"""M5 fixture 2 — Units mismatch.

Gravity is mm/g/s magnitude (-9810) but youngModulus is at the SI-Pa
'rubber/steel' scale (5e9). Rule 9 fires at warning severity per
_summary_runtime_template.py:check_rule_9_units (gmag≈9810 → mm/g/s →
ym>1e9 suspicious).

Used by test_diagnose_e2e.py and the manual M5 checklist.
"""

import Sofa
import Sofa.Core


def createScene(root_node):
    root_node.gravity = [0, -9810, 0]  # mm/g/s magnitude
    root_node.addObject("RequiredPlugin", name="Sofa.Component.ODESolver.Backward")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Direct")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.StateContainer")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Mass")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.FEM.Elastic")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Grid")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")

    root_node.addObject("DefaultAnimationLoop")
    body = root_node.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("RegularGridTopology", min=[0, 0, 0], max=[10, 10, 10], n=[3, 3, 3])
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    # The bug: youngModulus=5e9 reads as steel in mm/g/s, not the kPa rubber the user meant.
    body.addObject("TetrahedronFEMForceField", poissonRatio=0.3, youngModulus=5e9)

    return root_node
