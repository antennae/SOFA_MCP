# Agent 9 — SoftRobots / SoftRobots.Inverse mining for `diagnose_scene`

**Date:** 2026-04-25
**Scope:** Closed + open issues and Q&A discussions in `SofaDefrost/SoftRobots` and `SofaDefrost/SoftRobots.Inverse`. Mining via WebFetch against the GitHub REST API and HTML pages, plus reading the `QPInverseProblemSolver` C++ sources directly.

## Executive summary

**Yes — `printLog=True` on `QPInverseProblemSolver` produces high-density, diagnostic output, and it is the single most valuable log target for any inverse-actuated SoftRobots scene.** When `f_printLog` is true the solver dumps, every step: total constraint-line count, the full QP system (`W`, `Q`, `A`, `Aeq`, `c`, `bu`, `bl`, `beq`, `l`, `u`, `dfree`), the result vectors (`delta`, `lambda`), and the relative variation of `||Q||_∞` between steps — exactly the data needed to diagnose actuator-not-pulling, ill-conditioning, and effector-unreachable cases. Independent of `printLog`, it always prints the QP backend in use (`"Using proxQP solver"` / `"Using qpOASES solver"`) and the `computeCompliance` constraint-correction count, so a wrong constraint-correction wiring is visible from line 1. Setting `d_displayTime=True` adds per-step build/solve/total-time numbers (stall detector). The spec's `log_solvers=True` default is validated. v1 should also auto-enable `d_displayTime` on this solver.

## Key findings (12)

1. **`QPInverseProblemSolver.printLog` is wired through `f_printLog.getValue()`** — gates `displayQPSystem()`, `displayResult()`, `displayQNormVariation()` calls in `QPInverseProblemSolver.cpp` (lines ~450–454) which in `QPInverseProblem.cpp` emit `msg_info("QPInverseProblem")` lines like `" W = ["`, `" Q = ["`, `" delta = ["`, `" lambda = ["`, `" Q infinity norm : "`, `" Relative variation of infinity norm through one step: "`. **Diagnostic:** lambda stuck at `bu`/`bl` bounds = actuator hitting force limit; lambda all-zero = actuator never engaged; `||Q||_∞` ratio drifting >>1 = ill-conditioned QP. **Fix:** keep `log_solvers=True`, surface the `delta`/`lambda` block in the report.

2. **`QPInverseProblemSolver` exposes `d_objective` (`Data<SReal>`) and `d_graph` (`Data<map<string, vector<SReal>>>`) directly** — programmatically queryable, no log scraping needed. `displayResult` writes to `d_graph` so plotting `iterations` and `objective` per step is free. **Recommendation:** read `d_graph` in `diagnose_scene` instead of regex-parsing the printLog output for inverse scenes.

3. **`actuatorsOnly` and `allowSliding` flags change the QP problem in ways that look like bugs.** With `actuatorsOnly=True` the solver ignores collision constraints in the QP — looks like "robot passes through obstacle" but is intentional. **Diagnostic:** flag these in `scene_summary`.

