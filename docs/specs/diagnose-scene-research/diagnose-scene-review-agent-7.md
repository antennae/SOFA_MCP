# Agent 7 — SOFA Official Documentation Review

**Mission:** Mine `https://sofa-framework.github.io/doc/` for general/tutorial/FAQ/troubleshooting/best-practices content relevant to `diagnose_scene` design and the 9 Scene Health Rules.

## Executive summary

The SOFA docs site has poor discoverability — many promising URLs (`using-sofa/`, `getting-started/`, FAQ, troubleshooting, performance, scene-checking, build-a-scene) return 404. Substantive content lives in `simulation-principles/` and component reference pages. There is **no canonical "scene checklist" published by upstream**, so our 9 Health Rules are essentially original work, but the docs do confirm individual items piecemeal. Two important *new* signals emerged: (1) `DefaultAnimationLoop` silently auto-instantiates if missing, so "scene is missing animation loop" is a soft failure mode the user never sees; (2) `EulerImplicitSolver` is "inherently dissipative" and `trapezoidalScheme` is documented as the upstream-recommended fix — a likely root cause of many "deformation too small" complaints. Both gaps need new smell tests. The docs also reveal `runSofa -c N` and the `VisualStyle` flag set as official debug tooling we should leverage.

## Findings

1. **Scene graph fundamentals — confirms our model.** `simulation-principles/scene-graph/`: "one node gathers the components associated with the same object (same degrees of freedom)." Validates Health Rule 6 (ForceField in same node as MO) and Rule 3 (solver in ancestry). Applies to smell tests `mo_static`, `low_forces`.

2. **Animation loop is auto-instantiated — silent failure.** `simulation-principles/animation-loop/`: "If none is explicitly defined, a DefaultAnimationLoop is automatically created at the root node." Our Rule 2 marks a missing loop as a violation, but a scene with no loop won't crash — it gets DefaultAnimationLoop and silently breaks any constraint-heavy setup. Add smell test `silent_default_animation_loop` (warn when no AnimationLoop is in script but constraint solvers/correction components are present — common cable/soft-robot bug).

3. **DefaultAnimationLoop refuses Lagrange multipliers.** `components/animationloop/defaultanimationloop/`: "this animation loop does not support constraints that use Lagrange multipliers." Confirms Rule 5 and gives a direct error pattern: scenes with `BilateralLagrangianConstraint`, `CableConstraint`, etc. must use `FreeMotionAnimationLoop`. Add smell test `lagrangian_constraint_with_default_loop`.

4. **FreeMotionAnimationLoop auto-creates LCP if no solver.** `components/animationloop/freemotionanimationloop/`: "If no [ConstraintSolver] is specified, an LCPConstraintSolver is automatically created." Explains "scene runs but constraints feel weird" complaints. Add smell test `auto_lcp_constraint_solver_warning`.

5. **EulerImplicitSolver dissipation default.** `components/odesolver/backward/eulerimplicitsolver`: scheme "is inherently dissipative, with only one Newton step performed per iteration." `rayleighStiffness=0` and `rayleighMass=0` defaults; `trapezoidalScheme="1"` reduces dissipation. Maps to "deformation way too small" complaints — energy is numerically damped. Playbook: when `low_displacement` flagged, *also* check rayleigh damping before suspecting the actuator.

6. **EulerExplicitSolver mass requirement.** `components/odesolver/forward/eulerexplicitsolver`: "is only working using" UniformMass or DiagonalMass; example dt = 0.00001. Add smell tests `explicit_solver_with_nondiagonal_mass` and `explicit_solver_with_large_dt` (>1e-3 with explicit is suspicious).

7. **CGLinearSolver convergence guidance.** `components/linearsolver/iterative/cglinearsolver`: "tolerance and threshold data must be chosen in accordance with the dimension of the degrees of freedom (DOFs). Usually, the value … is close to the square of the expected error on the DOFs." Default iterations=25, tolerance=1e-5. For [mm,g,s] units in a soft-robot scene, expected DOF error ~1e-3 mm → tolerance should be ~1e-6 not 1e-5. Refine our `solver_iter_cap_hit` for CG specifically.

8. **UniformMass accuracy warning.** `components/mass/uniformmass`: "should be carefully used if accuracy is a criterion, especially when using surface or volumetric physical models … no space integration." Our rules don't call this out. Add smell test `uniform_mass_on_volumetric_topology`.

9. **DiagonalMass loses connectivity.** `components/mass/diagonalmass/`: "diagonalizing the mass matrix … removes the connectivity (neighborhood) information from the matrix … decreases accuracy." Recommends `MeshMatrixMass`. Same playbook row as #8.

10. **VisualStyle is the official "visual debugger."** `components/visual/visualstyle/`: lists `showForceFields`, `showCollisionModels`, `showBoundingCollisionModels`, `showInteractionForceFields`, `showMappings`, `showWireframe`, `showNormals`. Page literally says these "enable visual debugging." Probe addition: `render_with_debug_flags(scene_path, flags=[...])` wrapping `render_scene_snapshot`. High value for "things pass through each other" and "visual lags mechanical."

11. **runSofa has built-in performance probe.** `using-sofa/runsofa`: `-c, --computationTimeSampling N` "outputs performance statistics at specified intervals … useful for analyzing simulation performance." This is upstream's recommended profiler. v2 probe: `profile_scene(scene_path, sampling_interval)` surfacing per-component timings — addresses "scene is too slow," which we have no story for today.

