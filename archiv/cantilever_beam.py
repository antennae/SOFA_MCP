import Sofa

def createScene(node):
    # Scene settings
    node.gravity = [0, -9810, 0] # mm/s^2
    node.dt = 0.01

    # Required Plugins
    node.addObject('RequiredPlugin', name='Sofa.Component.ODESolver.Backward')
    node.addObject('RequiredPlugin', name='Sofa.Component.LinearSolver.Direct')
    node.addObject('RequiredPlugin', name='Sofa.Component.Topology.Container.Grid')
    node.addObject('RequiredPlugin', name='Sofa.Component.StateContainer')
    node.addObject('RequiredPlugin', name='Sofa.Component.SolidMechanics.FEM.Elastic')
    node.addObject('RequiredPlugin', name='Sofa.Component.Engine.Select')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Projective')
    node.addObject('RequiredPlugin', name='Sofa.Component.Mass')
    node.addObject('RequiredPlugin', name='Sofa.Component.Visual')
    node.addObject('RequiredPlugin', name='Sofa.Component.AnimationLoop')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Lagrangian.Solver')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Lagrangian.Correction')

    # Visual and Global components
    node.addObject('VisualStyle', displayFlags='showBehavior showBehaviorModels')
    node.addObject('FreeMotionAnimationLoop')
    node.addObject('NNCGConstraintSolver')

    # Beam simulation node
    beam = node.addChild('beam')
    beam.addObject('EulerImplicitSolver', name='odesolver')
    beam.addObject('SparseLDLSolver', name='linearsolver')

    # Topology and State
    # Dimensions: 4x4x50mm, centered on X and Y, length along Z
    beam.addObject('RegularGridTopology', name='grid', min=[-2, -2, 0], max=[2, 2, 50], n=[3, 3, 20])
    beam.addObject('MechanicalObject', name='mo', template='Vec3d')
    beam.addObject('UniformMass', totalMass=0.8) # g
    
    # Physics - Hexahedral FEM
    beam.addObject('HexahedronFEMForceField', name='FEM', youngModulus=349271, poissonRatio=0.45, method='large')

    # Boundary Condition - Fixed at z=0
    beam.addObject('BoxROI', name='box', box=[-2.1, -2.1, -0.1, 2.1, 2.1, 0.1])
    beam.addObject('FixedProjectiveConstraint', indices='@box.indices')

    # Constraint Correction
    beam.addObject('GenericConstraintCorrection')

    return node
