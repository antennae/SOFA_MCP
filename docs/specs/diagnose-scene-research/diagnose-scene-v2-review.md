# `diagnose_scene` v2 spec review

**Date:** 2026-04-25. Independent review of `2026-04-25-diagnose-scene-design-v2.md` against agent findings 1-9 and the project's plugin cache.

## Executive verdict

v2 is a substantial improvement over v1 and gets the architectural decisions right (subprocess isolation, dynamic solver discovery, full-stdout capture, delegation of structural checks to `summarize_scene`). All three Agent-1 blockers are addressed. **However, v2 is not yet ready to implement** because (a) it still names two unregistered classes inside structural rules (`AttachConstraint`, `PullingCable`), repeating exactly the class-cache hygiene failure that motivated the rewrite; (b) it under-specifies the `summarize_scene` extension that the new architecture leans on (Rules 10/11/12 must move into the existing 3-check `checks` array but the current implementation has no slot for them); (c) the changelog claim of "14 new smell tests" is off by one (count is 13). One more revision pass to fix the unregistered-class names, scope the `summarize_scene` extension explicitly, and prune the half-dozen smell tests from Agents 3/7 that v2 silently dropped should put it in implementable shape.

## Blockers (must-fix before implementation)

**B1. Unregistered class names re-introduced inside Rule 5.** §10 Rule 5 sub-checks reference `AttachConstraint` ("AttachConstraint template match" sub-bullet) and `PullingCable` (Inverse-actuator-needs-QP). Neither appears in the plugin cache:
- `AttachConstraint` — not registered. The cache has `AttachProjectiveConstraint` (Sofa.Component.Constraint.Projective). Same v23+ rename family as `FixedConstraint`→`FixedProjectiveConstraint` that v2 fixed two bullets earlier.
- `PullingCable` — not registered. This is a `softrobots.actuators` Python prefab, not a C++ component class. The registered actuator names are `CableActuator`, `SurfacePressureActuator`, `ForcePointActuator`, `ForceSurfaceActuator`, `SlidingActuator`, etc. (`SoftRobots.Inverse` plugin). The smell test should match the registered names, not the prefab.

**B2. `summarize_scene` extension is unscoped.** §3 and §6.C state structural smell tests are folded into `summarize_scene`'s `checks` field and `diagnose_scene` "lifts the `checks` output into its anomalies." But the current `_build_summary_wrapper` in `sofa_mcp/architect/scene_writer.py:177-181` produces only three checks (`has_animation_loop`, `has_constraint_solver`, `has_time_integration`) as simple booleans — not the rich `{severity, rule, subject, message}` shape the diagnose report consumes. v2 needs an explicit subsection enumerating: (a) every new check `summarize_scene` must emit (Rule 5 sub-checks, Rule 7 extension, Rule 10 collision cluster, Rule 11 units, Rule 12 anti-patterns); (b) the new schema; (c) what `diagnose_scene` does when `summarize_scene` itself fails. As written the integration claim is gestural. Probably half the structural-check effort, invisible in §11.

## Major concerns (should-fix; not blockers)

**M1. `actuators_only` in scene_summary needs a source.** §8 sample output shows `"actuators_only": false`. Agent 9 F3 names `actuatorsOnly` as a `QPInverseProblemSolver` Data field. `summarize_scene` does not currently read component Data field values. Either spec that summarize_scene must read `actuatorsOnly` off the QP solver, or read it inside the diagnose subprocess.

**M2. Smell-test count claim wrong.** Changelog says "14 new smell tests added"; count is 13. Update.

**M3. Agent 3/7 smell tests dropped without acknowledgment.** v2 absorbs Agent 9 (8/8), Agent 6 (5/5 structural), Agent 5 (5/6) but silently drops several Agent 3 and Agent 7 high-signal items:
- Agent 3 F4: `high_poisson_with_linear_tet`
- Agent 3 F6: `alarm_distance_vs_mesh_scale`
- Agent 3 F10: `overlapping_subtopology_indices`
- Agent 3 F11: `bilateral_constraint_pair_distance_drift`
- Agent 7: `explicit_solver_with_large_dt`, `uniform_mass_on_volumetric_topology`, `nonlinear_mapping_with_symmetric_solver`, `rayleigh_overdamped`

Either implement, defer-with-justification, or list explicitly under "Not added."

**M4. `DefaultAnimationLoop` discovery is hand-waved.** §4 step 4 says it "must look at it via factory enumeration too" but doesn't name the API. The right call is `Sofa.Core.ObjectFactory` enumeration; without naming it, an implementer will hardcode or re-derive from `Base` MRO.

