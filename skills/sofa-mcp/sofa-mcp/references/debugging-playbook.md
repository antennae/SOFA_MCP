# Debugging Playbook — investigating a scene that runs but misbehaves

Use this when the user has an **existing scene that initializes and animates without crashing**, but the behavior is wrong: "the robot doesn't move when I actuate it", "deformation is way too small", "things pass through each other", "the tip overshoots", "it explodes after a few steps".

This is a different problem from authoring. There's no traceback to parse, no missing component to flag from a static check alone. The scene is *physically* wrong. The MCP tools provide probes; the reasoning is yours.

## The investigative loop

```
symptom → sanity report → run + measure → form hypothesis → instrument or modify → re-measure
```

Don't skip steps. The temptation is to read the file, spot something suspicious, and recommend a fix. That works for authoring bugs; for behavioral bugs it produces guesses that don't reproduce.

### Step 1 — Pin the symptom

Get the user to describe the bug in observable, measurable terms. Push back on vague descriptions:

- ✗ "It's broken" → ask: what did you expect, what did you see?
- ✗ "It doesn't work" → ask: at what step? from initialization, or after some specific input?
- ✓ "When I set cable_displacement=20, the tip moves 0.2 mm but I expect ~15 mm"
- ✓ "Position diverges to 1e8 around step 50 then NaN"
- ✓ "The visual mesh and the FEM mesh stop tracking each other after step 20"

Write the expected vs. observed values down before running anything. They are the falsification target.

### Step 2 — Sanity report (cheap, always do this first)

Call `diagnose_scene(scene_path, steps=N, dt=...)`. This is the unified entry point: it runs `summarize_scene`'s 9 structural Health Rules, then runs the scene in a subprocess for `steps` iterations and folds in runtime + structural smell tests. Pick `steps`: 5–10 for a quick read, 50+ if you want a fuller trajectory. Default `dt` is 0.01.

The response gives you, in one shot:

- `anomalies[]` — Health-Rule checks (slugs `rule_1_plugins` … `rule_9_units`) AND smell-test slugs:
  - `excessive_displacement` (warning ≥10× extent, error ≥100× extent) — primary numerical-blowup detector
  - `solver_iter_cap_hit` — NNCG/BGS hit `maxIterations`; carries `steps_hit_cap: [...]`
  - `inverse_objective_not_decreasing` — QP objective stalled over the last 5 steps
  - `qp_infeasible_in_log` — `QP infeasible` warnings emitted by qpOASES; carries `match_count`
  - `multimapping_node_has_solver` — structural anti-pattern (a `*MultiMapping` and an ODE solver in the same node)
- `metrics.{nan_first_step, max_displacement_per_mo, max_force_per_mo}` — per-MO trajectory summary
- `extents_per_mo`, `solver_iterations`, `objective_series` — raw signals the smell tests are derived from; use them to sanity-check the slugs and reason past their thresholds
- `solver_logs` — captured stdout/stderr from the subprocess, head-and-tail truncated. The full log was scanned by smell tests before truncation, so anything in the elided middle has already been processed

Read the full `anomalies` list — not just `error`-severity. A scene that passed authoring rules can still drift in the user's edits. Especially watch for:

- **Rule 9 (units) warnings** — surprisingly common in scenes that "used to work" but were edited. A `youngModulus=5000` in an SI scene means 5 kPa rubber, not 5 GPa steel. Mismatched units explain many "deformation too small/large" symptoms.
- **Rule 5 (constraint handling) errors** — if the user added a `*Constraint` without realizing FreeMotionAnimationLoop / GenericConstraintCorrection is now required.
- **Rule 4 (linear solver scope)** — only-ancestor solvers cause "doesn't move" because the descendant subtree gets no factorization.
- **Rule 6 (force field mapping)** — pair-interaction forces with stale `object1`/`object2` paths silently no-op.
- **`excessive_displacement` warning** — points at numerical blowup (dt × stiffness too large) or units mismatch making the system effectively softer than `dt` allows. Often co-occurs with Rule 9.
- **`qp_infeasible_in_log`** — actuator bounds, hard equalities, or contact constraints conflict in the QP formulation. Bypasses `printLog` so it surfaces even on default logging.

If an anomaly clearly points at the bug, propose the fix and stop. Don't run a 200-step trajectory when a 5-step sanity report has already pointed at the cause.

### Step 3 — Targeted trajectory (when the sanity report isn't enough)

If `diagnose_scene` ran cleanly but the symptom persists, get a focused trajectory: `run_and_extract(scene_path, steps=N, target_object=...)`. Pick `steps` to span the symptom: 50–100 for "doesn't move enough", 200+ for instabilities, less if the scene is heavy. `target_object` should be the mechanical state whose behavior the user described.

Then `process_simulation_data(json_path)` for summary statistics — max displacement, position norm over time, NaN/Inf detection, convergence flags.

This gives you the data side at higher resolution than the sanity report. Match it against the symptom from Step 1.

### Step 4 — Match the data to a hypothesis

Common patterns and what they suggest. The "Sanity-report signal" column tells you what to look for in the `diagnose_scene` response from Step 2; the "Likely cause" is your starting hypothesis.

