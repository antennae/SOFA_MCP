"""§6.A.3 trigger: a 50mm beam with no fixed boundary falls freely under
gravity (9810 mm/s²). After ~5 steps at dt=0.1s, the beam drops far past
its own length — displacement / extent ≥ 10× (warning), well below the
100× error threshold. Stays numerically clean (no NaN).
"""
import Sofa


def createScene(node):
    node.gravity = [0, -9810, 0]
    node.dt = 0.1

    node.addObject('RequiredPlugin', name='Sofa.Component.AnimationLoop')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Lagrangian.Correction')
    node.addObject('RequiredPlugin', name='Sofa.Component.Constraint.Lagrangian.Solver')
    node.addObject('RequiredPlugin', name='Sofa.Component.LinearSolver.Direct')
    node.addObject('RequiredPlugin', name='Sofa.Component.Mass')
    node.addObject('RequiredPlugin', name='Sofa.Component.ODESolver.Backward')
    node.addObject('RequiredPlugin', name='Sofa.Component.SolidMechanics.FEM.Elastic')
    node.addObject('RequiredPlugin', name='Sofa.Component.StateContainer')
    node.addObject('RequiredPlugin', name='Sofa.Component.Topology.Container.Grid')

    node.addObject('FreeMotionAnimationLoop')
    node.addObject('NNCGConstraintSolver')

    beam = node.addChild('falling_beam')
    beam.addObject('EulerImplicitSolver')
    beam.addObject('SparseLDLSolver', template='CompressedRowSparseMatrixd')
    beam.addObject('GenericConstraintCorrection')
    beam.addObject('RegularGridTopology', name='grid', min=[-2, -2, 0], max=[2, 2, 50], n=[3, 3, 11])
    beam.addObject('MechanicalObject', name='mo', template='Vec3d')
    beam.addObject('UniformMass', totalMass=0.8)
    beam.addObject('TetrahedronFEMForceField', youngModulus=1e5, poissonRatio=0.3, method='large')
    # Deliberately NO FixedProjectiveConstraint — beam free-falls indefinitely.
