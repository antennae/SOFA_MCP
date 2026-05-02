"""Tri-leg cable-actuated robot solving an inverse-position problem.

Each of three legs has:
  - CableActuator pulling its tip toward a common pullPoint (above the
    structure)
  - PositionEffector tracking the leg's tip MO toward a per-leg goal
  - QPInverseProblemSolver finds the cable forces that move each tip
    toward its goal

This is the headline portfolio demo: open the rendered PNG and see
three legs reaching three asymmetrically-placed targets.
"""

import Sofa
import Sofa.Core
import math


def createScene(root_node):
    root_node.addObject("RequiredPlugin", name="Sofa.Component.ODESolver.Backward")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Direct")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Iterative")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.StateContainer")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Mass")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.FEM.Elastic")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Grid")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Lagrangian.Correction")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Projective")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Visual")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Mapping.Linear")
    root_node.addObject("RequiredPlugin", name="Sofa.GL.Component.Rendering3D")
    root_node.addObject("RequiredPlugin", name="SoftRobots")
    root_node.addObject("RequiredPlugin", name="SoftRobots.Inverse")

    root_node.addObject("VisualStyle", displayFlags="showBehavior showVisual")
    root_node.addObject("FreeMotionAnimationLoop")
    root_node.addObject("QPInverseProblemSolver", epsilon=1e-3, printLog=False)

    common_pull_point = [0, 0, 150]
    radius = 30.0
    leg_centers = [
        [radius * math.cos(0),               radius * math.sin(0),               0],
        [radius * math.cos(2 * math.pi / 3), radius * math.sin(2 * math.pi / 3), 0],
        [radius * math.cos(4 * math.pi / 3), radius * math.sin(4 * math.pi / 3), 0],
    ]
    leg_height = 100.0
    leg_width = 10.0

    inward_offsets = [25.0, 18.0, 12.0]
    colors = [
        [0.85, 0.30, 0.30, 1.0],
        [0.30, 0.75, 0.30, 1.0],
        [0.30, 0.45, 0.85, 1.0],
    ]

    for i, center in enumerate(leg_centers):
        x, y, z = center

        goal = root_node.addChild(f"goal_{i}")
        goal.addObject("EulerImplicitSolver", firstOrder=True)
        goal.addObject("CGLinearSolver", iterations=100, tolerance=1e-5, threshold=1e-5)
        norm = math.hypot(x, y) or 1.0
        goal_pos = [x * (1.0 - inward_offsets[i] / norm),
                    y * (1.0 - inward_offsets[i] / norm),
                    leg_height]
        goal.addObject("MechanicalObject", name="goalMO",
                       position=[goal_pos], showObject=True, showObjectScale=3.0)
        goal.addObject("UncoupledConstraintCorrection")

        leg = root_node.addChild(f"Leg_{i}")
        leg.addObject("EulerImplicitSolver")
        leg.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")

        w = leg_width / 2.0
        leg.addObject("RegularGridTopology",
                      min=[x - w, y - w, 0],
                      max=[x + w, y + w, leg_height],
                      n=[2, 2, 11])
        leg.addObject("MechanicalObject", template="Vec3d", name="mo")
        leg.addObject("UniformMass", totalMass=0.5)
        leg.addObject("TetrahedronFEMForceField", poissonRatio=0.3, youngModulus=5000)
        leg.addObject("FixedProjectiveConstraint", indices=[0, 1, 2, 3])
        leg.addObject("GenericConstraintCorrection")

        eff = leg.addChild("effector")
        eff.addObject("MechanicalObject", name="effMO",
                      position=[[x, y, leg_height]])
        eff.addObject("PositionEffector",
                      indices=[0],
                      effectorGoal=f"@../../goal_{i}/goalMO.position")
        eff.addObject("BarycentricMapping")

        leg.addObject("CableActuator",
                      name=f"cable_{i}",
                      indices=[40, 41, 42, 43],
                      pullPoint=common_pull_point,
                      maxPositiveDisp=40.0,
                      minForce=0)

        visu = leg.addChild("Visual")
        visu.addObject("OglModel", name="VisualModel", color=colors[i])
        visu.addObject("IdentityMapping", input="@../mo", output="@VisualModel")

    return root_node
