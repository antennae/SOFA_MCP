# Design — `diagnose_scene` investigation toolkit

**Date:** 2026-04-25
**Status:** Draft, pending external review (plan review + GitHub issue scout + scene pattern miner)
**Owner:** Sizhe Tian
**Project context:** Phase 6.1 of the SOFA_MCP polish plan (`~/.claude/plans/cosmic-bubbling-salamander.md`). Portfolio piece + research-flavored deliverable for the user's supervisor.

## Problem

A user describes a *behavioral* bug in a SOFA scene in natural language ("the robot doesn't move when I actuate the cable", "deformation way too small", "things pass through each other"). The scene runs without crashing — there is no traceback to parse, no missing component to flag. A rules engine doesn't help.

Goal: give an LLM agent the tools to investigate the bug and find it. The MCP provides good probes; the LLM does the reasoning.

## Non-goals

- A complete diagnostician. The smell tests will be a starter set; we expect them to grow.
- Fixing structural-failure scenes (`validate_scene` already handles "scene won't init"; this is for scenes that init fine but behave wrong).
- Rules-based "the bug is X" output. The agent reads evidence and reasons.

## Architecture (chosen: hybrid)

Three layers:

1. **Sanity report** — single MCP tool, the entry point. Runs the scene, captures metrics, flags anomalies, **defaults to enabling `printLog=True` on integrators / linear solvers / constraint solvers** (highest information density per byte in SOFA).
2. **Probe library** — small focused tools the agent calls based on the report and the playbook.
3. **Playbook** — a methodology section in `SKILL.md` that maps complaint patterns to investigation recipes.

```
diagnose_scene(scene_path, complaint, steps)
      ↓
   sanity report  (per-step metrics + smell tests + solver logs)
      ↓
   anomalies + metrics + logs
      ↓
   agent reads SKILL playbook  →  picks probe to dig deeper
                                       ↓
                                  enable_logs_and_run
                                  read_field_trajectory  (existing run_and_extract)
                                  compare_scenes
                                  perturb_and_run
```

## API: `diagnose_scene`

```python
diagnose_scene(
    scene_path: str,
    complaint: str = None,        # optional natural-language hint
    steps: int = 200,
    dt: float = 0.01,
    log_solvers: bool = True,     # auto-enable printLog on solvers (default ON)
) -> dict
```

**Behavior:**
1. Load scene module via `importlib` (same pattern as `stepping.py`, `renderer.py`).
2. Walk the scene tree; if `log_solvers`, set `printLog=True` on every component matching one of: `EulerImplicitSolver`, `RungeKutta4Solver`, `SparseLDLSolver`, `CGLinearSolver`, `SparseDirectSolver`, `NNCGConstraintSolver`, `LCPConstraintSolver`, `BlockGaussSeidelConstraintSolver`, `QPInverseProblemSolver`. (List should be configurable / auto-discovered.)
3. Init + animate N steps, capturing stdout/stderr in a wrapped subprocess (or in-process with redirect).
4. At every step, capture per-`MechanicalObject`: position, velocity. Per-`ForceField`: max force magnitude. Per-`ConstraintSolver`: iteration count. Energy if available.
5. Run smell tests against the trajectory.
6. Return structured report.

**Return shape:**
```json
{
  "success": true,
  "metrics": {
    "max_displacement_per_mo": {"/leg_0/mo": 0.001, "/leg_1/mo": 0.005, ...},
    "max_force_per_ff": {...},
    "energy_trajectory": [...],
    "constraint_solver_iterations": [...],
    "nan_inf_detected": false
  },
  "anomalies": [
    {
      "severity": "warning",
      "rule": "low_displacement",
      "subject": "/leg_0/mo",
      "message": "MechanicalObject /leg_0/mo moved <0.01mm over 200 steps — actuators may be inactive.",
      "suggested_probe": "enable_logs_and_run on /leg_0/cable_0"
    }
  ],
  "solver_logs": "<captured stdout, truncated at 50KB>",
  "scene_summary": {"node_count": 4, "class_counts": {...}}
}
```

## Smell tests (starter set)

| Rule | Trigger | Likely meaning |
|---|---|---|
| `nan_inf_detected` | any field NaN/inf | numerical explosion / singular matrix |
| `low_displacement` | max disp per MO < threshold | actuator inactive / forces too small / overdamped |
| `excessive_displacement` | max disp > threshold | numerical instability / scale mismatch |
| `low_forces` | all forces ~0 in a forcefield | material params zero, mapping broken, or actuator never engaged |
| `solver_iter_cap_hit` | constraint iters == maxIter every step | underconstrained / poorly scaled |
| `monotonic_energy_growth` | KE strictly increasing over trajectory | energy injection bug / explicit method instability |
| `mo_static` | individual MO has 0 motion across all steps | dead component / mismapped / fixed when shouldn't be |
| `visual_mechanical_diff` | OglModel positions != mapped MO positions | broken Mapping (Identity vs Barycentric mismatch) |

