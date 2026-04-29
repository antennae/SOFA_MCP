# SOFA component alternatives — registered classes by category

Quick reference for picking alternatives when SKILL.md's recommended default doesn't fit. All classes verified registered in this build (SOFA v24.12 + SoftRobots + SoftRobots.Inverse + Cosserat). For anything not listed here, use `search_sofa_components('keyword')` for live discovery.

## Animation loops

| Class | Use case |
|---|---|
| `FreeMotionAnimationLoop` | Lagrangian constraints, soft-robot actuators (recommended for any constraint scene) |
| `DefaultAnimationLoop` | core built-in; constraint-free scenes |
| `ConstraintAnimationLoop` | deprecated upstream — prefer `FreeMotion` |
| `MultiStepAnimationLoop` | sub-stepping per frame |
| `MultiTagAnimationLoop` | scene-graph partitioning by tag |

## Time integrators (ODE solvers)

| Class | Type | Use case |
|---|---|---|
| `EulerImplicitSolver` | implicit | recommended default (~88% of upstream) |
| `EulerExplicitSolver` | explicit | explicit dynamics with bounded stiffness |
| `RungeKutta2Solver` / `RungeKutta4Solver` | explicit | higher-order explicit |
| `NewmarkImplicitSolver` | implicit | Newmark scheme |
| `BDFOdeSolver` | implicit | backward differentiation |
| `NewtonRaphsonSolver` | implicit | iterative Newton refinement |
| `StaticSolver` | implicit | quasi-statics (no inertia) |
| `VariationalSymplecticSolver` | implicit | energy-conserving |
| `CentralDifferenceSolver` | explicit | central difference scheme |

## Linear solvers

| Class | Direct/Iterative | Use case |
|---|---|---|
| `SparseLDLSolver` (with `template="CompressedRowSparseMatrixMat3x3d"`) | direct | recommended default for FEM |
| `AsyncSparseLDLSolver` | direct | async variant |
| `EigenSimplicialLDLT` | direct | Eigen-backed |
| `CholeskySolver` | direct | dense Cholesky |
| `SVDLinearSolver` | direct | rank-deficient or singular systems |
| `BTDLinearSolver` | direct | block tridiagonal (beam/cable) |
| `CGLinearSolver` | iterative | very large systems; backup for SparseLDL |
| `PCGLinearSolver` / `ParallelCGLinearSolver` | iterative | preconditioned CG |
| `MinResLinearSolver` | iterative | symmetric indefinite |
| `PrecomputedLinearSolver` | direct | static system, factorize once |

**Not registered in this build:** `SparseDirectSolver`, `SparseLUSolver`, `SparseCholeskySolver`.

## Constraint solvers (root, under `FreeMotionAnimationLoop`)

| Class | Use case |
|---|---|
| `NNCGConstraintSolver` | forward soft-robotics (project default) |
| `QPInverseProblemSolver` | required for any `SoftRobots.Inverse` scene |
| `LCPConstraintSolver` | classical LCP |
| `BlockGaussSeidelConstraintSolver` | block Gauss-Seidel |
| `ImprovedJacobiConstraintSolver` | parallel Jacobi |
| `UnbuiltGaussSeidelConstraintSolver` | matrix-free GS |

## Constraint corrections (one per deformable subtree)

| Class | Use case |
|---|---|
| `GenericConstraintCorrection` | safe default; requires `linearSolver` + `ODESolver` links |
| `LinearSolverConstraintCorrection` | cable/wire scenes; set `wire_optimization=1` |
| `UncoupledConstraintCorrection` | rigid bodies; per-DoF compliance |
| `PrecomputedConstraintCorrection` | precomputed compliance matrix |

## Topology containers

| Class | Element type |
|---|---|
| `TetrahedronSetTopologyContainer` | volumetric tetra |
| `HexahedronSetTopologyContainer` | volumetric hexa |
| `TriangleSetTopologyContainer` | surface triangles |
| `QuadSetTopologyContainer` | surface quads |
| `EdgeSetTopologyContainer` | edges (beams, cables) |
| `MeshTopology` | generic; safe as volumetric only when loaded from `.msh`/`.vtk`/`.vtu` |
| `RegularGridTopology` / `SparseGridTopology` | structured grid; must be 3D to count as volumetric |

