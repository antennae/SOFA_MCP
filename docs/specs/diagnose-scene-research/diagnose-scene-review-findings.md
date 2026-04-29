# `diagnose_scene` review findings

External reviews of the spec at `docs/specs/2026-04-25-diagnose-scene-design.md`. Captured 2026-04-25 from a 9-agent review fleet; 2 succeeded substantively, 7 blocked by sub-agent permissions (re-run pending after permission allowlist setup). Findings below to be folded into the spec before implementation.

---

## Agent 1 — Spec review (succeeded fully)

### Blockers (must fix before implementation)

**B1. `sys.modules` leak inherited from `stepping.py`.** The spec's "load via `importlib` (same pattern as `stepping.py`, `renderer.py`)" inherits the bug from `code_review.md` issue #2 (`stepping.py:43`, `renderer.py:38`). `renderer.py:206` does clean up in `finally`; `stepping.py` does not. Worse: when `diagnose_scene` runs the same scene 2-3 times back-to-back to confirm a smell test, **state from the first run is still present in `sys.modules`**, so a smell test like `monotonic_energy_growth` can be triggered by stale residue rather than the scene under test.

*Fix:* implement a single `_load_scene_module(path)` helper with try/finally that pops the module **and** explicitly does `Sofa.Simulation.unload(root)` on exit. Place in `observer/` and have diagnostics use it.

**B2. In-process load + simultaneous `printLog` mutation poisons subsequent calls.** SOFA components are global C++ objects; setting `printLog=True` on a component referenced by a previously-loaded module leaks across diagnose calls if `sys.modules` retains them. Combined with B1 this is severe. CLAUDE.md explicitly calls subprocess isolation a "critical design decision."

*Fix:* **Use the `~/venv/bin/python` subprocess pattern from `scene_writer.py`** — write a wrapper script that does printLog mutation + animate + emits a `DIAGNOSE_JSON:` line, parse on return. Cost: ~30 lines of overhead, eliminates two correctness landmines.