4. **Inverse-vs-direct solver mismatch — most common cable-not-actuating bug** ([SoftRobots discussion #233](https://github.com/SofaDefrost/SoftRobots/discussions/233)). User imported `softrobots.inverse.actuators.PullingCable` but kept `GenericConstraintSolver`; scene loads, animation does nothing. Maintainer: replace `GenericConstraintSolver` with `QPInverseProblemSolver`. **Symptom:** scene runs but no motion. **Diagnostic:** detect any `PullingCable`/`CableActuator`/`SurfacePressureActuator`/`ForcePointActuator` without a `QPInverseProblemSolver`. → **new smell test `inverse_actuator_without_qp_solver`**.

5. **`SurfacePressureConstraint` value scales with `dt` — silent unit bug** ([SoftRobots #86](https://github.com/SofaDefrost/SoftRobots/issues/86), [#290](https://github.com/SofaDefrost/SoftRobots/issues/290), [discussion #207](https://github.com/SofaDefrost/SoftRobots/discussions/207)). Maintainer EulalieCoevoet: "there is a time step dependency [...] users must divide the value by dt." Same applies to `CableConstraint` reported force (#207: cable force went 40→400 when dt went 0.01→0.1). **Diagnostic:** rerun the scene at 0.5×dt; if reported pressures/forces scale linearly, it's the impulse-vs-force bug. → **new smell test `dt_scaling_violation`**.

6. **Cable-not-moving is almost always a missing `RequiredPlugin`, not a logic bug** ([SoftRobots #150](https://github.com/SofaDefrost/SoftRobots/issues/150), [#42](https://github.com/SofaDefrost/SoftRobots/issues/42), [#229](https://github.com/SofaDefrost/SoftRobots/issues/229)). Component creation silently fails when its plugin is not loaded. **Diagnostic:** scrape `init` stdout for `"This scene is using component defined in plugins but is not importing"`. → ensure `diagnose_scene` surfaces these init warnings into `anomalies`, not just `solver_logs`.

7. **`MeshTopology` reading edges from a Gmsh file crashes hyperelasticity** ([discussion #224](https://github.com/SofaDefrost/SoftRobots/discussions/224)). `TetrahedronHyperelasticityFEMForceField` segfaults during `animate()` if the topology was loaded with `MeshTopology(src='@loader')` from a Gmsh-exported `.vtu`. Fix: `MeshTopology(tetrahedra='@loader.tetrahedra', position='@loader.position')`. → **new playbook entry: "crash on animate, no init error, hyperelastic + .vtu" → switch to explicit-tetrahedra topology**.

8. **Cable fingers do not bend, only pull-point moves — broken `BarycentricMapping`** ([discussion #233](https://github.com/SofaDefrost/SoftRobots/discussions/233) and Agent 4 pattern #8). Cable child MO has wrong/no mapping to parent finger MO; constraint pulls cable points but parent FE mesh sees no force. **Diagnostic:** compare max displacement of cable child MO vs parent FEM MO; if cable >>1 mm and parent <0.01 mm, mapping is the suspect. → **new smell test `child_only_motion`**: detect mapped MO whose parent and child trajectories diverge by >100×.

9. **`UncoupledConstraintCorrection` paired with deformable FEM is a slow-burn bug** (Agent 4 pattern #4 confirmed by [discussion #252](https://github.com/SofaDefrost/SoftRobots/discussions/252)). Inverse problems are especially sensitive — wrongly-paired constraint correction makes the QP `Q` matrix ill-conditioned, which `displayQNormVariation()` lets us *measure*. → **new smell test `q_norm_blowup`**: parse the printLog "Relative variation of infinity norm" line; if any step shows >10× change, flag.

10. **`CableConstraint` with default-zero `minForce` lets the cable push instead of pull** (Agent 4 pattern #9, also implied by [PR #179](https://github.com/SofaDefrost/SoftRobots/issues/179) "smooth cable actuation"). Inverse-problem `CableActuator` has `minForce` as a Data field; if unset, the QP can give negative lambda → cable injects energy. **Diagnostic:** read `lambda` block from QP printLog; if any cable lambda <0, flag. → **new smell test `cable_negative_lambda`**.

11. **MeshVTKLoader rejects numpy float64 transformation values silently** ([SoftRobots #304](https://github.com/SofaDefrost/SoftRobots/issues/304)). Component is created but with default (identity) transform — visual model lands in wrong place. → **playbook addition: when visual and mechanical meshes diverge, grep init logs for `"Could not read value for data field"`**.

12. **`FingerController` Python-side AttributeError on Linux but not Windows** ([SoftRobots #307](https://github.com/SofaDefrost/SoftRobots/issues/307)). `Unable to find attribute: cable` — node-name resolution differs across platforms. Playbook line: "controller AttributeError → check exact node name with `tree`; do not trust the example."

## Recommended additions to smell tests

| Rule | Trigger | Source |
|---|---|---|
| `inverse_actuator_without_qp_solver` | inverse actuator present, no `QPInverseProblemSolver` | Finding 4 |
| `child_only_motion` | mapped child MO max displacement >>100× parent MO | Finding 8 |
| `cable_negative_lambda` | any cable lambda <0 in QP log | Finding 10 |
| `q_norm_blowup` | "Relative variation of infinity norm" >10× on any step | Finding 9 |
| `dt_scaling_violation` | rerun at 0.5dt; constraint force scales linearly | Finding 5 |
| `inverse_objective_not_decreasing` | `d_graph["objective"]` non-decreasing | Finding 2 |
| `actuator_lambda_zero` | all actuator lambdas == 0 every step | Finding 1 |
| `actuatorsOnly_collision_present` | `actuatorsOnly=True` and CollisionPipeline in tree | Finding 3 |

## Recommended additions to playbook

- **"only cable/pull-point moves, finger doesn't bend"** → check BarycentricMapping; compare child vs parent trajectories.
- **"cable/pneumatic actuator does nothing"** → first check the constraint solver is `QPInverseProblemSolver`, not `GenericConstraintSolver`. Then `enable_logs_and_run` on the QP solver and read `lambda`.
- **"force/pressure values change with dt"** → known dt-scaling on `SurfacePressureConstraint`/`CableConstraint`; divide by dt for physical units.
- **"hyperelastic crash on animate"** → swap to `MeshTopology(tetrahedra=..., position=...)` to skip Gmsh edge list.
- **"visual mesh in wrong place"** → grep init logs for `"Could not read value for data field"`; numpy float64 likely.
- **"robot passes through obstacle in inverse scene"** → check `actuatorsOnly` flag; might be intentional.
- **"inverse solver runs but doesn't reach effector"** → read `d_graph["objective"]`; non-decreasing means infeasible target or insufficient actuators.

## Contradictions / corrections to spec and prior agents

- **Spec line 57 lists `QPInverseProblemSolver` in printLog targets — validated. No change.**
- **Agent 1's M5 (parse solver log for iteration count)** is unnecessary for `QPInverseProblemSolver`: `d_graph` exposes `iterations` as structured data. Keep log-parsing as fallback for `NNCGConstraintSolver` only.
- **Agent 1's M4 ("set `verbose=True` if field exists")** does not apply to `QPInverseProblemSolver` — it has neither `verbose` nor `debug`, only `f_printLog` (inherited from `Base`) and `d_displayTime`. Auto-enable `d_displayTime=True` alongside `printLog=True` for this class only.
- **Agent 4 pattern #9 (negative-force CableConstraint)** is the direct-problem equivalent of Finding 10; both should produce a negative-force smell test, reading different fields.
- **The spec's `low_forces` rule (Agent 1 already weakened to `low_assembled_forces`)** is even less reliable for inverse scenes because actuator forces live in `lambda` inside the QP, not in the MO's assembled `f`. For inverse scenes, replace with `actuator_lambda_zero` (Finding 1).
- **Agent 1's recommendation to subprocess-isolate** is reinforced: `QPInverseProblemSolver` allocates qpOASES/proxQP scratch buffers as static/global state in some builds; back-to-back in-process diagnose calls risk stale workspaces.