| Sanity-report signal | Observation | Likely cause |
|---|---|---|
| `max_displacement_per_mo` near zero, no smell-test fires | `max_disp < 1e-3` over the run | Unactuated: cable/pressure value=0, actuator wired to wrong indices, or constraint correction missing. Compare to the actuator's `value` field and the indices its `pullPoint`/`triangles` reference. |
| `max_displacement_per_mo` low but non-zero, no slug fires | `max_disp` plateaus far below expected | Stiffness too high (`youngModulus`), or boundary constraint pinning too much of the body. Check `FixedProjectiveConstraint`/`RestShapeSpringsForceField` indices vs. the actuator's reach. |
| `excessive_displacement` (error tier) and/or `nan_first_step` set | Position diverges → NaN | Time step too large for the stiffness, integrator wrong (explicit on stiff system), or units mismatch making the system effectively softer than a stable `dt` allows. Co-check Rule 9. |
| `solver_iter_cap_hit` carries `steps_hit_cap: [...]` | Converges then drifts after step N | Constraint solver hit `maxIterations` — raise the cap, tighten `tolerance`, or check for redundant constraints in the same subtree. |
| `inverse_objective_not_decreasing` (warning) | Inverse-problem scene: tip never reaches goal | QP objective stalled. Effector goal may be unreachable from the current actuator bounds, or the actuator coupling to the effector point is too weak. Inspect `objective_series` directly to see the plateau. |
| `qp_infeasible_in_log` (error) with `match_count > 0` | Inverse scene runs but actuation is wrong/zero | Hard QP infeasibility — actuator bounds, hard equalities (`*Equality`), or contact constraints conflict. `minForce > maxForce` is the classic case. |
| `multimapping_node_has_solver` (error) | Anything from "child subtree silently doesn't integrate" to a segfault during animate | A `*MultiMapping` output node can't carry an ODE solver — the visitor detaches output DoFs from parent integration. Move the solver to the input subtrees. |
| No anomaly fires, but mesh visibly desyncs | Visual mesh and mechanical mesh stop tracking | Mapping is broken — `BarycentricMapping` parent/child mismatch, or `OglModel`'s topology is loaded from a different file than the mechanical state. |
| No anomaly fires, but contact pair penetrates | Two collision shapes pass through | Collision pipeline is incomplete (Rule 8) — re-check the 5-cluster setup. Or contact stiffness is too low. |

These are starting points, not rules. The data may not match any cleanly, in which case go to Step 5.

### Step 5 — Instrument or modify to test the hypothesis

Pick one hypothesis. Modify the scene **minimally** to test it:

- **Suspect a stiffness issue?** Halve `youngModulus`, re-run, see if displacement scales as expected.
- **Suspect actuator wiring?** Increase the actuator value 10×, re-run. If displacement also scales 10×, the wiring is fine and the issue is upstream. If displacement stays near zero, the actuator isn't reaching the DOFs you think it is.
- **Suspect units mismatch?** Multiply gravity by 1000 or divide YM by 1000 to see which scales the result toward expected.
- **Suspect a mapping?** Add `printLog=True` on the mapping and the topology container to see what they bind to at init time, then re-`validate_scene` and read the captured stderr.

Use `patch_scene` to apply the minimal change, then `run_and_extract` again. Compare to the previous trajectory. The change in behavior **falsifies or confirms** the hypothesis far more reliably than reading the source.

### Step 6 — Render at key moments

Call `render_scene_snapshot(scene_path, steps=N)` after a hypothesis test to compare visually against the user's mental model. Steps to pick: just before divergence, the moment of the symptom, the final state. A side-by-side of "expected" sketch from the user and your render usually surfaces wrong-axis issues, wrong-direction actuators, and inverted gravity that pure numbers miss.

## What to NOT do

- **Don't recommend a fix without running the modified scene.** "Try setting youngModulus=2000" without measuring is guessing.
- **Don't read the SOFA C++ source.** It's almost never the bug. The bug is in the scene.
- **Don't run 1000 steps when 50 would surface the symptom.** Use the cheapest run that distinguishes hypotheses.
- **Don't rewrite large sections of the scene.** Each modification should isolate one variable.
- **Don't skip `diagnose_scene`** even when you have a strong intuition. The 5–10 step sanity report is cheap, and the smell-test slugs catch silent failures (e.g. `qp_infeasible_in_log`) that an authoring read can't see.

## Example: "robot doesn't move"

User: "I added a `CableConstraint` to my soft leg with `value=20`, but the tip barely moves."

1. Symptom: tip displacement expected ~15 mm, observed (per user) <1 mm.
2. `diagnose_scene(scene, steps=20, dt=0.01)` returns: rule_5 OK, GCC confirmed in subtree; `max_displacement_per_mo = {"/Leg_0/mo": 0.4}`; `extents_per_mo = {"/Leg_0/mo": 100.0}`. No smell-test slugs fire (ratio 0.004 — well below `excessive_displacement` warn threshold). Rule 9 is `ok` because `youngModulus=5000` and `gravity=[0,0,-9810]` both fall inside their per-unit-system tolerances when read individually.
3. Hypothesis: cable indices don't reach the tip — `tip_indices=[40,41,42,43]` may not be the top of the grid. `find_indices_by_region(mesh, region_box=[top of leg])` returns `[40,41,42,43]` — they ARE the tip. Falsified.
4. New hypothesis: units mismatch. Gravity is `-9810` (mm/g/s) but `youngModulus=5000` reads as 5 kPa in either unit system — for an mm/g/s scene the scale should be 5e6 (rubber). Rule 9's per-field check missed it because the magnitudes happened to land in their independent allowed ranges.
5. `patch_scene` to set `youngModulus=5e6`. Re-run `diagnose_scene` — `max_displacement_per_mo = {"/Leg_0/mo": 12.4}`. Hypothesis confirmed.
6. `render_scene_snapshot` before/after — show the user.

The bug was units. The sanity report's raw `extents_per_mo`/`max_displacement_per_mo` numbers (visible alongside the `ok` rules) made the magnitude problem obvious in one tool call.