**B3. `monotonic_energy_growth` has no general extraction path.** SOFA does not expose total kinetic/potential energy as a Data field. KE must be computed from `MechanicalObject.velocity` × `UniformMass.totalMass`; PE only exists inside ForceFields via `getPotentialEnergy()` (a method, not a Data field — `findData` won't find it).

*Fix:* drop `monotonic_energy_growth` from v1, or replace with `monotonic_velocity_norm_growth` (sum of `||v_i||² × mass_i` on a best-effort MO walk; document the approximation).

### Major concerns (should fix)

**M4. `printLog` semantics are component-specific.** `printLog` is a runtime-checked Data field in `sofa::core::objectmodel::Base`; consulted by `msg_info()` macros at log-emission time, not cached at `init()`. Setting it after `createScene` and before `Simulation.init` will work for almost all components — *but* some constraint solvers gate verbose output on a separate `verbose` Data field (e.g., `LCPConstraintSolver.verbose`), so the static class-name list will silently miss output for those.

*Fix:* after setting `printLog=True`, also set `verbose=True` if the field exists (`obj.findData("verbose")` truthy → `setValue(True)`); add a regression test that runs the cantilever scene with `log_solvers=True` and asserts stdout is non-empty.

**M5. `solver_iter_cap_hit` requires reading post-step iteration count, which is not a uniform Data field.** Some solvers expose `currentIterations` or `iterations`, others only the configured `maxIterations` input. `NNCGConstraintSolver` exposes iteration count via printout, not a programmatically queryable field in all versions.

*Fix:* implement this rule by **parsing the captured solver log** (regex for "Iter=N" / "iterations: N") rather than `findData`. Otherwise the rule will silently never fire.

**M6. `low_forces` per-ForceField magnitude is not uniformly available.** `findData("f")` on a MechanicalObject returns the assembled force vector, not per-ForceField. Per-ForceField forces require either `addForce()` on a buffer (rarely exposed) or computing it from displacement via `addDForce`. None of this is plug-and-play across `HexahedronFEMForceField`, `TetrahedronFEMForceField`, `ConstantForceField`.

*Fix:* rename to `low_assembled_forces` and read `MechanicalObject.force` magnitude per MO. Drop the per-FF promise.

**M7. 50KB stdout truncation is the wrong tail.** Solver logs in SOFA are highly periodic (same line every step). 50KB of "step 1 → step 47" is useless if the explosion happens at step 198.

*Fix:* keep first 5KB + last 25KB + summarize the middle as "N lines elided"; matches how the agent actually reads logs.

**M8. `visual_mechanical_diff` smell test bakes in a wrong assumption.** OglModel positions equal mapped MO positions only after the visual mapping has run during the simulation step. In a `FreeMotionAnimationLoop`, mapping propagation happens before draw, not before user inspection.

*Fix:* either drop this rule, or compare *changes* not *absolute equality* and set a generous tolerance (e.g., 1e-5 mm).

### Minor

- `dt: float = 0.01` — every existing scene in this project sets its own `node.dt`. Passing `dt` and ignoring `root.dt` produces subtly wrong dynamics. Read `root.dt` first, use spec'd `dt` only as override.
- `enable_logs_and_run` realistic estimate is ~150 lines (not ~80) once class-name vs node-path target resolution is implemented (cf. `stepping.py:62-79`).
- `compare_scenes`: be explicit whether it diffs source text or runtime graph (very different tools). Spec is ambiguous.
- File should live in `sofa_mcp/observer/diagnostics.py` (not `architect/`) to match the `observer/{stepping,renderer,metrics}.py` pattern.
- `metrics.py` is empty (0 bytes). Populate that module rather than starting fresh.

### Things the spec gets right

The hybrid "sanity report + probe library + playbook" architecture matches how a SOFA developer actually debugs (`grep printLog sofa_examples/`-style workflow). Defaulting `log_solvers=True` is the right tradeoff: noise is cheap, missing context is expensive. The "agent reads evidence and reasons; the MCP doesn't claim 'the bug is X'" framing is exactly right for a portfolio piece. The smell-test table is well-shaped (severity + subject + suggested probe). The playbook complaint table reads like real triage. Reusing `run_and_extract` instead of reimplementing it is correct.

---

## Agent 4 — SOFA closed issues, 2-5 years old (partial success via WebSearch)

`gh` and `WebFetch` were blocked; agent fell back to `WebSearch` and surfaced ~12 specific SOFA GitHub issues, Discussions, and forum posts. Citations included.

### Headline themes

The classic gotchas cluster around five themes: **units (mm/g/s vs SI)**, **constraint/collision pipeline mismatches**, **animation-loop / constraint-correction pairing**, **plugin gating after the v20.12 PLUGINIZE migration**, and **mapping / topology incompatibilities**.

### 12 patterns with citations

1. **Units mismatch — Young's modulus in Pa instead of MPa** ([Discussion #2879](https://github.com/sofa-framework/sofa/discussions/2879), [forum: Units of simulation](https://www.sofa-framework.org/community/forum/topic/units-of-simulation/)). Deformation absurdly small or large because scene in mm but `youngModulus=3000` interpreted as 3 GPa instead of 3 MPa.

2. **Gravity sign / magnitude wrong unit** ([forum: Model collapse with gravity](https://www.sofa-framework.org/community/forum/topic/model-collapse-with-force-of-gravity/)). User uses `-9.81` in mm scene; objects barely move. Fix: `-9810` for mm/s².

3. **`FixedConstraint` fixes position but not velocity under FreeMotionAnimationLoop** ([forum: Fixed constraints not so fixed](https://www.sofa-framework.org/community/forum/topic/fixed-constraints-not-so-fixed-with-genericconstraintsolver/)). By design — projective constraint clamps positions, but Lagrange-mediated impulse perturbs velocities, integrating to drift. Fix: `PartialFixedConstraint` or stiffness-based attach.

4. **`UncoupledConstraintCorrection` + deformable FEM mismatch** ([forum](https://www.sofa-framework.org/community/forum/topic/objects-not-colliding-using-uncoupledconstraintcorrection/)). Uncoupled assumes diagonal compliance; pairs poorly with deformable FEM. Fix: `LinearSolverConstraintCorrection` + `SparseLDLSolver`.

5. **Modeller (legacy GUI) corrupts scenes** ([forum](https://www.sofa-framework.org/community/forum/topic/constraint-tutorial-scene-crash/)). Scenes that run fine in `runSofa` crash when loaded via Modeller.

6. **Bilateral constraint + collision on same region → simulation freezes** ([forum: Subset mapping & collisions](https://www.sofa-framework.org/community/forum/topic/subset-mapping-collisions/)). Collision pushes apart, constraint pulls together — solver hits iteration cap. Diagnosed via `solver_iter_cap_hit`.

7. **Collision response type incompatible with constraints (segfault)** ([forum: Crash in collision response](https://www.sofa-framework.org/community/forum/topic/crash-in-collision-response-computation/)). Switching `distanceLMConstraint` → `FrictionContact` fixed it.

8. **Cable/Pneunet not actuating because BarycentricMapping is broken** ([Discussion #4716](https://github.com/sofa-framework/sofa/discussions/4716), [Issue #5060](https://github.com/sofa-framework/sofa/issues/5060)). Only `pullPoint` moves, fingers don't. Missing/wrong `BarycentricMapping` between cable DoFs and finger DoFs.

9. **`CableConstraint` negative-force surprise** ([Discussion #4923](https://github.com/sofa-framework/sofa/discussions/4923)). Old behavior pushed instead of pulled when force went negative; current API needs explicit `minForce=0`.

10. **PLUGINIZE migration (v20.12+) — RequiredPlugin missing → component silently null** ([Issue #307](https://github.com/sofa-framework/sofa/issues/307), [Issue #1402](https://github.com/sofa-framework/sofa/issues/1402)). Long-standing user trap.

11. **DataEngine init-order bug — MO sees empty link.** Scene-graph order determines visitor order; DataEngine *after* MO leaves MO seeing nothing.

12. **Hexa BarycentricMapping fails when output verts outside any element** ([forum](https://www.sofa-framework.org/community/forum/topic/barycentricmapping-and-hexahedral-meshes/)). Verts get assigned but coefficients drift.

### Recommended new smell tests

- **`units_inconsistency`** — heuristic on YM vs gravity vs mass vs mesh extent (mm/g/s convention)
- **`fixed_points_drift`** — track fixed-indexed DoFs; flag drift > 1e-6
- **`constraint_correction_mismatch`** — `UncoupledConstraintCorrection` + FEM is suspicious
- **`cable_minforce_unset`** — `CableConstraint` without `minForce` for actuation
- **`legacy_response_string`** — flag pre-v21.12 collision response names

### Recommended new playbook entries

- **"Object type not in factory"** → 95% missing `RequiredPlugin`. Diagnose first.
- **"works in runSofa, fails in <tool>"** → blame the tool, not the scene
- **"infinite solver iterations"** → constraint + collision on the same region
- **"only the master DoF moves"** (cables, rigids) → mapping broken or absent; compare child MO trajectory to parent
- **"behavior depends on scene-graph order"** → DataEngine sits after its consumer

### Classic gotchas to call out explicitly in the playbook

1. SOFA has no default units. mm/g/s implies gravity = 9810 and YM in MPa.
2. `FixedConstraint` does not fix velocity. Drift under `FreeMotionAnimationLoop` is expected.
3. `UncoupledConstraintCorrection` ≠ universal. Don't pair with deformable FEM.
4. Scene-graph order is init order. DataEngines must precede their consumers.
5. Component creation can silently fail when the required plugin isn't loaded — the factory just returns nothing.
6. Bilateral constraints and collision response on the same surface fight each other.

---

## Pending re-runs (after sub-agent permission allowlist setup)

- Agent 2: Empirical Health Rules validation against `~/workspace/sofa/` (needs Bash + Read on that path)
- Agent 3: SOFA closed issues, recent ~24mo (needs `gh` or WebFetch on github.com)
- Agent 5: SOFA discussions Q&A, recent ~18mo (same)
- Agent 6: SOFA discussions Q&A, older / non-Q&A (same — also hit org monthly limit, may be capacity-constrained)
- Agent 7: SOFA docs general (needs WebFetch on sofa-framework.github.io)
- Agent 8: SOFA docs component reference (same)
- Agent 9: SoftRobots + SoftRobots.Inverse issues + discussions (needs `gh` or WebFetch)

Permissions to allowlist before re-running:
- `Bash(gh:*)`
- `Bash(find:*)`, `Bash(grep:*)`, `Bash(ls:*)` for `~/workspace/sofa/`
- `WebFetch(domain:github.com)`
- `WebFetch(domain:api.github.com)`
- `WebFetch(domain:sofa-framework.github.io)`
- `WebFetch(domain:sofa-framework.org)`
- `WebSearch` (already worked for Agent 4 fallback — confirm enabled)
