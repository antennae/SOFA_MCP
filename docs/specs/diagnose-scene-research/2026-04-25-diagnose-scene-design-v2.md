# Design v2 — `diagnose_scene` investigation toolkit

**Date:** 2026-04-25
**Status:** Draft, post-multi-agent review. Pending one empirical check (`printLog` post-construction) before implementation.
**Owner:** Sizhe Tian
**Supersedes:** `2026-04-25-diagnose-scene-design.md` (v1).
**Review inputs:** `docs/specs/diagnose-scene-review-findings.md` (Agents 1, 4) + `docs/specs/diagnose-scene-review-agent-{2,3,5,6,7,8,9}.md`.

## Changelog vs v1

**Architectural:**
- v1 used `importlib` in-process loading. **v2 uses subprocess isolation** via `~/venv/bin/python` (Agent 1 B1, B2; reinforced by Agent 9: QPInverseProblemSolver allocates static qpOASES/proxQP scratch buffers that leak across in-process runs).
- v2 captures **all** stdout from `Sofa.Simulation.init` onward, not just solver logs (Agent 5: three of recent diagnoses came from default-verbosity factory/intersector warnings, not `printLog` output).
- The `printLog` target list is **dynamically discovered** from the plugin cache, not hardcoded (Agent 7: static list goes stale).

**Smell tests:**
- Drop `monotonic_energy_growth` (Agent 1 B3, Agent 5 F5, Agent 7: EulerImplicit dissipates by design).
- Weaken `low_forces` to `low_assembled_forces` per-MO (Agent 1 M6, Agent 5 F7).
- Replace `nan_inf_detected` boolean with `nan_first_step` (record step index; Agent 5 F3 — maintainers triage this).
- Fix `solver_iter_cap_hit`: branch on solver class. NNCG and BlockGaussSeidel expose `currentIterations` as queryable Data; LCP needs log regex (Agent 8).
- Fix `visual_mechanical_diff`: compare *changes*, not absolute equality, with generous tolerance (Agent 1 M8).
- 14 new smell tests added (see §6).

**Spec bug fixes:**
- Drop `SparseDirectSolver` from the API target list — **the class does not exist in this SOFA build** (Agent 8, verified via plugin cache + runtime instantiation). Same fix needed in `CLAUDE.md` and `sofa_mcp/architect/scene_writer.py`.
- Drop `FixedConstraint` / `PartialFixedConstraint` references — **renamed to `FixedProjectiveConstraint` / `PartialFixedProjectiveConstraint` in v23+** and both old names are unregistered (verified at runtime).
- Drop `DefaultContactManager` references — **renamed to `CollisionResponse` in v24.12** (verified at runtime).
- Drop `GenericConstraintSolver` (not registered in this build).

**Structural rules consolidated:**
- All pre-step structural smell tests (originally drafted as §6.C in early v2) are folded into the Scene Health Rules and `summarize_scene`'s `checks` field. `diagnose_scene` calls `summarize_scene` as step 1 of its pipeline and lifts the `checks` output into its anomalies. Single source of truth; same enforcement benefits scene authors (via `summarize_scene`) and bug investigators (via `diagnose_scene`). See §10 for the rule additions.

**Health Rule changes:** see §10.

## 1. Problem

(Unchanged from v1.) A user describes a *behavioral* bug in a SOFA scene in natural language. The scene runs without crashing — there is no traceback to parse, no missing component to flag. A rules engine doesn't help.

Goal: give an LLM agent the tools to investigate the bug. The MCP provides good probes; the LLM does the reasoning.

## 2. Non-goals

(Unchanged.) Not a complete diagnostician; not for structural-failure scenes (`validate_scene` covers those); not a "the bug is X" rules-based output.

## 3. Architecture (chosen: hybrid, subprocess-isolated)

Three layers — same shape as v1, with subprocess isolation throughout.

1. **Sanity report** (entry point, `diagnose_scene`) — runs the scene in a `~/venv/bin/python` subprocess, captures full stdout/stderr, sets `printLog=True` on dynamically-discovered solver classes plus per-class `verbose`/`displayDebug`/`d_displayTime` toggles, gathers per-step metrics, runs smell tests, returns a structured report.
2. **Probe library** — focused tools the agent calls based on the report and the playbook (§7).
3. **Playbook** — methodology section in `SKILL.md` mapping complaint patterns to investigation recipes (§9).

