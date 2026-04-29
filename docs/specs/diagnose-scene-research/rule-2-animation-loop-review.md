# Rule 2 — Animation Loop: deep review

**Date:** 2026-04-26  
**Reviewer:** single-rule deep-review agent  
**Verdict:** REFINE — two targeted corrections needed before implementation

---

## 1. Mechanistic explanation (3 sentences)

`Sofa.Simulation.init()` in `Simulation.cpp:91-102` checks `root->getAnimationLoop()`; if null it emits a `msg_warning` and instantiates `DefaultAnimationLoop` silently — so a scene with no explicit loop never crashes but gets constraint handling wrong. `DefaultAnimationLoop.animate()` calls `SolveVisitor(params, dt, useFreeVecIds=false, ...)` which drives each ODE solver to update positions directly in `x`/`v`, completely bypassing the free-motion + constraint-correction pipeline that Lagrange multipliers require. `FreeMotionAnimationLoop.init()` (lines 102-133 of its `.cpp`) searches downward for a `ConstraintSolver` and, when absent, auto-creates a `BlockGaussSeidelConstraintSolver` with a `msg_warning` — an independent footgun that the spec already captures via the `auto_constraint_solver_warning` smell test.

---

## 2. Class-registration audit

### Animation loop classes

| Class | In plugin cache | Plugin | Notes |
|---|---|---|---|
| `FreeMotionAnimationLoop` | YES | `Sofa.Component.AnimationLoop` | Primary constraint loop |
| `DefaultAnimationLoop` | NO (core-builtin) | `sofa.simulation` framework | Registered via `registerDefaultAnimationLoop()` in `Simulation/Core`, not a plugin .so |
| `ConstraintAnimationLoop` | YES | `Sofa.Component.AnimationLoop` | **DEPRECATED** — emits `msg_deprecated` at init: *"use FreeMotionAnimationLoop + GenericConstraintSolver"*; does handle Lagrange internally but ships its own GS solver |
| `MultiStepAnimationLoop` | YES | `Sofa.Component.AnimationLoop` | |
| `MultiTagAnimationLoop` | YES | `Sofa.Component.AnimationLoop` | |

**`DefaultAnimationLoop` is absent from the plugin cache** (`.sofa_mcp_results/.sofa-component-plugin-map.json`) because it lives in the Simulation framework core, not a loadable `.so`. The implementation must add it to the valid-set via `ObjectFactory` enumeration or a hard-coded constant, not by trusting the plugin cache alone.

### "Lagrangian constraint" — concrete class enumeration

All found in plugin cache (from `search_sofa_components`):

**Direct Lagrangian constraint classes (7):**
- `BilateralLagrangianConstraint`
- `FixedLagrangianConstraint`
- `SlidingLagrangianConstraint`
- `StopperLagrangianConstraint`
- `UniformLagrangianConstraint`
- `UnilateralLagrangianConstraint`
- `AugmentedLagrangianConstraint`

**SoftRobots actuators that use Lagrange multipliers internally (from `search_sofa_components('Actuator')`):**
- `CableActuator`
- `SurfacePressureActuator`
- `ForcePointActuator`
- `ForceSurfaceActuator`
- `JointActuator`
- `SlidingActuator` / `SlidingForceActuator` / `SmoothSlidingForceActuator` / `SphericalSlidingForceActuator`
- `AreaContactSlidingForceActuator`
- `ForceLocalizationActuator`
- `CosseratActuatorConstraint`
- `YoungModulusActuator`

**Constraint corrections (presence implies Lagrange use):**
- `GenericConstraintCorrection`, `LinearSolverConstraintCorrection`, `UncoupledConstraintCorrection` — these are only meaningful inside `FreeMotionAnimationLoop`'s two-phase pipeline. Presence of any correction object is a reliable proxy for "this subtree uses Lagrange multipliers."

