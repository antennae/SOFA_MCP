# Agent 3 — recent (~24mo) SOFA closed issues

**Date:** 2026-04-25. Source: GitHub Issues API and HTML pages on `sofa-framework/sofa` and `SofaDefrost/SoftRobots`. Coverage: ~30 closed issues sampled, ~15 read in detail. Cutoff: issues updated 2024-01-01 through 2026-04-23. **No overlap with Agent 4's older / forum set.**

## Executive summary

Recent SOFA bugs cluster differently from the older ones Agent 4 mined. The dominant motifs of the past 24 months are: (a) **mapping-aware solver bugs** (mass matrices behaving wrong under mappings, integrator coefficients off by powers of `tr`/`h`); (b) **silent topology / sub-topology corruption** at material interfaces and after refactors; (c) **path / link-string typos in Data references** producing the `cannot find mechanical object named '0000…0000'` error class — diagnosed by reading stderr; and (d) **dt-sensitive constraints** (notably `SurfacePressureConstraint`) where a scene that converges at one `dt` explodes at another. These are exactly the failure modes a sanity-report + smell-test loop should catch — most produce a cheap, parseable signal (NaN, zero motion, recognizable bad-pointer string in error, divergent behavior between two dt values).

## Patterns / findings (12)

1. **#5999 — `EulerExplicitSolver` gives zero acceleration for mapped masses.** Symptom: particle under gravity through `IdentityMapping` doesn't accelerate, only translates at constant velocity. Diagnosed by minimal repro + visual trajectory comparison. Root cause: solver computes `M^-1 f` instead of `(JᵀMJ)^-1 f`. Fix: solver patch upstream. Maps cleanly to a `mapped_dof_zero_accel` smell test.

2. **#5140 — `EulerImplicitSolver` trapezoidal `kFact` off by `tr·h`.** Symptom: subtly wrong dynamics with `trapezoidal=True`. Diagnosed by a developer reading code against the analytical derivation (no in-scene signal). Fix: PR #5169, `kFact = -tr·tr·h·h`. Lesson: some bugs only show as *subtle wrongness* at long horizons.

3. **#5733 — Ogden material: `SelfAdjointEigenSolver` returns wrong eigenvectors.** Symptom: hyperelastic test fails; residual `‖Cv − λv‖ ≈ 7`. Diagnosed by checking eigen-equation residual directly. Fix: switched to generic `EigenSolver`. Too domain-specific to add as a smell test.

4. **#5751 — Tetrahedral beam drifts laterally under `SurfacePressureForceField`.** Symptom: tet beam deflects sideways where hex beam doesn't, especially at ν≈0.495. Diagnosed by tet vs hex comparison on the same load. Root cause: linear-tet locking with near-incompressible material. Workaround: hex elements or lower ν. Maps to **`high_poisson_with_linear_tet`** smell test.

5. **#5135 — `MeshSpringForceField` silently ignores `indices1`/`indices2` after PR #4649.** Symptom: user provides indices, gets topology-wide springs; no warning. Diagnosed by side-by-side scene with `SpringForceField`. Maps to a `silent_data_ignored` smell test for known-affected components.

6. **#5130 — Layered soft tissue interpenetrates under `PenalityContactForceField`.** Symptom: muscle/fat/skin layers tear into each other when dragged. Components: `LocalMinDistance` (alarm=0.1, contact=0.05), `TetrahedralCorotationalFEMForceField`. Root cause: penalty contact too soft for mass/stiffness ratio; `alarmDistance` ≪ tet edge length. Maps to **`alarm_distance_vs_mesh_scale`**.

7. **#5100 — Collision response silently inserts unowned `MechanicalObject` + `BarycentricMapping` nodes, then crashes.** Symptom: scene graph grows extra nodes after first contact, then segfault. Diagnosed by post-step graph inspection. Suggests probe **`scene_graph_diff_pre_post_init`**.

8. **#5579 — `cannot find the mechanical object named '0000000000000000'`.** Symptom: error string contains a null pointer formatted as hex zeros. Root cause: `IdentityMapping input="@../../airMechanicalObject"` referenced wrong path; actual MO was `@../../air/air`. Diagnosed by reading stderr and grepping the scene for the bad path. **Highest-value playbook entry.** The smell test is trivial: regex stdout for `'0+'` between quotes.

9. **#4954 — SOFA mass / stiffness matrices disagree with COMSOL on a 27-node cube.** User used `assembleMMatrix()` / `assembleKMatrix()`. No fix landed. Implication: matrix assembly is *not* trustworthy ground truth; if we add an `assemble_*_matrix` probe, document that values are SOFA-internal-convention dependent.