```
diagnose_scene(scene_path, complaint, steps)
      ↓
   summarize_scene(script_content)        ← structural Health-Rule checks
      ↓
   subprocess: load scene, mutate logging Data fields, init, animate
      ↓
   sanity report (structural checks + per-step metrics + stdout regex + full logs)
      ↓
   anomalies + metrics + logs
      ↓
   agent reads SKILL playbook → picks probe to dig deeper
                                       ↓
                                  scan_init_stdout
                                  enable_logs_and_run
                                  read_field_trajectory  (existing run_and_extract)
                                  compare_scenes  (runtime Data values, not source text)
                                  perturb_and_run
```

The first call into `summarize_scene` returns its `checks` array; any failed check becomes an anomaly in the diagnose report. This delegates all *structural* (pre-step) validation to one component, leaving `diagnose_scene` focused on the runtime-only smell tests in §6.

## 4. API: `diagnose_scene`

```python
diagnose_scene(
    scene_path: str,
    complaint: str = None,
    steps: int = 200,
    dt: float = None,           # None → use scene's root.dt (Agent 1 minor)
    log_solvers: bool = True,
) -> dict
```

**Behavior:**

1. Spawn `~/venv/bin/python` subprocess with a wrapper script. (Pattern follows `sofa_mcp/architect/scene_writer.py`.)
2. In the subprocess: import the scene module, build `rootNode`, walk the tree.
3. If `log_solvers`, for every component whose class is in the **dynamically-discovered solver target set**:
   - `findData("printLog")` → set True
   - `findData("verbose")` → set True if exists (catches `UncoupledConstraintCorrection`, `LCPConstraintSolver`, `LinearSolverConstraintCorrection.wire_optimization` is unrelated; Agent 1 M4, Agent 8)
   - `findData("displayDebug")` → set True if exists (catches `LCPConstraintSolver`; Agent 8)
   - `findData("displayTime")` / `findData("d_displayTime")` → set True if class is `QPInverseProblemSolver` (Agent 9)
   - `findData("computeResidual")` → set True if class is `EulerImplicitSolver` (Agent 8 — for v2 smell test using `residual` Data)
4. Solver target set is computed at runtime from the plugin cache by name suffix matching (`*Solver`, `*ConstraintCorrection`, `*AnimationLoop`) intersected with what's actually registered. Verified-registered classes (in this build, 2026-04-25): `EulerImplicitSolver`, `RungeKutta4Solver`, `NewmarkImplicitSolver`, `StaticSolver`, `EulerExplicitSolver`, `VariationalSymplecticSolver`, `CentralDifferenceSolver`, `SparseLDLSolver`, `CGLinearSolver`, `BTDLinearSolver`, `EigenSimplicialLDLT`, `PCGLinearSolver`, `AsyncSparseLDLSolver`, `SVDLinearSolver`, `NNCGConstraintSolver`, `LCPConstraintSolver`, `BlockGaussSeidelConstraintSolver`, `ImprovedJacobiConstraintSolver`, `UnbuiltGaussSeidelConstraintSolver`, `QPInverseProblemSolver`, `GenericConstraintCorrection`, `LinearSolverConstraintCorrection`, `UncoupledConstraintCorrection`, `PrecomputedConstraintCorrection`. (`DefaultAnimationLoop` is core-built-in and creatable but not in the plugin cache; the discovery mechanism must look at it via factory enumeration too.)
5. Initialize + animate N steps. Capture stdout/stderr.
6. Per step, capture per-`MechanicalObject`: `position`, `velocity`, `force` magnitude. Per-`ConstraintSolver`: `currentIterations` / `currentError` (NNCG, BlockGaussSeidel) or regex-parsed iter count from log (LCP, CG). For `QPInverseProblemSolver`: read `d_graph` Data (programmatic per-step `iterations`, `objective`; Agent 9 F2). For `EulerImplicitSolver` w/ `computeResidual=True`: read `residual` Data (Agent 8 §5).
7. Run smell tests (§6). Run regex smell tests against captured stdout (§6.B).
8. Truncate logs: keep first 5KB head + last 25KB tail + summarize the middle as "N lines elided" (Agent 1 M7, Agent 5 §3 confirms head matters most).
9. Return structured report.

**Return shape:** unchanged from v1, with `nan_first_step` (int|null) added to metrics, and an `init_stdout_findings` list separate from `solver_logs`.

## 5. Subprocess isolation (Agent 1 B1, B2)

Implementation pattern mirrors `scene_writer.py` validation:

