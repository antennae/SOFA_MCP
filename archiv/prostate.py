import Sofa
import Sofa.Core

def createScene(rootNode):
    # Plugins
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.IO.Mesh")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Dynamic")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.StateContainer")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.FEM.Elastic")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Projective")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.ODESolver.Backward")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Direct")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Lagrangian.Correction")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Lagrangian.Solver")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Visual")
    rootNode.addObject("RequiredPlugin", name="Sofa.GL.Component.Rendering3D")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Engine.Select")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Mapping.Linear")

    rootNode.addObject("VisualStyle", displayFlags="showBehaviorModels showVisualModels showForceFields")
    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("NNCGConstraintSolver", tolerance=1e-5, maxIterations=50)

    # Prostate node
    prostateNode = rootNode.addChild("prostate")
    prostateNode.addObject("EulerImplicitSolver", rayleighStiffness=0.1, rayleighMass=0.1)
    prostateNode.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")

    prostateNode.addObject("MeshVTKLoader", name="loader", filename="meshes/prostate.vtk")
    prostateNode.addObject("TetrahedronSetTopologyContainer", name="container", src="@loader")
    prostateNode.addObject("TetrahedronSetTopologyModifier")
    prostateNode.addObject("TetrahedronSetGeometryAlgorithms", template="Vec3d")
    
    prostateNode.addObject("MechanicalObject", name="mo", template="Vec3d", src="@loader")
    prostateNode.addObject("TetrahedronFEMForceField", name="fem", youngModulus=5000, poissonRatio=0.45, method="large")
    
    # Boundary condition: fix at the bottom (z_min = -18.16)
    prostateNode.addObject("BoxROI", name="box_roi", box=[-20, -20, -18.2, 22, 15, -17.5], drawBoxes=True)
    prostateNode.addObject("FixedProjectiveConstraint", indices="@box_roi.indices")
    
    # Visual model
    visualNode = prostateNode.addChild("visual")
    visualNode.addObject("OglModel", name="visualModel", src="@../loader", color=[0.8, 0.4, 0.4, 0.8])
    visualNode.addObject("BarycentricMapping")
    
    prostateNode.addObject("GenericConstraintCorrection")
