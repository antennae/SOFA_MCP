# Rule 5 — Constraint Handling: Deep Review

**Date:** 2026-04-26
**Scope:** v2.1 §1.1 Rule 5, all three sub-checks. Source-verified against SOFA C++ and SoftRobots.Inverse C++.
**Research inputs:** v2.1 spec, Agent 6 (F1, F7), Agent 9 (F4), Agent C (QP source verification), component registry audit, AttachProjectiveConstraint/PairInteractionProjectiveConstraintSet source, Actuator.h base class hierarchy.

---

## 1. Class-registration audit

### Actuators (search: "Actuator") — 13 registered

| Class | Registered | Base class |
|---|---|---|
| `CableActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `SurfacePressureActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `ForcePointActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `ForceSurfaceActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `JointActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `SlidingActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `SlidingForceActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `SmoothSlidingForceActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `SphericalSlidingForceActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `AreaContactSlidingForceActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `ForceLocalizationActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `YoungModulusActuator` | YES | `Actuator<DataTypes>` (SoftRobots.Inverse) |
| `CosseratActuatorConstraint` | YES | `CableModel<DataTypes>` (Cosserat plugin — NOT `Actuator<>` base) |

Key finding: `BeamRestPositionActuator` exists as a header file in SoftRobots.Inverse but is **not registered** in the ObjectFactory (search returns 0 results). `CosseratActuatorConstraint` does NOT inherit from `softrobotsinverse::behavior::Actuator<>` — it inherits from `CableModel` in the base SoftRobots plugin and resolves constraints directly via `ConstraintResolution`, not the QP framework.

### Constraint solvers (search: "ConstraintSolver") — 5 registered

| Class | Registered |
|---|---|
| `NNCGConstraintSolver` | YES |
| `QPInverseProblemSolver` | YES |
| `LCPConstraintSolver` | YES |
| `BlockGaussSeidelConstraintSolver` | YES |
| `ImprovedJacobiConstraintSolver` | YES |
| `UnbuiltGaussSeidelConstraintSolver` | YES |
| `GenericConstraintSolver` | **NO** — NOT registered in this build (confirmed in v2.1 §1.3) |

Auto-created solver: `FreeMotionAnimationLoop.cpp` lines 111–117 confirm the auto-instantiated default is `BlockGaussSeidelConstraintSolver`, not `LCPConstraintSolver`. The v2.1 spec's regex `A ConstraintSolver is required by .* but has not been found` is correct and class-invariant.

### Constraint corrections (search: "ConstraintCorrection") — 4 registered

| Class | Registered |
|---|---|
| `GenericConstraintCorrection` | YES |
| `LinearSolverConstraintCorrection` | YES |
| `PrecomputedConstraintCorrection` | YES |
| `UncoupledConstraintCorrection` | YES |

### Attach (search: "Attach") — relevant result

| Class | Registered |
|---|---|
| `AttachProjectiveConstraint` | YES |
| `AttachBodyButtonSetting` | YES (unrelated) |
| `ConstraintAttachButtonSetting` | YES (unrelated) |
| `AttachConstraint` | **NOT registered** — the old v1 name; correctly replaced with `AttachProjectiveConstraint` in v2.1 |

---

## 2. Sub-check A: Constraint correction in each deformable subtree

### Mechanistic explanation

Agent 6 F1 source (SOFA discussion #2731): a maintainer states that an object failing to move under `FreeMotionAnimationLoop` is "characteristic from a missing ConstraintCorrection." The mechanism: `FreeMotionAnimationLoop` orchestrates free-motion prediction, then constraint resolution, then a correction step. The correction step is applied by the `*ConstraintCorrection` object attached to each MO's subtree. Without it, the constraint forces are computed globally but never projected back onto the mechanical degrees of freedom of that subtree — the body stays frozen.

### Concrete detection algorithm (refined from spec's "not strictly per node")

The spec's phrasing "not strictly per node" is deliberately loose. The correct algorithm is:

1. Walk the scene graph. Identify every **deformable subtree**: a node that contains `MechanicalObject` (any template) AND a deformable force field (`TetrahedronFEMForceField`, `TriangularFEMForceField`, `TetrahedronHyperelasticityFEMForceField`, `HexahedronFEMForceField`, `QuadBendingFEMForceField`, `MeshSpringForceField`, or any class matching `*FEMForceField` or `*ForceField` that is not pure-rigid).
2. **Exempt** nodes whose MechanicalObject is reached via a mechanical mapping (`*Mapping` parent in ancestry) — mapped DOFs inherit their master's constraint correction.
3. For each non-exempt deformable node found in step 1: check whether any `*ConstraintCorrection` is present in that node **or any ancestor up to the root, or any sibling node at the same level under a common parent** (SOFA's constraint correction scoping is per-MO-owner subtree, not strictly per-node; a correction on the parent node covers children that have no independent solver). The simplest safe rule: the deformable subtree must have a `*ConstraintCorrection` **at or above** the node containing the deformable force field, OR **inside** that node.
4. **Scope additionally**: only fire this check when `FreeMotionAnimationLoop` is present in the scene. Under `DefaultAnimationLoop`, there is no Lagrangian constraint step and corrections are irrelevant.

**Practical implementation:** For each deformable node (non-mapped, contains a FEM force field), check `node.getObject('*ConstraintCorrection')` walking up through ancestors. If none found along the path from root to that node, emit the violation.

This is a **static structural check** — it fires before any stepping. Confidence: HIGH (maintainer-sourced, well-documented).

### The `UncoupledConstraintCorrection` footgun

`UncoupledConstraintCorrection` IS a valid correction object and satisfies the "correction present" structural check above. However, it uses a scalar diagonal compliance (from `d_defaultCompliance` or `d_compliance` Data), not the assembled system stiffness matrix. For deformable FEM bodies, this is an approximation that can produce ill-conditioned QP systems (Agent 9 finding #9, confirmed by discussion #252: "Inverse problems are especially sensitive — wrongly-paired constraint correction makes the QP Q matrix ill-conditioned").

This is a **separate smell test** from the structural correction-present check — it is `q_norm_blowup` (§6.A runtime), not a Rule 5 structural sub-check. Rule 5 should only fire on total absence of correction. The `UncoupledConstraintCorrection` + deformable FEM combination is covered by the runtime `q_norm_blowup` smell test, not by the structural sub-check.

---

## 3. Sub-check B: inverse-actuator-needs-QP

### Mechanistic explanation

Agent 9 F4 / Agent C source verification: `QPInverseProblemSolver.cpp` is the only solver that formulates and solves the QP problem `argmin ||W·λ - δ_free||` subject to actuator bounds. Any `softrobotsinverse::behavior::Actuator<>` subclass populates the QP's actuator rows via `buildConstraintMatrix()` and `getConstraintOnLambda()`. When a non-QP solver (`NNCGConstraintSolver`, `BlockGaussSeidelConstraintSolver`, `LCPConstraintSolver`) is used instead, the actuator's constraint rows are still added to the constraint problem, but the solver resolves them as standard bilateral/unilateral constraints — effectively treating the actuator as a fixed-target constraint rather than an energy-minimizing actuator. The scene loads and runs silently; no motion occurs because the solver ignores the inverse logic.

### Which actuator classes truly require QPInverseProblemSolver

All classes that inherit from `softrobotsinverse::behavior::Actuator<DataTypes>` require `QPInverseProblemSolver`. From source audit:

**Confirmed require QP (all in SoftRobots.Inverse, all inherit `Actuator<>`)**:
`CableActuator`, `SurfacePressureActuator`, `ForcePointActuator`, `ForceSurfaceActuator`, `JointActuator`, `SlidingActuator`, `SlidingForceActuator`, `SmoothSlidingForceActuator`, `SphericalSlidingForceActuator`, `AreaContactSlidingForceActuator`, `ForceLocalizationActuator`, `YoungModulusActuator`

**Does NOT require QP (different base class)**:
`CosseratActuatorConstraint` — inherits from `CableModel<DataTypes>` in the base SoftRobots plugin, implements its own `ConstraintResolution`, and resolves using whatever constraint solver is present (forward-compatible). The Cosserat plugin does not depend on SoftRobots.Inverse.

### v2.1 lists only 4 — should it list all 12?

The v2.1 rule lists `CableActuator`, `SurfacePressureActuator`, `ForcePointActuator`, `ForceSurfaceActuator`. The other 8 (`JointActuator`, `SlidingActuator`, `SlidingForceActuator`, `SmoothSlidingForceActuator`, `SphericalSlidingForceActuator`, `AreaContactSlidingForceActuator`, `ForceLocalizationActuator`, `YoungModulusActuator`) are all equally invalid without QP — confirmed by identical `Actuator<>` base class.

**Recommendation:** The implementation should detect any class that is a registered actuator from SoftRobots.Inverse (i.e., any class name ending in `Actuator` that resolves to a SoftRobots.Inverse plugin in the plugin cache, OR is in the explicit set of all 12 listed above). The rule wording in SKILL.md need not enumerate all 12 by name — it can say "any `SoftRobots.Inverse` actuator" with the 4 most common shown as examples.

The detection predicate: `class_name in INVERSE_ACTUATOR_CLASSES` where `INVERSE_ACTUATOR_CLASSES` is the full set of 12, excluding `CosseratActuatorConstraint`.

---

## 4. Sub-check C: AttachProjectiveConstraint template matching

### Source analysis

`AttachProjectiveConstraint` inherits from `PairInteractionProjectiveConstraintSet<DataTypes>` — a **single-template** constraint: both `object1` and `object2` must be `MechanicalObject<DataTypes>` with the same template. Explicitly instantiated types (from header): `Vec3Types`, `Vec2Types`, `Vec1Types`, `Rigid3Types`, `Rigid2Types`.

Template mismatch failure mode (from `PairInteractionProjectiveConstraintSet.h` lines 133–138):

```
arg->logError("Data attribute 'object1' does not point to a valid mechanical state of datatype 'Vec3d'.")
arg->logError("Data attribute 'object2' does not point to a valid mechanical state of datatype 'Vec3d'.")
```

This is emitted via `logError` during the factory's `canCreate()` check. In SOFA, `logError` from `canCreate` causes `Object type [AttachProjectiveConstraint<Vec3d>] was not created` — which **does** match the `factory_or_intersector_warning` regex (`Object type .* was not created`). So template mismatch IS already caught by the existing §6.B regex, but:

1. The error fires **only at runtime init**, not statically.
2. The error message alone does not reveal which templates conflicted.
3. Agent 6 F7 reports the original `AttachConstraint` also silently no-ops or emits `Link name 'mechanicalStates' already used` — the behavior may differ between SOFA versions. The `logError` path is from the current source.

**Static check approach:** Parse the scene source text for `AttachProjectiveConstraint` objects and resolve `object1`/`object2` link paths to their MOs' templates using the static tree walk. If `obj1_template != obj2_template`, emit a warning immediately (static, before subprocess). This is fast and catches the issue before the `factory_or_intersector_warning` fires at runtime.

**Template matching rules from source:**
- `Vec3d ↔ Vec3d`: valid (both bodies are Vec3d-DOF deformable/rigid)
- `Rigid3d ↔ Rigid3d`: valid (both are articulated rigid bodies)
- `Vec3d ↔ Rigid3d`: **INVALID** — factory creation will fail with logError
- Mixed Vec dimensions: also invalid (Vec3d ↔ Vec1d, etc.)

`f_freeRotations=True` and `f_restRotations=True` are only meaningful for `Rigid3Types` — the constraint has specializations for both Rigid3d and Rigid2d in the .inl. For Vec3d, rotational DOFs don't exist, so `f_freeRotations` is a no-op.

---

## 5. Edge cases

### E1. QPInverseProblemSolver with effectors only, no actuators

A scene like `VolumeEffector.py` uses `QPInverseProblemSolver` but the actuator `ForcePointActuator` IS present. The pure effectors-only case (e.g., a scene using `PositionEffector` to define a target but no actuator yet) would pass the structural check — correct behavior, not a false positive. The rule fires only when an `Actuator<>` class is present without QP, not the reverse. QP + effectors-only is valid inverse kinematics (the effectors constrain via the QP, some other mechanism provides motion, e.g., BoundaryCondition). No false positive.

### E2. LCPConstraintSolver with an actuator

`LCPConstraintSolver` is registered. At runtime, the actuator's constraint rows are processed via `ConstraintResolution::resolution()` — the LCP solver calls the actuator's `getConstraintResolution()`, which for `Actuator<>` subclasses tries to set the actuator target as a bilateral constraint. The inverse optimization loop is never executed. Result: scene runs silently, actuator has no effect, no warning. This is exactly the "cable-not-actuating" pattern from Agent 9 F4. Sub-check B correctly fires on this combination.

### E3. Multiple constraint solvers in different subtrees

SOFA allows a constraint solver per subtree (non-root nodes can have their own solver scoped to that subtree via `FreeMotionAnimationLoop`'s `SearchDown` lookup). This is rare but legitimate in multi-physics scenes. Sub-check B's detection algorithm should be **per-deformable-subtree**: for each actuator found, walk upward to find the nearest ancestor constraint solver, and check if it is a QP solver. If a subtree has its own `NNCGConstraintSolver` but the actuator is in that subtree (not the root's QPInverseProblemSolver's scope), it fires correctly. Implementation note: use the same ancestor-walk as the correction check — find the in-scope constraint solver for each actuator node.

### E4. UncoupledConstraintCorrection + deformable FEM

Structural sub-check A passes (correction IS present). The pathology surfaces at runtime as `q_norm_blowup`. This is correctly a separate runtime smell test, not a Rule 5 structural violation. However, the v2.1 SKILL.md guidance could add an info-level note: "prefer `GenericConstraintCorrection` over `UncoupledConstraintCorrection` for deformable FEM nodes in inverse scenes."

### E5. ForceLocalizationActuator / YoungModulusActuator — non-force actuators

`YoungModulusActuator` changes material stiffness to reach an effector goal. It still inherits `Actuator<>` and still requires QPInverseProblemSolver. Confirmed from source: `YoungModulusActuator.h` includes `SoftRobots.Inverse/component/behavior/Actuator.h` and is templated on `Actuator<DataTypes>`. Sub-check B should list it.

---

## 6. Sample scenes

### Should-NOT-trigger (canonical)

1. **`archiv/tri_leg_cables.py`** — `FreeMotionAnimationLoop` + `NNCGConstraintSolver` (forward sim, no actuators) + `GenericConstraintCorrection` per leg node. All three sub-checks pass: correction present, no inverse actuators, no AttachProjectiveConstraint.

2. **`archiv/prostate_chamber.py`** — Same pattern: `FreeMotionAnimationLoop` + `NNCGConstraintSolver` + `GenericConstraintCorrection` on prostate node. Pass.

3. **`SoftRobots.Inverse/examples/.../Diamond.py`** — `FreeMotionAnimationLoop` + `QPInverseProblemSolver` + `GenericConstraintCorrection` on robot node + `CableActuator`. All three sub-checks pass: correction present, actuators have QP, no AttachProjectiveConstraint.

### Should-trigger violations

4. **Sub-check A violation (missing correction):** A scene with `FreeMotionAnimationLoop` + `NNCGConstraintSolver` where the deformable body node has NO `*ConstraintCorrection`. Pattern: `archiv/tri_leg_cables.py` minus the `GenericConstraintCorrection` line. Symptom: "nothing moves." Severity: **error**.

5. **Sub-check B violation (actuator without QP):** A scene using `CableActuator` (or any of the 12 inverse actuator classes) with `NNCGConstraintSolver` instead of `QPInverseProblemSolver`. Pattern: SoftRobots discussion #233 — user keeps `GenericConstraintSolver` (or NNCGConstraintSolver) with inverse actuators. Severity: **error**.

6. **Sub-check C violation (template mismatch):** A scene with `AttachProjectiveConstraint(object1='@Vec3dBody/mstate', object2='@Rigid3dBody/mstate')` where the two MOs have different templates. Static parse detects template mismatch. Runtime: `factory_or_intersector_warning` fires too, but with less context. Severity: **warning** (static check, before init).

---

## 7. Severity per sub-check

| Sub-check | Slug | Severity | Rationale |
|---|---|---|---|
| Correction in each deformable subtree | `freemotion_without_constraintcorrection` | **error** | Maintainer-confirmed: "characteristic" failure. Scene runs but does nothing useful. |
| Inverse actuator without QP | `inverse_actuator_without_qp_solver` | **error** | Scene loads and runs silently; actuator has zero effect. No warning at runtime. High-confidence false negative if not caught. |
| AttachProjectiveConstraint template mismatch | `attach_projective_template_mismatch` | **warning** | Factory creation may fail (caught by `factory_or_intersector_warning` at runtime too), but static detection is faster and more informative. Downgraded from error because the runtime already catches it; the static check adds context. |

---

## 8. Final rule wording (revised v2.1 §1.1 Rule 5)

```
Rule 5 — Constraint Handling.
  Recommend: NNCGConstraintSolver (forward sim), QPInverseProblemSolver (inverse sim),
             GenericConstraintCorrection (safe default for deformable bodies),
             LinearSolverConstraintCorrection for cable/wire scenes (set wire_optimization=1).

  Sub-check A — freemotion_without_constraintcorrection [error]:
    When FreeMotionAnimationLoop is present, every non-mapped deformable subtree
    (any node containing a MechanicalObject + a FEM force field, not reached via
    a mechanical mapping) must have a *ConstraintCorrection at or above it in the
    tree. Valid corrections: GenericConstraintCorrection, LinearSolverConstraintCorrection,
    PrecomputedConstraintCorrection, UncoupledConstraintCorrection.
    Note: UncoupledConstraintCorrection satisfies this structural check but may
    cause QP ill-conditioning in inverse scenes (caught separately by q_norm_blowup).

  Sub-check B — inverse_actuator_without_qp_solver [error]:
    If any SoftRobots.Inverse actuator class is present (CableActuator,
    SurfacePressureActuator, ForcePointActuator, ForceSurfaceActuator, JointActuator,
    SlidingActuator, SlidingForceActuator, SmoothSlidingForceActuator,
    SphericalSlidingForceActuator, AreaContactSlidingForceActuator,
    ForceLocalizationActuator, YoungModulusActuator), the scene must contain
    QPInverseProblemSolver as the in-scope constraint solver for that actuator's subtree.
    CosseratActuatorConstraint is exempt (different base class, forward-compatible).
    Detection: per-actuator-node ancestor walk for constraint solver type.

  Sub-check C — attach_projective_template_mismatch [warning]:
    AttachProjectiveConstraint is a single-template class: both object1 and object2
    must be MechanicalObject with the same DataTypes (Vec3d↔Vec3d, Rigid3d↔Rigid3d,
    etc.). Mixed templates fail factory creation (logError, caught by
    factory_or_intersector_warning at runtime). Static pre-check: resolve the link
    paths, compare MO templates, emit warning immediately.
    Note: Rigid3d-specific features (freeRotations, restRotations) are no-ops on Vec3d.