- Wrapper script (`sofa_mcp/observer/_diagnose_runner.py`) loads the scene module, builds + animates, emits `DIAGNOSE_JSON: <payload>` on the last line of stdout for the parent to parse.
- Parent (`diagnose_scene`) does `subprocess.run(["~/venv/bin/python", "_diagnose_runner.py", scene_path, ...], capture_output=True, timeout=...)`.
- Per-run isolation makes back-to-back diagnose calls (e.g., for `perturb_and_run`) safe even when scenes hold mutable controller state, when QPInverseProblemSolver allocates global qpOASES buffers, or when the scene's own controller reuses module-scope state (cf. `RobSouple-SOFA/projet.py:201`).

This adds ~30 lines of process-spawn overhead but eliminates the `sys.modules` leak and the static-buffer cross-talk.

## 6. Smell tests

### 6.A — Per-step / runtime-data smell tests

| Rule | Trigger | Likely meaning | Source |
|---|---|---|---|
| `nan_first_step` | record first step where any field is NaN/inf, null otherwise | numerical explosion / singular matrix | v1 + Agent 5 F3 |
| `low_displacement` | max disp per MO < threshold | actuator inactive / forces too small / overdamped | v1 |
| `excessive_displacement` | max disp > threshold | numerical instability / scale mismatch | v1 |
| `low_assembled_forces` | per-MO assembled `force` magnitude ~0 | mapping broken / actuator never engaged. Note: **constraint-mediated forces don't appear here** (Agent 1 M6, Agent 5 F7) — for those see `actuator_lambda_zero` | v1 weakened |
| `mo_static` | individual unmapped MO has 0 motion | dead component / mismapped / overconstrained | v1 |
| `solver_iter_cap_hit` | NNCG/BlockGaussSeidel: `currentIterations == maxIterations` every step. LCP/CG: regex match `Iter=N` against maxIterations | underconstrained / poorly scaled | v1 + Agent 8 (class branching) |
| `visual_mechanical_diff` | per-step **change** in OglModel positions diverges from mapped MO change by >1e-5 mm | broken Mapping (Identity vs Barycentric mismatch) | v1 + Agent 1 M8 |
| `mapped_dof_zero_accel` | for each MO under a Mapping, velocity doesn't change when net force ≠ 0 | mass-matrix bug under mapping (cites SOFA #5999) | Agent 3 #1 |
| `child_only_motion` | mapped child MO max disp >>100× parent MO max disp | broken mapping in cable/actuator setup | Agent 9 F8 |
| `actuator_lambda_zero` | all `lambda` entries for actuators in QP printLog == 0 every step | inverse actuator never engaged | Agent 9 F1 |
| `cable_negative_lambda` | any cable lambda < 0 in QP printLog | cable pushing instead of pulling (missing minForce) | Agent 9 F10 |
| `q_norm_blowup` | "Relative variation of infinity norm" >10× on any step (parsed from QP printLog) | ill-conditioned QP | Agent 9 F9 |
| `inverse_objective_not_decreasing` | `d_graph["objective"]` non-decreasing under `QPInverseProblemSolver` | infeasible target or insufficient actuators | Agent 9 F2 |

### 6.B — Init-time stdout regex smell tests (Agent 5 §3, Agent 7 #1, Agent 9 F6)

Run against full captured stdout from `init` onward. Each is cheap and high-signal.