**Spec's v2.1 enumeration (`CableActuator`, `SurfacePressureActuator`, `ForcePointActuator`, `ForceSurfaceActuator`) is incomplete.** `JointActuator`, `SlidingActuator` family, and `CosseratActuatorConstraint` are also registered actuators. The implementation should pattern-match `*Actuator` OR `*LagrangianConstraint` rather than enumerate by name.

---

## 3. Final rule wording

### Rule 2 — Animation Loop

**Validate:** Accept any of: `FreeMotionAnimationLoop`, `DefaultAnimationLoop`, `MultiStepAnimationLoop`, `MultiTagAnimationLoop`. `ConstraintAnimationLoop` is also registered and technically functional for Lagrange constraints but is deprecated — emit `warning` if present, suggesting migration to `FreeMotionAnimationLoop + GenericConstraintSolver`.

**Correction from v2.1 spec:** `ConstraintAnimationLoop` **does** support Lagrange multipliers (it runs its own internal Gauss-Seidel solver). Accepting it silently in `validate` is wrong — it will not break, but it emits a `msg_deprecated` at init and upstream has deprecated it. Correct action: accept it as valid (no `error`), emit `warning`, suggest migration.

**Sub-checks with severities:**

| Sub-check slug | Severity | Condition |
|---|---|---|
| `no_loop_with_lagrange` | `error` | No explicit animation loop AND scene contains `*LagrangianConstraint`, `*Actuator` (from SoftRobots), or `*ConstraintCorrection` |
| `default_loop_with_lagrange` | `error` | Explicit `DefaultAnimationLoop` AND scene contains any of the above |
| `deprecated_constraint_loop` | `warning` | `ConstraintAnimationLoop` present |
| `free_motion_no_constraint_solver` | `warning` | `FreeMotionAnimationLoop` present AND no `ConstraintSolver` in scene (auto-BGS smell) — already captured by `auto_constraint_solver_warning` in §6.B; reference that instead of duplicating |
| `unknown_animation_loop` | `error` | Animation loop class present but not in the valid set |

**Recommend:** `FreeMotionAnimationLoop` when any Lagrangian constraint, SoftRobots actuator, or constraint correction is present; `DefaultAnimationLoop` otherwise. `FreeMotionAnimationLoop` is **required** — not just recommended — in the constraint case.

---

## 4. Edge cases

### Handled

- **No loop + no Lagrange** — silent `DefaultAnimationLoop` auto-instantiated; no issue. Rule correctly does not trigger. The `no_loop_with_lagrange` sub-check will not fire.
- **Explicit `DefaultAnimationLoop` + Lagrange** — clear `error`. Source confirmed: `DefaultAnimationLoop.animate()` runs `SolveVisitor(useFreeVecIds=false)` which calls `s->solve()` on each ODE solver directly, bypassing the free-motion pass entirely; Lagrange constraints produce zero effect and no runtime error.
- **No loop + Lagrange** — `error`. The auto-instantiated `DefaultAnimationLoop` produces the same silent failure. The `no_loop_with_lagrange` check must scan for constraint markers even when no loop token appears in the source.
- **`ConstraintAnimationLoop` + Lagrange** — works but deprecated; `warning` only.
- **`FreeMotionAnimationLoop` + no constraint solver** — `FreeMotionAnimationLoop.init()` auto-creates `BlockGaussSeidelConstraintSolver` and emits `msg_warning("A ConstraintSolver is required by FreeMotionAnimationLoop but has not been found")`. Captured by §6.B `auto_constraint_solver_warning` smell test. No additional structural sub-check needed.

### Not handled / open