**M5. `compare_scenes` runtime-Data diff is much larger than ~80 lines.** Realistic: ~200 lines plus an awkward "what counts as equal" policy (float tolerance, index ordering, numpy array handling).

**M6. §6.B regex robustness.** Agent 5 quotes literal upstream strings — risky across SOFA versions. Add (a) regression tests pinning each regex against a known-bad scene, and (b) a fallback "any line emitted at WARNING or higher" catch-all.

**M7. Subprocess "~30 lines overhead" estimate is misleading.** Realistic: 120-180 lines for `_diagnose_runner.py` plus ~60 lines of parent-side parsing. ~5× understated.

## Minor concerns

- §3 diagram shows `summarize_scene(script_content)` as step 1, but `diagnose_scene` takes `scene_path`. Spell out the file-read step.
- §6.A `solver_iter_cap_hit` row says "every step." Consider relaxing to "≥ N consecutive steps" to avoid one-step transients.
- §10 Rule 5 mentions `wire_optimization` — should say "set `wire_optimization=1`," not just name the field.
- §13 Open Question 1 empirical test should also flip `Sofa.Helper.MessageHandler` per Agent 6 F10.
- The phrase "`LinearSolverConstraintCorrection.wire_optimization` is unrelated" inside §4 step 3 reads like a copy-paste residue.
- `nan_first_step` per the metric description records "first step where any field is NaN/inf" — scope to per-MO `position`/`velocity`/`force`, not arbitrary Data.
- v2 references `AttachConstraint` and `BilateralLagrangianConstraint` together for template matching. `BilateralLagrangianConstraint` IS registered. Keep that one; replace the AttachConstraint half.

## Class-registration audit

| Class named in v2 | Registered? | Verdict |
|---|---|---|
| All solvers in §4 step 4 list (24 classes) | YES | OK |
| `FreeMotionAnimationLoop`, `MultiStepAnimationLoop`, `ConstraintAnimationLoop`, `MultiTagAnimationLoop` | YES | OK |
| `DefaultAnimationLoop` | core builtin, not in cache | v2 acknowledges — see M4 |
| `CollisionAnimationLoop` | NOT in cache | v2 correctly excludes |
| Collision pipeline (`CollisionPipeline`, `BruteForceBroadPhase`, `BVHNarrowPhase`, `MinProximityIntersection`, `LocalMinDistance`, `CollisionResponse`) | YES | OK |
| `FixedProjectiveConstraint`, `PartialFixedProjectiveConstraint` | YES | OK |
| `BilateralLagrangianConstraint` | YES | OK |
| **`AttachConstraint`** | **NOT registered** | **B1 — replace with `AttachProjectiveConstraint`** |
| **`PullingCable`** | **NOT registered** (Python prefab) | **B1 — replace with `CableActuator`, `SurfacePressureActuator`, `ForcePointActuator`, `ForceSurfaceActuator`** |
| `SofaCarving`, `TearingEngine` (Rule 12) | NOT in cache | Either gate Rule 12 on plugin presence or describe by the registered modifier-with-handler set |
| `MeshTopology`, `*GridTopology` (Rule 7) | YES | OK |
| `LCPForceFeedback`, `RestShapeSpringsForceField`, `BoxROI` | YES | OK |

## Things v2 gets right

- All three Agent-1 blockers addressed (subprocess isolation, dynamic discovery, drop `monotonic_energy_growth`).
- `low_assembled_forces` correctly per-MO (Agent 1 M6) and notes constraint-mediated forces are absent (Agent 5 F7).
- Captures full stdout (Agent 5 §3 absorbed correctly).
- `d_graph` programmatic Data field for `QPInverseProblemSolver` (Agent 9 F2).
- `solver_iter_cap_hit` branches on solver class (Agent 8).
- Rules 2/3 `Recommend / Validate / Discovery escape` pattern is clearer than the original.
- Drops `SparseDirectSolver`, `GenericConstraintSolver`, old `FixedConstraint`, `DefaultContactManager` correctly.
- 5KB head + 25KB tail truncation matches the reading pattern.
- `compare_scenes` switching to runtime Data diff is the correct call.
- `nan_first_step` as integer index, not boolean.
- M5 verification list (cables, units, collision, mapping) is concrete.

## Final recommendation

**Revise once more.** Fix B1 (unregistered class names — quick), tighten B2 (`summarize_scene` extension subsection — the missing piece), and either implement or explicitly defer the M3 dropped smell tests. Re-estimate effort with M7's realistic subprocess-runner LOC. After that pass, implementable.