**Known gap:** the list is empirical; review by GitHub-issue-scout agent should suggest additions based on real-world SOFA bug reports.

## Probe library — v1

| Probe | Purpose | Estimated lines |
|---|---|---|
| `enable_logs_and_run(scene_path, log_targets, steps)` | Toggle `printLog=True` on specific components by class name or node path; run; return logs | ~80 |
| `read_field_trajectory` | Already exists as `run_and_extract` — reuse | 0 |
| `compare_scenes(scene_a_path, scene_b_path)` | Diff two scene files structurally | ~60 |
| `perturb_and_run(scene_path, parameter_changes, steps)` | Patch fields temporarily, run, return metrics | ~100 |

**v2 (later, if v1 doesn't cover real cases):**
- `bisect_scene` — strip components, add back to find trigger. Slow, last resort.
- `read_internal_forces` — direct elastic force access. May be subsumed by `enable_logs_and_run` on the ForceField.

## Playbook (added to `SKILL.md`)

```markdown
## Debugging Playbook

When the user reports a behavioral bug, follow this loop:

1. Call `diagnose_scene(scene_path, complaint)`. Read `anomalies` and `solver_logs`.
2. Pick a hypothesis from the table below based on the strongest anomaly.
3. Call the suggested probe to confirm or refute.
4. If confirmed, propose a fix (component addition, parameter change, plugin load).

| User complaint                   | First check                          | Confirm with                                 |
|----------------------------------|--------------------------------------|----------------------------------------------|
| "nothing moves / no actuation"   | sanity report → `low_forces` flag    | `enable_logs_and_run` on actuator + solver   |
| "explodes / NaN"                 | sanity report → `nan_inf_detected`   | reduce dt, then `enable_logs_and_run` on integrator |
| "passes through itself"          | check for collision components       | `enable_logs_and_run` on collision pipeline  |
| "deformation way too small"      | sanity report → `low_displacement`   | `perturb_and_run` with reduced Young's modulus |
| "visual lags mechanical"         | sanity report → `visual_mechanical_diff` | `enable_logs_and_run` on the Mapping        |
| "scene A works, B doesn't"       | `compare_scenes(A, B)` first         | then `diagnose_scene` on B                   |
```

## Files to create / modify

**Create:**
- `sofa_mcp/architect/diagnostics.py` — `diagnose_scene` orchestrator + smell test rules
- `sofa_mcp/architect/probes.py` — `enable_logs_and_run`, `compare_scenes`, `perturb_and_run`
- `test/test_architect/test_diagnostics.py` — table-driven tests for smell tests
- `test/test_architect/test_probes.py` — tests for individual probes

**Modify:**
- `sofa_mcp/server.py` — register the new tools
- `skills/sofa-mcp/sofa-mcp/SKILL.md` — add the Playbook section
- `README.md` — mention the toolkit in the "What's inside" table

## Estimated effort

~600 lines total: 200 for sanity report + smell tests, 80 for `enable_logs_and_run`, 100 for `compare_scenes` + `perturb_and_run`, 40 for SKILL playbook section, plus tests.

## Verification (M5 milestone)

User feeds the toolkit 3-4 scenes with known behavioral bugs (cables not actuated, wrong material modulus, missing collision pipeline, broken Mapping). For each: does the agent (a) see the right anomaly in the sanity report, (b) propose a hypothesis a human SOFA dev would also propose, (c) verify by running the right follow-up probe?

Bar: "the agent acts like a junior SOFA dev with no help, not like a stochastic parrot."

## Open questions / things to validate before implementation

1. **Are the smell tests the right starter set?** GitHub issue scout agent → identify real failure modes from upstream issues.
2. **Are the Health Rules referenced in `SKILL.md` correct and complete?** Scene pattern miner agent → empirically validate from `~/workspace/sofa/` examples.
3. **Does enabling `printLog=True` post-construction actually work?** Most SOFA components have it as a Data field, but timing matters — set it before `init()`. Need to verify.
4. **In-process vs subprocess execution:** `stepping.py` and `renderer.py` currently load in-process; long-running diagnose calls might benefit from subprocess isolation. Review later.
5. **Solver-log capture:** SOFA logs may exceed 50KB easily. Need a sensible truncation/summarization strategy that keeps the most diagnostic content.
