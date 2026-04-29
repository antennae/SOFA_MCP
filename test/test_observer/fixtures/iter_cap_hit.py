"""§6.A.6 trigger: NNCGConstraintSolver with `maxIterations=2`. The
CableConstraint creates Lagrangian constraints that the NNCG solver iterates
to satisfy; the tight cap forces every step to hit it.
"""
import Sofa


def createScene(node):
    node.gravity = [0, -9810, 0]
    node.dt = 0.01

    node.addObject('RequiredPlugin', name='Sofa.Component.AnimationLoop')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Lagrangian.Correction')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Lagrangian.Solver')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Projective')
    node.addObject('RequiredPlugin', name='Sofa.Component.Engine.Select')
    node.addObject('RequiredPlugin', name='Sofa.Component.LinearSolver.Direct')
    node.addObject('RequiredPlugin', name='Sofa.Component.Mapping.Linear')
    node.addObject('RequiredPlugin', name='Sofa.Component.Mass')
    node.addObject('RequiredPlugin', name='Sofa.Component.ODESolver.Backward')
    node.addObject('RequiredPlugin', name='Sofa.Component.SolidMechanics.FEM.Elastic')
    node.addObject('RequiredPlugin', name='Sofa.Component.StateContainer')
    node.addObject('RequiredPlugin', name='Sofa.Component.Topology.Container.Grid')
    node.addObject('RequiredPlugin', name='SoftRobots')

    node.addObject('FreeMotionAnimationLoop')
    # Tight cap: NNCG hits its iteration cap on every step. tolerance is
    # tightened so the solver doesn't bail early on convergence.
    node.addObject('NNCGConstraintSolver', maxIterations=2, tolerance=1e-12)

    leg = node.addChild('leg')
    leg.addObject('EulerImplicitSolver')
    leg.addObject('SparseLDLSolver', template='CompressedRowSparseMatrixd')
    leg.addObject('GenericConstraintCorrection')
    leg.addObject('RegularGridTopology', name='grid',
                  min=[-5, -5, 0], max=[5, 5, 100], n=[2, 2, 11])
    leg.addObject('MechanicalObject', template='Vec3d', name='mo')
    leg.addObject('UniformMass', totalMass=0.5)
    leg.addObject('TetrahedronFEMForceField', poissonRatio=0.3, youngModulus=5000)
    leg.addObject('FixedProjectiveConstraint', indices=[0, 1, 2, 3])

    leg.addObject('CableConstraint', name='cable',
                  indices=[40, 41, 42, 43],
                  pullPoint=[0, 0, 150],
                  maxPositiveDisp=30.0, minForce=0,
                  valueType='displacement', value=20.0)
