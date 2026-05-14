import Sofa
import Sofa.Core
import math

def createScene(root_node):
    # Required Plugins
    root_node.addObject("RequiredPlugin", name="Sofa.Component.ODESolver.Backward")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Direct")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.StateContainer")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Mass")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Engine.Select")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.FEM.Elastic")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Grid")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Lagrangian.Solver")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Lagrangian.Correction")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Projective")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Visual")
    root_node.addObject("RequiredPlugin", name="Sofa.Component.Mapping.Linear")
    root_node.addObject("RequiredPlugin", name="Sofa.GL.Component.Rendering3D")
    root_node.addObject("RequiredPlugin", name="SoftRobots")

    # Basic Setup
    root_node.addObject("VisualStyle", displayFlags="showBehavior showBehaviorModels")
    root_node.addObject("FreeMotionAnimationLoop")
    root_node.addObject("NNCGConstraintSolver", tolerance=1e-5, maxIterations=50)

    common_start_point = [0, 0, 150] 
    # 3 legs in a triangular layout around the center
    radius = 30.0
    leg_centers = [
        [radius * math.cos(0), radius * math.sin(0), 0],
        [radius * math.cos(2*math.pi/3), radius * math.sin(2*math.pi/3), 0],
        [radius * math.cos(4*math.pi/3), radius * math.sin(4*math.pi/3), 0]
    ]
    leg_height = 100.0
    leg_width = 10.0

    colors = [
        [1, 0, 0, 1], # Red
        [0, 1, 0, 1], # Green
        [0, 0, 1, 1]  # Blue
    ]
    cable_displacements = [22.0, 12.0, 5.0]  # mm of contraction per leg, asymmetric for a clearer demo

    for i, center in enumerate(leg_centers):
        leg_node = root_node.addChild(f"Leg_{i}")
        leg_node.addObject("EulerImplicitSolver")
        leg_node.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")

        x, y, z = center
        w = leg_width / 2.0
        leg_node.addObject("RegularGridTopology",
                           min=[x-w, y-w, 0],
                           max=[x+w, y+w, leg_height],
                           n=[2, 2, 11])

        leg_mo = leg_node.addObject("MechanicalObject", template="Vec3d", name="mo")
        leg_node.addObject("UniformMass", totalMass=0.5)
        leg_node.addObject("TetrahedronFEMForceField", poissonRatio=0.3, youngModulus=5000)

        # Fix the base
        leg_node.addObject("FixedProjectiveConstraint", indices=[0, 1, 2, 3])

        # Cable Actuator (using CableConstraint for forward simulation)
        tip_indices = [40, 41, 42, 43]
        leg_node.addObject("CableConstraint",
                           name=f"cable_{i}",
                           indices=tip_indices,
                           pullPoint=common_start_point,
                           maxPositiveDisp=30.0,
                           minForce=0,
                           valueType="displacement",
                           value=cable_displacements[i],
                           color=colors[i])

        # Visual model
        visu_node = leg_node.addChild("Visual")
        visu_node.addObject("OglModel", name="VisualModel", color=colors[i])
        visu_node.addObject("IdentityMapping", input="@../mo", output="@VisualModel")

        leg_node.addObject("GenericConstraintCorrection")

    return root_node

def add_scene_content(parent_node):
    return createScene(parent_node)