10. **#4706 — Multi-material hyperelasticity via sub-topologies crashes mid-simulation.** Symptom: scene with two `BoxROI`-defined regions and two `TetrahedronHyperelasticityFEMForceField` instances runs ~N steps and segfaults. Suspected cause: interface edges counted in both sub-topologies → double force. Maps to **`overlapping_subtopology_indices`** (intersect ROI index sets).

11. **#2486 — `BilateralInteractionConstraint` regression v19.12 → v21.06.** Symptom: visualisation of constraint pairs shows correct contact points, but distances drift; objects "let go" instead of being grasped. Fixed in PR #2495. Lesson: **constraint visual ≠ constraint enforcement** — different code paths. Smell test: **`bilateral_constraint_pair_distance_drift`** (monotonic growth in paired-index distance).

12. **SoftRobots #86 — `SurfacePressureConstraint` is `dt`-dependent with `valueType="pressure"`.** Symptom: bunny deforms differently at dt=0.01 / 0.001 / 0.0001; explodes around 0.5 kPa at small dt regardless of ramp speed. Root cause: pressure not normalized over dt. **Highest-leverage probe pattern**: `perturb_and_run` with halved dt; if behavior changes qualitatively, flag `dt_sensitivity`.

## Recommended additions to smell tests (priority order)

- **`mapped_dof_zero_accel`** — for each MO under a `Mapping`, check velocity changes when net force ≠ 0. Cites #5999. Cheap; complements Agent 4's `fixed_points_drift`.
- **`broken_link_string`** — regex stderr for `'0+'` patterns inside quotes. Cites #5579. Five lines of code; catches the typo'd-`@`-path class.
- **`alarm_distance_vs_mesh_scale`** — compare `alarmDistance` / `contactDistance` to mean edge length of the collision mesh. Cites #5130; complements Agent 4's "constraint vs collision on same region" from a different angle.
- **`dt_sensitivity` (promote to probe)** — re-run last 20 steps at `dt/2`; flag if max-displacement-per-MO disagrees by >10%. Cites SoftRobots #86 + #5751. Expensive — should be a probe `perturb_and_run` invokes, not a default sanity-report check.
- **`overlapping_subtopology_indices`** — when multiple ForceFields share a parent topology, intersect their index sets; flag non-empty intersection. Cites #4706.
- **`bilateral_constraint_pair_distance_drift`** — track paired-index distance under any `BilateralInteractionConstraint`; flag monotonic growth. Cites #2486.
- **`high_poisson_with_linear_tet`** — flag `TetrahedronFEMForceField` with ν > 0.45. Cites #5751.

**De-prioritise** Agent 1's `monotonic_energy_growth` (already B3 in their findings). #5140 shows that even when the bug is real, energy signal is too noisy to be diagnostic without analytical ground truth.

## Recommended additions to playbook

- **"Error mentions `'0000000000000000'`"** → broken `@`-path string in a Data link; grep scene for the suspect MO/topology name. Cite #5579.
- **"Same scene works at one dt, fails at another"** → run `perturb_and_run` halving dt; if behavior diverges, blame an unnormalized constraint or explicit-method instability. Cite SoftRobots #86, #5751.
- **"After collision, extra nodes appear in scene graph then crash"** → expected SOFA behavior is auto-inserted response nodes, but a *crash* immediately after means the inserted Mapping has no valid parent MO. Probe by snapshotting the tree pre-init vs post-step-1. Cite #5100.
- **"`indices` set on a force field but no springs / forces appear"** → known regression class (#5135 for `MeshSpringForceField`). Warn explicitly when a Data field is set but the runtime ignores it.

## Contradictions / disagreements

- **Spec smell test `low_forces` (per-ForceField).** Agent 1 already flagged non-uniformity. #4954 confirms even *assembled* matrices aren't always trustworthy. Implement only **`low_assembled_forces` per-MO**; drop per-FF.
- **Spec's `compare_scenes(scene_a_path, scene_b_path)`.** #5135 (silently-ignored Data fields) shows source-text diff isn't sufficient — a runtime Data-value diff after `init()` would have caught the regression where `indices1` was set but not used. Make `compare_scenes` operate on the *runtime* scene graph (post-init Data values), not source text. Stronger version of an ambiguity Agent 1 already flagged.
- **Agent 4's "DataEngine init-order" theme.** Recent issues don't reinforce this — no 2024-2026 issue with that signature. Lower the priority of any DataEngine-specific smell test relative to the mapping-aware ones above.
- **Spec's defaulting `log_solvers=True`.** Strongly confirmed: #5579, #5100, #4706 all surfaced their root cause via stderr/log inspection rather than metric anomalies. **Keep this default ON.**

Sources: api.github.com/search/issues queries; github.com/sofa-framework/sofa issues #5999, #5140, #5733, #5751, #5135, #5130, #5100, #5579, #4954, #4706, #2486; github.com/SofaDefrost/SoftRobots issues #86, #307, #136.
