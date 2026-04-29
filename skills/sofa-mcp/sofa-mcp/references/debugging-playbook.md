# Debugging Playbook — investigating a scene that runs but misbehaves

Use this when the user has an **existing scene that initializes and animates without crashing**, but the behavior is wrong: "the robot doesn't move when I actuate it", "deformation is way too small", "things pass through each other", "the tip overshoots", "it explodes after a few steps".

This is a different problem from authoring. There's no traceback to parse, no missing component to flag from a static check alone. The scene is *physically* wrong. The MCP tools provide probes; the reasoning is yours.

## The investigative loop

```
symptom → structure check → run + measure → form hypothesis → instrument or modify → re-measure
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

### Step 2 — Structure check (cheap, always do this)

Call `summarize_scene(script_content)`. Read the full `checks` list — not just `error`-severity entries, also `warning` and `info`. A scene that passed authoring rules can still drift in the user's edits.

Look for:
- **Rule 9 (units) warnings** — surprisingly common in scenes that "used to work" but were edited. A `youngModulus=5000` in an SI scene means 5 kPa rubber, not 5 GPa steel. Mismatched units explain many "deformation too small/large" symptoms.
- **Rule 5 (constraint handling) errors** — if the user added a `*Constraint` without realizing FreeMotionAnimationLoop / GenericConstraintCorrection is now required.
- **Rule 4 (linear solver scope)** — only-ancestor solvers cause "doesn't move" because the descendant subtree gets no factorization.
- **Rule 6 (force field mapping)** — pair-interaction forces with stale `object1`/`object2` paths silently no-op.

If a Rule fires and you think it's the cause, propose the fix and stop. Don't run a 200-step simulation when a static check has already pointed at the bug.

### Step 3 — Run and measure

Call `run_and_extract(scene_path, steps=N, target_object=...)` to get a JSON trajectory. Pick `steps` to span the symptom: 50–100 for "doesn't move enough", 200+ for instabilities, less if the scene is heavy. `target_object` should be the mechanical state whose behavior the user described.

Then call `process_simulation_data(json_path)` to extract summary statistics — max displacement, position norm over time, NaN/Inf detection, convergence flags.

This gives you the data side. Match it against the symptom from Step 1.

### Step 4 — Match the data to a hypothesis

Common patterns and what they suggest:

| Observation | Likely cause |
|---|---|
| `max_disp < 1e-3` over the run | Unactuated: cable/pressure value=0, actuator wired to wrong indices, or constraint correction missing. Compare to the actuator's `value` field and the indices its `pullPoint`/`triangles` reference. |
| `max_disp` plateaus far below expected | Stiffness too high (`youngModulus`), or boundary constraint pinning too much of the body. Check `FixedProjectiveConstraint`/`RestShapeSpringsForceField` indices vs. the actuator's reach. |
| Position diverges → NaN | Time step too large for the stiffness, integrator wrong (explicit on stiff system), or units mismatch making the system effectively softer than a stable `dt` allows. |
| Converges then drifts after step N | Constraint solver hitting `maxIterations` — increase iterations, tighten `tolerance`, or check for redundant constraints in the same subtree. |
| Visual mesh and mechanical mesh visibly desync | Mapping is broken — `BarycentricMapping` parent/child mismatch, or `OglModel`'s topology is loaded from a different file than the mechanical state. |
| Two collision shapes pass through | Collision pipeline is incomplete (Rule 8) — re-check the 5-cluster setup. Or contact stiffness is too low. |

These are not rules — they are starting points. The data may not match any cleanly, in which case go to Step 5.

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

## Example: "robot doesn't move"

User: "I added a `CableConstraint` to my soft leg with `value=20`, but the tip barely moves."

1. Symptom: tip displacement expected ~15 mm, observed (per user) <1 mm.
2. `summarize_scene` returns rule_5 OK, all rules ok. Structure is fine.
3. `run_and_extract(scene, steps=100, target_object="/Leg_0/mo")`. `process_simulation_data` shows max_disp=0.4 mm.
4. Hypothesis: cable indices don't reach the tip — `tip_indices=[40,41,42,43]` may not be the top of the grid.
5. `find_indices_by_region(mesh, region_box=[top of leg])` returns `[40,41,42,43]` — they ARE the tip. Hypothesis falsified. New hypothesis: cable is attached but the leg subtree has no `GenericConstraintCorrection`. Check: rule_5 said OK; re-read the summary's `objects` list for the subtree → confirms GCC present.
6. New hypothesis: `valueType="displacement"` with a cable that has `maxPositiveDisp=30` and the user expects `value=20` mm of contraction — but the units gravity is `[0,0,-9810]` (mm/g/s) and the scene's youngModulus is in Pa (5000), not in mm/g/s consistent units. Rule 9 SHOULD have caught this; check if `youngModulus` field was on a force field type Rule 9 inspects.
7. Modify: change `youngModulus=5000` → `youngModulus=5e6` (rubber in mm/g/s), re-run. Tip moves ~12 mm. Confirmed.
8. Render before/after — show the user.

The bug was units. Static rules nearly caught it; the data run nailed it.