## FEM force fields — high Poisson ratio

For near-incompressible materials (high Poisson ratio approaching 0.5 — biological tissue, gel, rubber, soft elastomers), `TetrahedronFEMForceField` (linear tet FEM) can suffer from volumetric locking: the simulation runs but the apparent stiffness comes out wrong, and the symptom is "deformation smaller than expected" without any error. Severity depends on mesh density and is usually mild for typical soft-robot silicones, becoming pronounced only as ν gets close to incompressible. If locking is suspected, switch to `TetrahedronHyperelasticityFEMForceField`. Hexahedral elements (`HexahedronFEMForceField`) lock less by construction.

## Mass

| Class | Use case |
|---|---|
| `UniformMass` | rigid bodies; quick-prototype FEM (most common upstream) |
| `DiagonalMass` | speed > accuracy |
| `MeshMatrixMass` | physically correct for FEM |

## Mappings (commonly used)

| Class | Use case |
|---|---|
| `IdentityMapping` | parent and child have same DoFs |
| `BarycentricMapping` | volumetric → surface (parent must be volumetric, except for shell FEM) |
| `RigidMapping` | rigid → deformable child |
| `SkinningMapping` | weighted skinning |
| `SubsetMultiMapping` | concatenate parts of multiple parent MOs |
| `IdentityMultiMapping` | concatenate identical MOs |
| `CenterOfMassMultiMapping` | center-of-mass aggregation |
| `DistanceMultiMapping` | distance-based |

**Important:** any node containing a `*MultiMapping` must NOT carry its own ODE solver — the solver detaches the output DoFs from the parent integration.

## Visual models (concrete)

| Class | Notes |
|---|---|
| `OglModel` | canonical for OpenGL rendering |
| `VisualModelImpl` | base implementation; `addObject("VisualModel")` aliases to this |
| `CylinderVisualModel` | cylinder primitive |
| `VisualMesh` | generic mesh |
| `OglShaderVisualModel` | custom shader |

## Collision pipeline — full alternatives

### Broad phase
| Class | Notes |
|---|---|
| `BruteForceBroadPhase` | recommended default |
| `ParallelBruteForceBroadPhase` | parallel variant |
| `IncrSAP` / `DirectSAP` | sweep-and-prune |

### Narrow phase
| Class | Notes |
|---|---|
| `BVHNarrowPhase` | recommended default |
| `ParallelBVHNarrowPhase` | parallel variant |

### Intersection methods
| Class | Notes |
|---|---|
| `MinProximityIntersection` | recommended default |
| `LocalMinDistance` | tighter contact distance |
| `NewProximityIntersection` | newer variant |
| `CCDTightInclusionIntersection` | continuous collision detection |
| `DiscreteIntersection` | runtime auto-fallback if missing |

### Contact managers
| Class | Notes |
|---|---|
| `CollisionResponse` | recommended default |
| `RuleBasedContactManager` | subclass; per-pair response selection |

### Bullet alternative
Loading `RequiredPlugin BulletCollisionDetection` provides its own broad+narrow phase implementation; coexists with `CollisionPipeline` and replaces the default broad/narrow.

## Inverse-problem components (`SoftRobots.Inverse` plugin)

Any of these classes in a scene requires `QPInverseProblemSolver` at root.

- **Actuators**: `CableActuator`, `SurfacePressureActuator`, `ForcePointActuator`, `ForceSurfaceActuator`, `JointActuator`, `SlidingActuator`, `SlidingForceActuator`, `SmoothSlidingForceActuator`, `SphericalSlidingForceActuator`, `AreaContactSlidingForceActuator`, `ForceLocalizationActuator`, `YoungModulusActuator`
- **Effectors**: `BarycentricCenterEffector`, `CableEffector`, `PositionEffector`, `SurfacePressureEffector`, `SurfaceSlidingEffector`, `VolumeEffector`
- **Equalities**: `CableEquality`, `PositionEquality`, `SurfacePressureEquality`
- **Sensors**: `CableSensor`, `SurfacePressureSensor`, `SurfaceSlidingSensor`

`CosseratActuatorConstraint` is in the `Cosserat` plugin (not `SoftRobots.Inverse`) — forward-compatible, does NOT require `QPInverseProblemSolver`.