- **Multiple animation loops at different nodes** — SOFA's `root->getAnimationLoop()` returns the first one found; having two is technically legal XML/Python but the second is unreachable. The rule does not currently check for duplicates. Low priority.
- **`ConstraintCorrection` presence as Lagrange proxy** — the spec's trigger list names only 4 actuators. The implementation should use pattern matching (`*ConstraintCorrection` OR `*LagrangianConstraint` OR `*Actuator`) to catch the full set. If using a class-name list instead of patterns, `JointActuator`, `SlidingActuator`, `CosseratActuatorConstraint`, etc. will be missed.
- **`YoungModulusActuator`** — registered as actuator but likely does not use Lagrange multipliers (it modulates material stiffness). Should be excluded from the Lagrange-trigger list unless verified.

---

## 5. Sample scenes

### Should-NOT-trigger (valid)

1. `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/component/engine/VolumeFromTriangles/Finger.py` — explicit `DefaultAnimationLoop`, no Lagrangian constraints, no actuators, no constraint corrections.
2. `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/tutorials/PneunetGripper/details/step5-timeIntegrationAndMatrixSolver.py` — explicit `DefaultAnimationLoop`, no Lagrangian constraints (tutorial step before constraints are added).
3. `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/component/controller/AnimationEditor/RigidAnimation.py` — explicit `DefaultAnimationLoop`, pure rigid animation, no constraints.

### Should-TRIGGER (violations)

1. `/home/sizhe/workspace/sofa/plugins/ModelOrderReduction/examples/organs/liver/liverFine_rotationalActuation.py` — explicit `DefaultAnimationLoop` AND `RequiredPlugin Sofa.Component.Constraint.Lagrangian.Solver` + `Sofa.Component.Constraint.Lagrangian.Correction` are present. Severity: `error` if actual Lagrangian constraint objects are created (requires AST walk, not just plugin-name scan; see note below).
2. `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/tutorials/SoftArmGripper/scene.py` — missing animation loop (no `AnimationLoop` token in `scene.py`) but `CableActuator` is present (via `header.py`). Note: cross-file detection requires resolving imports — difficult for static analysis. Single-file scan may miss this.
3. A deliberately broken test fixture: copy of `archiv/tri_leg_cables.py` with `FreeMotionAnimationLoop` replaced by `DefaultAnimationLoop` — `CableActuator` present in subtree → `error`.

**Note on liver example:** The `RequiredPlugin` scan is a heuristic; what actually matters is whether `addObject('BilateralLagrangianConstraint', ...)` or similar appears. The `liverFine_rotationalActuation.py` scene only loads the plugin but uses `RestShapeSpringsForceField` for actuation — not an actual Lagrangian constraint. A pure regex on plugin names is a false positive source; the check should walk object class names, not required-plugin declarations.

---

## 6. Corrections to v2.1 spec

1. **`ConstraintAnimationLoop` should not appear in the `validate` allowlist without a deprecation flag.** It works but emits `msg_deprecated`. Add it to the allowlist with severity `warning`, not silent `ok`.
2. **`DefaultAnimationLoop` not in plugin cache.** The valid-set check cannot rely solely on the plugin cache to confirm `DefaultAnimationLoop` registration. It must be hard-coded as core-builtin or detected via `ObjectFactory` enumeration.
3. **Lagrange-trigger class list is incomplete.** Spec names 4 actuators. Add at minimum `JointActuator`, `SlidingActuator`, and all `*LagrangianConstraint` classes. Prefer pattern matching over enumeration.
4. **Required-plugin heuristic is unreliable.** The liver example shows a scene that loads `Lagrangian.Solver` plugin but does not create any Lagrangian objects. The detector must walk `addObject` class names, not `RequiredPlugin` names.

---

## 7. Confidence verdict: REFINE

The mechanistic claim is correct and source-verified. Two implementation-blocking corrections are required:

- The `DefaultAnimationLoop` cache-miss must be handled explicitly.
- The Lagrange-trigger class list must be widened (pattern over enumeration) to avoid false negatives.

One spec-wording correction is needed: `ConstraintAnimationLoop` is valid-but-deprecated, not valid-and-silent. Everything else in v2.1 §1.1 Rule 2 holds.
