"""M5 fixture 4 — Broken Barycentric mapping.

A child node has a BarycentricMapping whose parent has only a bare
MeshTopology (no filename, no loader sibling, no shell FEM). Per
_summary_runtime_template.py:_node_is_volumetric the parent is not
considered volumetric, so rule_7_topology fires at error severity for
the BarycentricMapping in 7B.

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
    root_node.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Constant")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Mapping.Linear")

    root_node.addObject("DefaultAnimationLoop")

    parent = root_node.addChild("parent")
    parent.addObject("EulerImplicitSolver")
    parent.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    # The bug: bare MeshTopology with no filename + no loader sibling.
    # _resolve_topology_filename returns None; node not marked volumetric.
    parent.addObject("MeshTopology")
    parent.addObject("MechanicalObject", template="Vec3d", position=[[0, 0, 0]])
    parent.addObject("UniformMass", totalMass=1.0)

    child = parent.addChild("child")
    child.addObject("MechanicalObject", template="Vec3d", position=[[0, 0, 0]])
    # BarycentricMapping with non-volumetric parent + no shell-FEM exemption.
    child.addObject("BarycentricMapping")

    return root_node
