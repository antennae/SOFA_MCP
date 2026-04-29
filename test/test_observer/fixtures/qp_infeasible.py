"""Genuinely-infeasible QP via inverted bounds: minForce > maxForce on the
CableActuator gives lambda lower bound > upper bound, which qpOASES rejects."""
import Sofa


def createScene(node):
    node.gravity = [0, 0, 0]
    node.dt = 0.01

    node.addObject('RequiredPlugin', name='Sofa.Component.AnimationLoop')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Lagrangian.Correction')
    node.addObject('RequiredPlugin', name='Sofa.Component.LinearSolver.Direct')
    node.addObject('RequiredPlugin', name='Sofa.Component.Mass')
    node.addObject('RequiredPlugin', name='Sofa.Component.ODESolver.Backward')
    node.addObject('RequiredPlugin', name='Sofa.Component.SolidMechanics.FEM.Elastic')
    node.addObject('RequiredPlugin', name='Sofa.Component.StateContainer')
    node.addObject('RequiredPlugin', name='Sofa.Component.Topology.Container.Grid')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Projective')
    node.addObject('RequiredPlugin', name='Sofa.Component.Engine.Select')
    node.addObject('RequiredPlugin', name='Sofa.Component.Mapping.Linear')
    node.addObject('RequiredPlugin', name='SoftRobots')
    node.addObject('RequiredPlugin', name='SoftRobots.Inverse')

    node.addObject('FreeMotionAnimationLoop')
    node.addObject('QPInverseProblemSolver', actuatorsOnly=False)

    beam = node.addChild('beam')
    beam.addObject('EulerImplicitSolver')
    beam.addObject('SparseLDLSolver', template='CompressedRowSparseMatrixd')
    beam.addObject('GenericConstraintCorrection')
    beam.addObject('RegularGridTopology', name='grid', min=[-2, -2, 0], max=[2, 2, 50], n=[3, 3, 11])
    beam.addObject('MechanicalObject', name='mo', template='Vec3d')
    beam.addObject('UniformMass', totalMass=0.8)
    beam.addObject('TetrahedronFEMForceField', youngModulus=1e5, poissonRatio=0.3, method='large')
    beam.addObject('BoxROI', name='fixedbox', box=[-2.1, -2.1, -0.1, 2.1, 2.1, 0.1])
    beam.addObject('FixedProjectiveConstraint', indices='@fixedbox.indices')

    cables = beam.addChild('cables')
    cables.addObject('MechanicalObject', name='cableMO', position=[[0, 0, 50], [0, 0, 25]])
    # Inverted bounds: lambda must be in [100, -100], which is empty.
    cables.addObject('CableActuator', name='cable', indices=[0, 1],
                     pullPoint=[0, 0, 0], minForce=100, maxForce=-100)
    cables.addObject('BarycentricMapping', mapForces=False, mapMasses=False)

    eff = beam.addChild('effector')
    eff.addObject('MechanicalObject', name='effMO', position=[[0, 0, 50]])
    eff.addObject('PositionEffector', indices=[0], effectorGoal=[10.0, 0, 50])
    eff.addObject('BarycentricMapping', mapForces=False, mapMasses=False)
