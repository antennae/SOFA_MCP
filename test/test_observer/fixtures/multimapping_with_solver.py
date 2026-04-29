"""§6.C.1 trigger fixture: a node with both a *MultiMapping and an ODE
solver in its `objects`. SOFA's MechanicalIntegration visitor detaches the
output DoFs from the parent integration when a MultiMapping is present, so
co-locating an ODE solver is an anti-pattern.

Two parent FEM beams; a child node concatenates their DoFs via
SubsetMultiMapping AND carries an EulerImplicitSolver — the trigger.
The scene is built so init() succeeds (the visitor warns but doesn't
abort), giving the runner a chance to populate the rest of the payload.
"""
import Sofa


def _add_beam(parent, name, x_offset):
    beam = parent.addChild(name)
    beam.addObject('EulerImplicitSolver')
    beam.addObject('SparseLDLSolver', template='CompressedRowSparseMatrixd')
    beam.addObject('GenericConstraintCorrection')
    beam.addObject('RegularGridTopology', name='grid',
                   min=[x_offset, -2, 0], max=[x_offset + 4, 2, 50], n=[3, 3, 11])
    beam.addObject('MechanicalObject', name='mo', template='Vec3d')
    beam.addObject('UniformMass', totalMass=0.4)
    beam.addObject('TetrahedronFEMForceField', youngModulus=1e5, poissonRatio=0.3, method='large')
    beam.addObject('BoxROI', name='fixedbox',
                   box=[x_offset - 0.1, -2.1, -0.1, x_offset + 4.1, 2.1, 0.1])
    beam.addObject('FixedProjectiveConstraint', indices='@fixedbox.indices')
    return beam


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

    node.addObject('FreeMotionAnimationLoop')
    node.addObject('NNCGConstraintSolver')

    a = _add_beam(node, 'a', x_offset=-10)
    b = _add_beam(node, 'b', x_offset=10)

    # Trigger node: SubsetMultiMapping AND EulerImplicitSolver in the same
    # `objects` list.
    combined = node.addChild('combined')
    combined.addObject('EulerImplicitSolver')
    combined.addObject('MechanicalObject', name='combinedMO', template='Vec3d')
    combined.addObject('SubsetMultiMapping',
                       input=['@/a/mo', '@/b/mo'],
                       output='@combinedMO',
                       indexPairs=[0, 0, 1, 0])