| Rule | Trigger (regex / pattern) | Likely meaning |
|---|---|---|
| `factory_or_intersector_warning` | `Element Intersector .* NOT FOUND` or `Object type .* was not created` or `cannot be found in the factory` | missing `RequiredPlugin` / template mismatch / unregistered class |
| `qp_infeasible_in_log` | `QP infeasible` | inverse target unreachable / overconstrained |
| `broken_link_string` | `'0+'` between quotes in stderr (e.g., `mechanical object named '0000000000000000'`) | broken `@`-path Data link (Agent 3 #8) |
| `pybind_numpy_warning` | `Could not read value for data field .* np.float64` | numpy/pybind11 ABI mismatch |
| `plugin_not_imported_warning` | `This scene is using component defined in plugins but is not importing` | missing `RequiredPlugin` (Agent 9 F6) |
| `auto_lcp_constraint_solver_warning` | upstream message when FreeMotionAnimationLoop auto-creates LCP because no constraint solver was provided | masked configuration bug (Agent 7 #4) |

### 6.C — Pre-step structural checks: delegated to `summarize_scene`

All structural anti-pattern detection lives in `summarize_scene`'s `checks` field, enforced via the Scene Health Rules (§10). `diagnose_scene` lifts those checks into its anomalies array as step 1 of the pipeline. The full list of rules added/refined to absorb what was originally drafted here is in §10.

(Drop `monotonic_energy_growth` from v1 — no general extraction path; Agent 1 B3.)

## 7. Probe library — v1

| Probe | Purpose | Estimated lines |
|---|---|---|
| `enable_logs_and_run(scene_path, log_targets, steps)` | Toggle `printLog`/`verbose`/`displayDebug` on specific components by class name or node path; run; return logs. | ~150 (Agent 1 minor: realistic estimate) |
| `read_field_trajectory` | Already exists as `run_and_extract` — reuse | 0 |
| `compare_scenes(scene_a_path, scene_b_path)` | Diff **runtime scene graphs** (post-init Data values), not source text. (Agent 1 minor; Agent 3 contradiction §) | ~80 |
| `perturb_and_run(scene_path, parameter_changes, steps)` | Patch fields temporarily, run, return metrics. Used for `dt_sensitivity` check (rerun at 0.5×dt) per Agent 9 F5. | ~100 |
| `scan_init_stdout(scene_path)` | Load + init only (no animate), capture stdout/stderr, run §6.B smell tests. ~1s. (Agent 5 §) | ~40 |

**v2 (later, gated on real-world need):**
- `bisect_scene` — strip components, add back to find trigger.
- `read_constraint_forces(scene_path)` — extract per-contact forces via H^T·λ when `computeConstraintForces=1` (Agent 6 F4).
- `count_contacts_per_step(scene_path)` — distinguishes "contacts not detected" from "contacts detected, response broken" (Agent 5 F8).
- `profile_scene(scene_path, sampling_interval)` — wraps runSofa `-c N` (Agent 7 #11).

## 8. Sample report (revised)

```json
{
  "success": true,
  "metrics": {
    "max_displacement_per_mo": {"/leg_0/mo": 0.001, "/leg_1/mo": 0.005},
    "max_force_per_mo": {...},
    "constraint_solver_iterations_per_step": [...],
    "qp_solver_objective_per_step": [...],
    "nan_first_step": null,
    "scene_classification_units": "mm/g/s"
  },
  "anomalies": [
    {"severity": "warning", "rule": "low_displacement", "subject": "/leg_0/mo",
     "message": "...", "suggested_probe": "enable_logs_and_run on /leg_0/cable_0"}
  ],
  "init_stdout_findings": [
    {"rule": "factory_or_intersector_warning", "match": "...", "context": "..."}
  ],
  "solver_logs": "<head 5KB + tail 25KB, middle elided>",
  "scene_summary": {"node_count": 4, "class_counts": {...}, "actuators_only": false}
}
```

## 9. Playbook (added/updated in `SKILL.md`)

Updated complaint table:

| User complaint | First check | Confirm with |
|---|---|---|
| "nothing moves / no actuation" | sanity → `low_assembled_forces`, `freemotion_without_constraintcorrection`, `inverse_actuator_without_qp_solver` | `enable_logs_and_run` on actuator + solver |
| "cable/actuator does nothing in inverse scene" | `inverse_actuator_without_qp_solver`, `actuator_lambda_zero` | `enable_logs_and_run` on `QPInverseProblemSolver`, read `lambda` block |
| "explodes / NaN at step N>0" | `nan_first_step` index | `enable_logs_and_run` from step N-5; reduce dt; check Rayleigh damping (default 0; if scene sets it ≫0.1, may be over-damped) |
| "passes through itself" | check collision pipeline cluster (5 components); `count_contacts_per_step` (v2 probe) | `render_with_debug_flags` showing `showCollisionModels` (v2 probe) |
| "deformation way too small" | sanity → `low_displacement`. **Hypotheses**: actuator inactive, Rayleigh damping set too high, EulerImplicit dissipation, wrong material modulus | `perturb_and_run` with reduced YM, or `trapezoidalScheme=1` |
| "visual lags mechanical / wrong place" | sanity → `visual_mechanical_diff`, `pybind_numpy_warning` in init stdout | `enable_logs_and_run` on the Mapping |
| "scene A works, B doesn't" | `compare_scenes(A, B)` (runtime values) | `diagnose_scene` on B |
| "QP infeasible / overconstrained" | `qp_infeasible_in_log`, `q_norm_blowup` | reduce dt, raise `contactDistance`, simplify collision geometry |
| "only the master DoF moves (cables, rigids)" | `child_only_motion` | inspect mapping; compare child vs parent trajectories |
| "force/pressure scales with dt" | rerun at 0.5×dt via `perturb_and_run` | known dt-scaling on `SurfacePressureConstraint`/`CableConstraint` (Agent 9 F5); divide by dt for physical units |
| "haptic device feels nothing" | check for `LCPForceFeedback` node | (Agent 6 F5) |
| "scene crashes mid-run after carving/tearing" | `topology_changing_with_static_indices` | (Agent 6 F3) |

The playbook is **additive** to the agent's own reasoning — the MCP doesn't claim "the bug is X." Agent picks a hypothesis, calls a probe, refines.

## 10. Scene Health Rule changes (`SKILL.md`)

**To revise:**
- **Rule 2 — Animation Loop.**
  - *Recommend:* `FreeMotionAnimationLoop` when Lagrangian constraints or inverse actuators are present; `DefaultAnimationLoop` otherwise. `FreeMotionAnimationLoop` is **required** in the constraint case — `DefaultAnimationLoop` does not support Lagrange multipliers (Agent 7 #3).
  - *Validate:* accept any of `FreeMotionAnimationLoop`, `DefaultAnimationLoop`, `ConstraintAnimationLoop`, `MultiStepAnimationLoop`, `MultiTagAnimationLoop` (all class-cache-verified registered). Don't false-flag the niche ones.
  - *Trigger on absence:* a scene with no loop silently auto-instantiates `DefaultAnimationLoop`, so the rule must check the constraint case even when the loop is implicit (Agent 7 #2).
  - *Discovery escape:* if you need `ConstraintAnimationLoop` / `MultiStepAnimationLoop` / `MultiTagAnimationLoop`, use `search_sofa_components`.

- **Rule 3 — Time Integration Solver.**
  - *Recommend:* `EulerImplicitSolver` for almost everything (~88% of upstream uses); `RungeKutta4Solver` for explicit dynamics where stiffness is bounded.
  - *Validate:* accept any of `EulerImplicitSolver`, `RungeKutta4Solver`, `NewmarkImplicitSolver`, `StaticSolver`, `EulerExplicitSolver`, `VariationalSymplecticSolver`, `CentralDifferenceSolver` (all class-cache-verified registered).
  - *Exempt mapped MOs* from the in-ancestry requirement — a mapped MO inherits dynamics from its parent.
  - *Discovery escape:* for quasi-statics use `StaticSolver`; for energy-conserving use `VariationalSymplecticSolver`; discover via `search_sofa_components`.
- **Rule 5 — Constraint Handling.** Three sub-checks added:
  - Soften "constraint correction on each mechanical node" to "constraint correction somewhere in each deformable subtree."
  - **Inverse-actuator-needs-QP**: any `PullingCable`, `CableActuator`, `SurfacePressureActuator`, `ForcePointActuator`, etc. requires `QPInverseProblemSolver` at root. (Agent 9 F4.)
  - **AttachConstraint template match**: `AttachConstraint` / `BilateralLagrangianConstraint` between MOs require both MOs share template (Vec3d↔Vec3d, Rigid3d↔Rigid3d). (Agent 5 F13, Agent 6 F7.)
  - Recommended defaults: `NNCGConstraintSolver` for forward-sim soft robotics (registered + user-preferred), `QPInverseProblemSolver` for inverse, `GenericConstraintCorrection` as the safe correction default, `LinearSolverConstraintCorrection` for cable/wire-heavy scenes (`wire_optimization`).
- **Rule 7 — Topology Containers.** Extend with: a `BarycentricMapping`'s **parent** node must have a volumetric topology container (`TetrahedronSetTopologyContainer`, `HexahedronSetTopologyContainer`, `*GridTopology`), not a surface-only one (`TriangleSetTopologyContainer`). (Agent 6 F6.) Also explicitly accept `MeshTopology` and `*GridTopology` as valid topology providers.
- **Rule 9 — Visual Style.** Change recommended `displayFlags` string to `"showBehaviorModels showForceFields showVisual"` (most-common upstream pattern).
- **Drop `[mm, g, s]` convention from CLAUDE.md and SKILL.md.** Replace with new Rule 11 (units consistency).
- **Replace `FixedConstraint` references with `FixedProjectiveConstraint`** in any scene-authoring guidance and validation lists. Old name is unregistered in v23+.

**To add:**
- **Rule 10 — Collision pipeline.** If any node has a `*CollisionModel`, the root needs the 5-component cluster: `CollisionPipeline`, `BruteForceBroadPhase`, `BVHNarrowPhase`, an intersection method (`MinProximityIntersection` or `LocalMinDistance`), and a contact manager (`CollisionResponse` — NOT `DefaultContactManager`, that name is unregistered).
- **Rule 11 — Units consistency.** Detect the scene's unit system from gravity magnitude (`-9.81` → SI; `-9810` → mm/g/s) and flag internal inconsistency: e.g. SI gravity with `youngModulus` in MPa-magnitude, or mesh extent in mm with SI gravity. Replaces the dropped blanket mm/g/s convention. (Agent 4 #1, refined per Agent 2 / user.)
- **Rule 12 — Structural anti-patterns.** Pre-step warnings that don't fit the existing rules cleanly:
  - **`multimapping_node_has_solver`** — `*MultiMapping` output node must NOT carry its own ODE solver (it breaks multimapping evaluation). (Agent 6 F8.)
  - **`topology_changing_with_static_indices`** — if a topology-modifying component (`SofaCarving`, `TearingEngine`, `TetrahedronSetTopologyModifier` with handlers) is present, all index-bearing components (`RestShapeSpringsForceField`, `FixedProjectiveConstraint`, `BoxROI` consumers) must use `TopologySubsetIndices`, not raw `Data<vector<Index>>`. (Agent 6 F3.)

**Not added** (per user preference):
- Rayleigh damping default. Use SOFA's default (0). Playbook still mentions it as a hypothesis when `low_displacement` fires.

## 11. Files to create / modify

**Create:**
- `sofa_mcp/observer/diagnostics.py` — orchestrator + smell tests
- `sofa_mcp/observer/_diagnose_runner.py` — subprocess-side wrapper
- `sofa_mcp/observer/probes.py` — `enable_logs_and_run`, `compare_scenes`, `perturb_and_run`, `scan_init_stdout`
- `test/test_observer/test_diagnostics.py` — table-driven tests for smell tests
- `test/test_observer/test_probes.py` — tests for individual probes

**Modify:**
- `sofa_mcp/server.py` — register the new tools.
- `skills/sofa-mcp/sofa-mcp/SKILL.md` — Health Rules edits (§10), playbook (§9), drop mm/g/s convention.
- `CLAUDE.md` — drop mm/g/s convention; fix the validated-class list (drop `SparseDirectSolver`, replace `FixedConstraint` with `FixedProjectiveConstraint`).
- `sofa_mcp/architect/scene_writer.py` — same fix to its required-component validation set.
- `README.md` — mention the toolkit.

**Estimated effort:** ~700 lines (subprocess-runner adds ~80 over v1; smell-test catalog grew ~70%; probes mostly the same).

## 12. Verification (M5 milestone)

User feeds the toolkit 3-4 scenes with known behavioral bugs:
- cables not actuated (missing `QPInverseProblemSolver` or wrong constraint correction)
- wrong material modulus (Young's modulus units mismatch)
- missing collision pipeline (Rule 10 violation)
- broken Mapping (`child_only_motion` should fire)

For each: does the agent (a) see the right anomaly in the sanity report or init-stdout findings, (b) propose a hypothesis a human SOFA dev would also propose, (c) verify by running the right follow-up probe?

Bar (unchanged): "the agent acts like a junior SOFA dev with no help, not like a stochastic parrot."

## 13. Open questions / things to validate before implementation

1. **Does `printLog=True` post-construction actually work?** Most components honor it as a runtime-checked Data field, but timing varies. **Empirical test before implementation:** run the cantilever scene with all solvers' `printLog=True` set after `createScene` returns and before `Sofa.Simulation.init`; assert stdout is non-empty. (Agent 1 M4 explicitly listed this as the regression-test recommendation; v1 Open Question 3 unresolved.)
2. **Subprocess vs in-process for `perturb_and_run`** — subprocess is correctness-safe but adds ~1s startup per call. If the agent calls `perturb_and_run` 10× in a session, that's 10s of overhead. Acceptable? Decide: subprocess always, or in-process with a forced `Sofa.Simulation.unload(root)` cleanup.
3. **Solver-log volume** — first 5KB head + last 25KB tail. If a scene runs 1000 steps with verbose solvers, the elided middle could be hundreds of KB. Probably fine, but worth a sanity check before shipping.