```

---

## 9. Issues and gaps found in the v2.1 spec

1. **Sub-check B enumerates only 4 of 12 inverse actuator classes.** The rule must list all 12 (or use the plugin-provenance heuristic: any class from the SoftRobots.Inverse plugin). `CosseratActuatorConstraint` is correctly excluded.

2. **Sub-check A detection algorithm is underspecified.** "Not strictly per node" leaves the implementation ambiguous. The algorithm in §2 above provides a concrete definition: non-mapped deformable node, ancestor-walk for correction.

3. **Sub-check C failure mode is NOT a silent no-op** — it fires `logError` via the factory's `canCreate`, which produces an `Object type .* was not created` error caught by `factory_or_intersector_warning`. The static check adds template-specific context the regex cannot provide. Sub-check C and `factory_or_intersector_warning` are complementary, not redundant.

4. **AttachProjectiveConstraint template mismatch error does not overlap `factory_or_intersector_warning`** in the static check — the static check runs before subprocess. At runtime the factory_or_intersector_warning regex does match it. This must be documented so the implementer does not assume static + runtime checks are duplicates.

5. **The `UncoupledConstraintCorrection` + deformable FEM footgun is NOT covered by Rule 5.** It is correctly a runtime smell test (`q_norm_blowup`). The rule wording should add a note pointing there.

---

## 10. Confidence verdict

| Item | Confidence | Source |
|---|---|---|
| All 12 `Actuator<>` classes require QP | HIGH | C++ header audit (base class confirmed) |
| `CosseratActuatorConstraint` is exempt | HIGH | C++ header audit (`CableModel<>`, not `Actuator<>`) |
| `BeamRestPositionActuator` is not registered | HIGH | Component registry search returned 0 |
| Auto-created solver is `BlockGaussSeidel`, not LCP | HIGH | `FreeMotionAnimationLoop.cpp` line 112 |
| Template mismatch fires `logError` via factory | HIGH | `PairInteractionProjectiveConstraintSet.h` lines 133–138 |
| Template mismatch error matches `factory_or_intersector_warning` regex | HIGH | Verified: `Object type .* was not created` is produced by `logError` in `canCreate` |
| `UncoupledConstraintCorrection` satisfies structural check, but not runtime-safe | HIGH | Source + Agent 9 F9 / discussion #252 |
| `GenericConstraintSolver` is NOT registered | HIGH | Component registry, confirmed in v2.1 §1.3 |
| Sub-check A "deformable subtree" definition | MEDIUM | Derived from maintainer statement + agent reasoning; no direct source line specifying the exact scoping algorithm |
| Multiple constraint solvers per subtree edge case | MEDIUM | Inferred from `SearchDown` lookup in FreeMotionAnimationLoop; not tested with actual scene |