12. **Mappings can introduce asymmetric matrices.** `simulation-principles/multi-model-representation/mapping/`: "Non-linear mappings introduce geometric stiffness terms (∂J^T/∂q)f_p, potentially creating asymmetric mechanical matrices — requiring specialized solvers like LU decomposition." `BarycentricMapping` between mismatched topologies + `SparseLDLSolver` can silently misbehave. Add smell test `nonlinear_mapping_with_symmetric_solver`.

## Recommended additions to Scene Health Rules

- **Rule 2 (Animation Loop):** note that *missing* loop silently becomes DefaultAnimationLoop; only matters with Lagrange constraints. Reword: "Root must contain a `FreeMotionAnimationLoop` whenever any Lagrangian constraint or constraint correction is present; otherwise `DefaultAnimationLoop` is fine."
- **Rule 4 (Linear Solver):** add: "for non-linear mappings (`BarycentricMapping` across non-matching topologies, `SkinningMapping`), prefer `SparseLUSolver` over `SparseLDLSolver` — the system matrix may be asymmetric."
- **New Rule 10 (Mass choice):** "Volumetric FEM scenes should use `MeshMatrixMass` for accuracy. `UniformMass` is acceptable only for rigid-body or quick-prototype scenes; `DiagonalMass` when speed > accuracy."

## Recommended additions to smell tests

| New rule | Trigger | Likely meaning |
|---|---|---|
| `silent_default_animation_loop` | Lagrangian constraint present, no explicit animation loop | DefaultAnimationLoop auto-installed; constraints inactive |
| `lagrangian_constraint_with_default_loop` | explicit `DefaultAnimationLoop` + Lagrangian constraints | hard incompatibility |
| `auto_lcp_constraint_solver_warning` | `FreeMotionAnimationLoop` + no constraint solver | upstream auto-creates LCPConstraintSolver |
| `explicit_solver_with_nondiagonal_mass` | `EulerExplicitSolver` + `MeshMatrixMass` | undefined behavior |
| `explicit_solver_with_large_dt` | `EulerExplicitSolver` + dt > 1e-3 | likely stability failure |
| `uniform_mass_on_volumetric_topology` | `UniformMass` on tetra/hexa topology | accuracy warning |
| `nonlinear_mapping_with_symmetric_solver` | non-linear mapping + `SparseLDLSolver` | asymmetric matrix; need LU |
| `rayleigh_overdamped` | `EulerImplicitSolver` rayleighMass/Stiffness > ~0.1 | numerical damping eats deformation |

## Recommended additions to playbook

| User complaint | First check | Confirm with |
|---|---|---|
| "deformation way too small" | rayleigh damping + UniformMass smell | toggle `trapezoidalScheme=1`, `perturb_and_run` |
| "constraints don't engage" | `silent_default_animation_loop` + `lagrangian_constraint_with_default_loop` | `enable_logs_and_run` on constraint solver |
| "things pass through each other" | render with `showCollisionModels showBoundingCollisionModels` | inspect collision pipeline |
| "scene is too slow" | runSofa `-c N` equivalent | per-component timings |

## Contradictions / corrections

- **Spec line 57 solver list is incomplete.** Add `LCPConstraintSolver` (auto-created by FreeMotionAnimationLoop), `NewmarkImplicitSolver`, `VariationalSymplecticSolver`, `StaticSolver`, `ShewchukPCGLinearSolver`, `MinResLinearSolver`, `SparseLUSolver`, `CholeskySolver`, `SparseCholeskySolver`, `SVDLinearSolver`, `BTDLinearSolver`. Auto-discovery (Open Question 5) is the right approach — static list will go stale.
- **Open Question 3 (printLog post-construction):** docs don't confirm; messaging API page 404'd. Verify empirically as planned.
- **Spec smell test `monotonic_energy_growth`:** `EulerImplicitSolver` is *dissipative by design*, so monotonic *decrease* is also a signal when energy injection is expected (active actuators) — invert direction conditionally on actuator presence.

## URLs of record

`simulation-principles/animation-loop/`, `simulation-principles/scene-graph/`, `simulation-principles/system-resolution/integration-scheme/`, `simulation-principles/system-resolution/linear-solver/`, `simulation-principles/multi-model-representation/mapping/`, `components/animationloop/defaultanimationloop/`, `components/animationloop/freemotionanimationloop/`, `components/odesolver/backward/eulerimplicitsolver/`, `components/odesolver/forward/eulerexplicitsolver/`, `components/linearsolver/iterative/cglinearsolver/`, `components/mass/uniformmass/`, `components/mass/diagonalmass/`, `components/visual/visualstyle/`, `components/constraint/lagrangian/correction/genericconstraintcorrection`, `using-sofa/runsofa/`, `using-sofa/terminology/`.

**Pages that 404'd** (save future agents the trip): `/using-sofa/`, `/using-sofa/scene-checking/`, `/using-sofa/build-a-scene/`, `/using-sofa/performance/`, `/getting-started/`, `/getting-started/first-steps/`, `/programming-with-sofa/api-overview/messaging/`, `/simulation-principles/constraint/`, `/simulation-principles/visitor/`. **The SOFA site has no FAQ or troubleshooting section as of today.**
