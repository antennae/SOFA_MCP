# `diagnose_scene` v2.1 — Implementation plan

**Date:** 2026-04-26 (v2.1.1 revision: same date; v2.1.2 restructure: same date — Step 1 narrowed to docs-only). 2026-04-29: Step 2 implementation plan drafted (this revision).
**Status:** **Step 1 (docs) ✅ shipped 2026-04-26.** **Step 1.5 (`summarize_scene` rule enforcement) ✅ shipped 2026-04-26 with 1.5+ transport hardening shipped 2026-04-28.** See `docs/progress.md` for the completion log. Step 2 plan ready (see §Step 2 below) — implementation pending user approval. Steps 3-5 await individual review.
**Supersedes:** v2 (`diagnose-scene-research/2026-04-25-diagnose-scene-design-v2.md`).
**Research inputs** (full analysis, citations, corpus stats): `diagnose-scene-research/` — Agents 1–9 review reports + v2 review + smell-test generality review + 4-agent team validation (A: locking literature, B: structural rule corpus, C: QP source verification, D: regex source verification).

## What changed in v2.1

The 4-agent team validation caught **5 breaking errors in v2** and tightened thresholds across the board. Net changes from v2:

- **3 unregistered class names** dropped/replaced: `AttachConstraint` → `AttachProjectiveConstraint`; `PullingCable` (Python prefab) → registered actuators (`CableActuator`, `SurfacePressureActuator`, `ForcePointActuator`, `ForceSurfaceActuator`); regex `'0+'` (pybind artifact, not SOFA emit) → `Link update failed for .+ = @|Could not read link from`.
- **Auto-LCP regex**: `LCPConstraintSolver` → `BlockGaussSeidelConstraintSolver` (current SOFA auto-creates BGS, not LCP). Use class-invariant regex `A ConstraintSolver is required by .* but has not been found`.
- **`d_graph` key names corrected**: `"iterations"`/`"objective"` → `"Last Iterations:"`/`"Last Objective:"` (verified in `QPInverseProblemSolver.cpp`). Use `d_objective` `Data<SReal>` instead — cleaner programmatic source.
- **`child_only_motion` guard**: added `parent_max_disp > 1mm` to prevent infinite-ratio false positives on fully-fixed parents (B5).
- **Shell-FEM exemption** added to BarycentricMapping topology check (B1).
- **High-poisson rule** confirmed STRONG ADD with tiered thresholds 0.45 / 0.49 / 0.499 (Agent A literature review with 6 citations).
- **Units rule**: gravity magnitude is the discriminator; YM thresholds are gravity-system-dependent (B6).
- **Topology-changing-with-static-indices rule dropped** entirely — corpus shows the actual bug pattern doesn't exist in any scene (B4: 100% FP under any practical detector).
- **Backend log strings ARE gated by `printLog`** (Agent C): `printLog=True` must be set *before* `Sofa.Simulation.init()`. Affects subprocess wrapper sequencing.
- **WARN-level catch-all** confirmed via `MessageFormatter.cpp`: `^\[(WARNING|ERROR|FATAL)\]` is universal across SOFA versions.

> **Numbering note (2026-04-26):** the spec keeps Rule 1-12 numbering to preserve traceability with the multi-agent review history (Rules 8/9 demoted to references, Rule 12 moved to Step 3 §6.C). `SKILL.md` uses clean 1-9 numbering for the 9 enforced rules. Cross-reference: spec Rule 10 = SKILL.md Rule 8 (collision); spec Rule 11 = SKILL.md Rule 9 (units).

## Changes in v2.1.1 (after 12-agent rule deep review)

The rule-by-rule deep-review fleet (10 Sonnet agents covering Rules 1-6, 8-11, plus the prior Rules 7 and 12 reviews) caught **9 more concrete bugs and missing pieces** in §1.1. All edits below trace to a per-rule review in `diagnose-scene-research/rule-{N}-*-review.md`.

- **Rule 1** — added core-builtin exemption list (only `DefaultAnimationLoop` and `RequiredPlugin` are truly creatable-without-plugin); documented the `get_plugins_for_components` "not in cache" string contract.
- **Rule 2** — Lagrange-trigger switched from 4-class enumeration to **pattern matching** (`*LagrangianConstraint|*Actuator|*ConstraintCorrection`); `ConstraintAnimationLoop` flagged as deprecated (warning); detection walks `addObject` class names not RequiredPlugin declarations; sub-checks now have explicit severities.
- **Rule 3** — added 3 missing integrators (`BDFOdeSolver`, `RungeKutta2Solver`, `NewtonRaphsonSolver`); flipped alternative recommendation `RungeKutta4Solver` → `EulerExplicitSolver` (4× upstream prevalence: 94 vs 24); added static-collider exemption.
- **Rule 4** — dropped the "100k nodes" CG-vs-LDL threshold (corpus shows the split is structural-role-based: FEM body vs effector target with `firstOrder=True`, not mesh-size); added `SearchDown` scope constraint (linear solver in *ancestor* does not satisfy a child ODE solver); expanded validate set to 11 registered classes.
- **Rule 5** — sub-check B switched from class-name enumeration to **plugin-attribution detection** (any class from `SoftRobots.Inverse` plugin other than `QPInverseProblemSolver` triggers the rule). Auto-covers all current and future inverse components — Actuators, Effectors, Equalities, Sensors. `CosseratActuatorConstraint` exempt automatically (different plugin). Concrete "deformable subtree" definition added for sub-check A.
- **Rule 6** — added **PairInteraction/MixedInteraction exemption** (~13 classes including `SpringForceField`, `JointSpringForceField`); detection uses non-empty `object1` Data field. Without this exemption, every spring scene false-positives.
- **Rule 7** — added 3 missing FEM exemptions (`TriangleFEMForceField` singular, `TriangularFEMForceFieldOptim`, `TriangularAnisotropicFEMForceField`) — without these, official SOFA tutorial `TutorialForceFieldLiverTriangleFEM.scn` false-positives. `MeshTopology` made conditional on loader file extension.
- **Rules 8, 9 — demoted to reference-only.** Visual-model and visual-style guidance moves to `SKILL.md` as authoring tips, not as `summarize_scene` checks. Both were `info`-severity cosmetic rules adding noise without diagnostic value (30%+ scenes are legitimately headless, displayFlags is GUI-only).
- **Rule 10** — **added `ParallelBruteForceBroadPhase` and `ParallelBVHNarrowPhase`** to allow-list (the project's own canonical scene `RobSouple-SOFA/projet.py` uses them; without this fix the rule false-positives on it). Added `RuleBasedContactManager`, `IncrSAP`, `DirectSAP`, `NewProximityIntersection`, `CCDTightInclusionIntersection`. Intersection-method severity downgraded `error` → `info` (runtime auto-fallback to `DiscreteIntersection`).
- **Rule 11** — added 4 missing gravity edge cases: digit-transposition typo `[9100, 9200]` (warning, suggest -9810), cm/g/s `[970, 990]` (info), zero gravity `0 0 0` (skip checks), no declaration (default SI). Magnitude computation made axis-agnostic.
- **Rule 12 — moved from `summarize_scene` to `diagnose_scene`-only** (Step 3 §6.C, new pre-step structural smell test category). The multimapping-output-has-solver pattern is too niche (24 upstream uses, 0 false positives but also 0 in-corpus violators) for scene authors using `summarize_scene` to see; only relevant when investigating an already-broken scene. Class-list corrections still apply: removed `BeamMultiMapping`/`RigidMultiMapping` (don't exist), added `CenterOfMassMultiMapping`, scoped "forbidden" to `core::behavior::OdeSolver` subclasses.

## Architecture (brief)

Same shape as v2:

```
diagnose_scene(scene_path, complaint, steps)
      ↓
   summarize_scene(script_content)             ← structural Health-Rule checks (Step 1)
      ↓
   subprocess: load scene, mutate logging Data fields, init, animate (Step 2)
      ↓
   sanity report = anomalies (from summarize_scene + smell tests) + metrics + truncated logs
      ↓
   agent reads SKILL playbook → picks probe to dig deeper
                                       ↓
                               enable_logs_and_run, compare_scenes,
                               perturb_and_run, scan_init_stdout (Step 4)
```

`diagnose_scene` runs in a `~/venv/bin/python` subprocess for isolation (Agent 1 B1, B2). All structural checks live in `summarize_scene` (single source of truth, benefits both scene authors and bug investigators).

---

# Step 1 — Health Rules documentation update (DOCS-ONLY)

**Goal:** Rewrite the Architect's Checklist in `SKILL.md` so it reflects the v2.1.1 rule set. Update `CLAUDE.md` conventions and validated-class list. **No source-code changes** — `summarize_scene`'s implementation is unchanged in this step (its current 3-boolean output remains the contract). This step delivers immediate value to the LLM agent's authoring guidance: scenes Claude generates from now on follow the corrected rule set.

**Files:**
- Modify `skills/sofa-mcp/sofa-mcp/SKILL.md` — Health Rules section (revise rules 2/3/5/7/9, add 10/11, drop mm/g/s convention; add §1.3 visual-reference paragraph for demoted rules 8/9).
- Modify `CLAUDE.md` — drop mm/g/s convention; fix validated-class list (drop `SparseDirectSolver`, `FixedConstraint` → `FixedProjectiveConstraint`, `DefaultContactManager` → `CollisionResponse`, drop `GenericConstraintSolver`).

**NOT in this step:** any modification to `sofa_mcp/architect/scene_writer.py`, `summarize_scene`, or any Python code. Those land in Step 2 (newly split out, awaiting review).

**Deliverables:**

### 1.1 Revised Scene Health Rules (SKILL.md)

Each rule keeps the `Recommend / Validate / Discovery escape` structure introduced in v2.

All entries below cite their per-rule review file under `diagnose-scene-research/`.

- **Rule 1 — Plugins.**
  - *Validate:* every component class has a corresponding `RequiredPlugin` (resolve via `get_plugins_for_components`).
  - *Mechanism:* missing plugin → `ObjectFactory::createObject()` returns `nullptr` → SofaPython3 raises `ValueError` at scene load. Hard failure, not silent.
  - *Core-builtin exemptions* (don't need RequiredPlugin, not in plugin cache): `DefaultAnimationLoop`, `RequiredPlugin` itself.
  - *`get_plugins_for_components` contract:* unknown class → returns string `"Component not found in cache"`. Treat that as `error` for unrecognized class names; treat the two core-builtins above as silent `ok`.
  - *Severity:* `error`.
  - *Source:* `rule-1-plugins-review.md`.
- **Rule 2 — Animation Loop.**
  - *Recommend:* `FreeMotionAnimationLoop` when any **Lagrangian-pattern** class is present; `DefaultAnimationLoop` otherwise. The Lagrangian pattern matches class names ending in `LagrangianConstraint`, `Actuator` (SoftRobots/SoftRobots.Inverse), or `ConstraintCorrection`.
  - *Detection:* walk `addObject` class names — NOT `RequiredPlugin` declarations (a scene can declare a plugin without using its classes).
  - *Validate set:* {`FreeMotionAnimationLoop`, `DefaultAnimationLoop` (core-builtin, not in plugin cache), `ConstraintAnimationLoop` (deprecated upstream), `MultiStepAnimationLoop`, `MultiTagAnimationLoop`}.
  - *Sub-checks (severities):*
    - `no_loop_with_lagrange` (`error`): no loop + any Lagrangian-pattern class
    - `default_loop_with_lagrange` (`error`): explicit `DefaultAnimationLoop` + Lagrangian-pattern class
    - `deprecated_constraint_loop` (`warning`): `ConstraintAnimationLoop` present
    - `unknown_animation_loop` (`error`): loop class outside the validate set
  - *Mechanism:* `Simulation.cpp:91-102` auto-instantiates `DefaultAnimationLoop` if none declared; `DefaultAnimationLoop.animate()` drives `SolveVisitor(useFreeVecIds=false)` — Lagrange multipliers produce zero force with no runtime error.
  - *Source:* `rule-2-animation-loop-review.md`.
- **Rule 3 — Time Integration Solver.**
  - *Recommend:* `EulerImplicitSolver` for almost everything (~88% upstream); `EulerExplicitSolver` for explicit dynamics (94 upstream uses, 4× more prevalent than `RungeKutta4Solver` — earlier draft had this backwards).
  - *Validate set (10 registered integrators):* `EulerImplicitSolver`, `EulerExplicitSolver`, `RungeKutta2Solver`, `RungeKutta4Solver`, `NewmarkImplicitSolver`, `BDFOdeSolver`, `NewtonRaphsonSolver`, `StaticSolver`, `VariationalSymplecticSolver`, `CentralDifferenceSolver`.
  - *Exemptions:*
    - **Mapped MOs** — detect via `node.mechanicalMapping != nullptr` (any `*Mapping` or `*MultiMapping` in the node). A mapped MO inherits dynamics from its parent solver.
    - **Static colliders** — MOs paired with `*CollisionModel simulated="false"`.
  - *Severity:* `error` — unmapped MO with no solver in ancestry is silently frozen (no NaN, no log, just zero motion).
  - *Source:* `rule-3-time-integration-review.md`.
- **Rule 4 — Linear Solver.**
  - *Recommend:* `SparseLDLSolver` with `template="CompressedRowSparseMatrixMat3x3d"` for FEM bodies (MO template = Vec3d). `CGLinearSolver` is the appropriate default for **effector/goal nodes** (single-point MOs with `firstOrder=True`, common in SoftRobots.Inverse). Drop the v1's "100k nodes" threshold — corpus shows the CG-vs-LDL split is structural-role-based, not mesh-size-based.
  - *Validate set (11 registered):* `SparseLDLSolver`, `AsyncSparseLDLSolver`, `EigenSimplicialLDLT`, `CGLinearSolver`, `PCGLinearSolver`, `ParallelCGLinearSolver`, `BTDLinearSolver`, `MinResLinearSolver`, `SVDLinearSolver`, `CholeskySolver`, `PrecomputedLinearSolver`. Confirmed NOT registered (drop): `SparseDirectSolver`, `SparseLUSolver`, `SparseCholeskySolver`.
  - *Scope constraint (critical):* `EulerImplicitSolver` resolves linear solver via `getContext()->get<LinearSolver>(SearchDown)` — a linear solver in an *ancestor* node does **NOT** satisfy. Must be in the same node or a descendant of the ODE solver.
  - *Asymmetric matrices:* no in-build remediation (`SparseLUSolver` not registered). Suggested fix: align topologies or use `SubsetMultiMapping`. Smell test fires `warning` only.
  - *Mechanism:* missing linear solver under implicit ODE → `[ERROR] A linear solver is required` + `ComponentState::Invalid` → segfault on first animate (not silent).
  - *Severity:* `error`.
  - *Source:* `rule-4-linear-solver-review.md`.
- **Rule 5 — Constraint Handling.**
  - *Recommend:* `NNCGConstraintSolver` (forward), `QPInverseProblemSolver` (inverse), `GenericConstraintCorrection` (safe correction default), `LinearSolverConstraintCorrection` for cable/wire scenes (set `wire_optimization=1`).
  - *Sub-check A — constraint correction in deformable subtree* (`error`): `FreeMotionAnimationLoop` present AND any non-mapped node containing `MechanicalObject` + `*FEMForceField` has no `*ConstraintCorrection` on the ancestor path from root to that node.
  - *Sub-check B — inverse-component-needs-QP* (`error`): **detect by plugin attribution.** For each `addObject` class name, look up its plugin via the plugin cache; if the plugin is `SoftRobots.Inverse` and the class is not `QPInverseProblemSolver` itself, then `QPInverseProblemSolver` must be at root. Auto-covers Actuators, Effectors, Equalities, Sensors, and any future additions to the plugin without spec churn. `CosseratActuatorConstraint` is automatically exempt (different plugin).
  - *Sub-check C — `AttachProjectiveConstraint` template match* (`warning`): `AttachProjectiveConstraint` is `PairInteractionProjectiveConstraintSet<DataTypes>` — both linked MOs must share template. Mixed (Vec3d↔Rigid3d) fails in `canCreate()`. Static check is complementary to §6.B `factory_or_intersector_warning`.
  - *Note on UCC + FEM:* `UncoupledConstraintCorrection` + deformable FEM passes Sub-check A structurally but produces ill-conditioned QP matrices — captured by runtime `q_norm_blowup` smell test (§6.A), not Rule 5.
  - *Source:* `rule-5-constraint-handling-review.md`.
- **Rule 6 — ForceField Mapping.**
  - *Validate:* every single-MO `ForceField` class must have a `MechanicalObject` somewhere in its ancestor chain (SOFA's `SearchParents` walk).
  - *Exemption:* `PairInteractionForceField` and `MixedInteractionForceField` subclasses (~13 classes including `SpringForceField`, `MeshSpringForceField`, `JointSpringForceField`, `GearSpringForceField`, `InteractionEllipsoidForceField`) — these use explicit `object1`/`object2` Data fields and can legitimately live at a common ancestor without a local MO. **Detection: skip the rule if `object1` Data field is non-empty.**
  - *Severity:* `error` if no MO in ancestor chain (matches SOFA init-time error). `warning` if MO exists only in an ancestor and the current node has visual-only components — silent-success case SOFA init does NOT catch.
  - *Source:* `rule-6-forcefield-mapping-review.md`.
- **Rule 7 — Topology Containers (extended).**
  - Volumetric force fields require typed containers (`TetrahedronSetTopologyContainer`, `HexahedronSetTopologyContainer`, `*GridTopology` 3D) OR `MeshTopology` (volumetric only).
  - *BarycentricMapping parent topology check*: parent node must have a volumetric topology container.
  - *Shell-FEM exemption set (verified registered in this build):* `TriangularFEMForceField`, **`TriangleFEMForceField`** (singular form was missing in v2 — its absence false-positives on official SOFA tutorial `TutorialForceFieldLiverTriangleFEM.scn`), **`TriangularFEMForceFieldOptim`**, **`TriangularAnisotropicFEMForceField`**, `QuadBendingFEMForceField`. (`TriangularBendingFEMForceField` was in earlier drafts as a defensive Shell-plugin add — dropped 2026-04-26 docs verification: not registered in this build, Shell plugin not loaded.)
  - *`MeshTopology` is conditionally safe* — verify the linked loader's file extension: `.obj`/`.stl`/`.ply` → fire `warning` (surface-only); `.msh`/`.vtk`/`.vtu` → suppress (volumetric); unknown → fire `info`.
  - *Deferred to v2.2:* (a) 2D `RegularGridTopology`/`SparseGridTopology` false-negative; (b) cross-ancestry BarycentricMapping (`input="@../../other/MO"`).
  - *Severity:* `warning`.
  - *Source:* `rule-7-barycentric-review.md`.
- **Rules 8 + 9 — demoted to reference-only authoring tips in `SKILL.md`** (not `summarize_scene` checks). See §1.3 below. Sources: `rule-8-visual-model-review.md`, `rule-9-visual-style-review.md` (full mechanism + class-registration audit retained for future reactivation if needed).
- **Rule 10 — Collision pipeline (NEW).**
  - If any node has a `*CollisionModel`, the root needs a 5-component cluster. Per-slot validate sets:
    - **Pipeline:** `CollisionPipeline`
    - **Broad phase:** `BruteForceBroadPhase`, **`ParallelBruteForceBroadPhase`**, `IncrSAP`, `DirectSAP`
    - **Narrow phase:** `BVHNarrowPhase`, **`ParallelBVHNarrowPhase`**
    - **Intersection method:** `MinProximityIntersection`, `LocalMinDistance`, `NewProximityIntersection`, `CCDTightInclusionIntersection`, `DiscreteIntersection`
    - **Contact manager:** `CollisionResponse`, **`RuleBasedContactManager`** (subclass; used in Cosserat `NeedleInsertion.py`)
  - *Bullet exemption:* scenes with `RequiredPlugin BulletCollisionDetection` skip the broad+narrow phase checks — Bullet coexists with `CollisionPipeline` and fills broad-phase slot internally.
  - *Static-collider note:* `simulated=False` collision models still participate in detection; rule still fires.
  - *Severity:* `error` for missing pipeline / broad / narrow / contact-manager slots (silent failure each); **`info` for missing intersection method** (runtime auto-fallback to `DiscreteIntersection`).
  - **Critical fix from v2:** the parallel broad/narrow classes were missing from the v2 wording — without them the rule false-positives on the project's own `RobSouple-SOFA/projet.py`.
  - *Source:* `rule-10-collision-pipeline-review.md`.
- **Rule 11 — Units consistency (NEW).** Replaces the mm/g/s convention.
  - *Detect unit system from gravity magnitude* (`sqrt(gx² + gy² + gz²)`, axis-agnostic):
    - magnitude in [9.5, 10.5] → SI; flag `youngModulus < 100` (warning), `< 10` (error)
    - magnitude in [9700, 9900] → mm/g/s; flag `youngModulus > 1e9` (warning)
    - magnitude in [970, 990] → cm/g/s (~29 corpus scenes); info note, skip YM checks
    - magnitude in [9100, 9200] → likely **digit-transposition typo** of -9810; warning ("Did you mean -9810?")
    - magnitude == 0 (`gravity="0 0 0"`, ~171 corpus files) → info, skip YM checks
    - no `gravity` declaration → SOFA defaults to `(0, -9.81, 0)`; treat as SI
    - magnitude in [90, 200] → ambiguous unit system, info
  - *Density sub-check* deferred to v2.2 (most scenes use `totalMass`, not `massDensity`; insufficient corpus signal).
  - *Poisson ratio* explicitly excluded — dimensionless.
  - *Implementation:* ~83 LOC.
  - *Source:* `rule-11-units-consistency-review.md`.
- **Rule 12 — moved to Step 3 §6.C** (`diagnose_scene`-only pre-step structural smell test). Too niche for `summarize_scene` to surface to scene authors; only relevant when investigating an already-broken scene. See Step 3 §6.C for full wording.

### 1.2 Visual reference (`SKILL.md` authoring tips, NOT `summarize_scene` checks)

Two visual-related rules from earlier drafts are now reference-only guidance in `SKILL.md`, not enforced anomalies. Both were `info`-severity, GUI-only, and added noise without diagnostic value.

- **Visual Model tip:** for rendering, map the mechanical state to an `OglModel` via `IdentityMapping` or `BarycentricMapping`. Registered concrete visual classes: `OglModel` (canonical), `VisualModelImpl`, `CylinderVisualModel`, `VisualMesh`, `OglShaderVisualModel`. (`VisualModel` is an abstract base class; `addObject("VisualModel")` works as an alias to `VisualModelImpl` but `search_sofa_components("VisualModel")` returns nothing.)
- **Visual Style tip:** for GUI runs, add a `VisualStyle` at root with `displayFlags="showBehaviorModels showForceFields showVisual"`. All three tokens are canonical (`DisplayFlags.cpp` lines 32, 35, 36); `showVisual` is the canonical group flag (NOT a typo for `showVisualModels`).

Reactivate either as a `summarize_scene` check (in Step 1.5) if real-world scenes start needing the enforcement; full mechanism + class-registration audits are preserved in `diagnose-scene-research/rule-8-visual-model-review.md` and `rule-9-visual-style-review.md`.

### 1.3 Updates to `CLAUDE.md`

- Drop the "All scenes use [mm, g, s]" convention.
- Drop `SparseDirectSolver` from the validated-class list.
- Replace `FixedConstraint` with `FixedProjectiveConstraint`.
- Replace `DefaultContactManager` with `CollisionResponse`.
- Drop `GenericConstraintSolver` (not registered in this build).

**Verification (docs-only):**
- Read `SKILL.md` Health Rules section cold; each rule has a clear *Recommend / Validate / Source* structure and class names match the source review file.
- Verify each class name in §1.1 against `search_sofa_components` (or annotate as core-builtin). One-pass spot-check, ~5 minutes.

**LOC estimate:** ~80 lines of prose changes across SKILL.md + CLAUDE.md. No source-code changes.

---

# Step 1.5 — `summarize_scene` rule enforcement (✅ COMPLETE 2026-04-26)

> **Status: COMPLETE.** Implementation delivered as `sofa_mcp/architect/_summary_runtime_template.py` (read by `_build_summary_wrapper` with sentinel-token substitution). 24/24 pytest tests pass in `test/test_architect/test_summarize_rules.py`. Actual LOC: ~690 runtime + ~600 tests (vs. ~170 + ~250 estimated — over-estimate explained by per-rule helpers, link-vs-data field handling, and full-scene fixtures). Pending follow-up: LLM smoke test (server up + Claude calling `summarize_scene` on a broken fixture).

**Goal:** Extend `summarize_scene`'s output schema so the 9 enforced Health Rules from Step 1 §1.1 produce structured `checks` entries, not just 3 booleans. Existing callers continue to work via legacy boolean aggregation.

**Files:**
- Modify `sofa_mcp/architect/scene_writer.py` — extend `_build_summary_wrapper` (currently lines ~177-181, returns 3 booleans) to emit the new checks with `{rule, severity, subject, message}` shape.

### 1.5.1 New `checks` schema

Replace the current 3-boolean schema with a list of `{rule, severity, subject, message}` entries:

```python
{
  "checks": [
    {
      "rule": "rule_2_animation_loop",          # rule slug
      "severity": "ok" | "info" | "warning" | "error",
      "subject": "/" | "/Robot/leg_0/cable",    # node path (or "/" for root)
      "message": "Scene has FreeMotionAnimationLoop but no constraint solver."
    },
    ...
  ]
}
```

Backwards-compatibility: also keep the legacy boolean fields (`has_animation_loop`, `has_constraint_solver`, `has_time_integration`) by aggregating from the new checks. Existing callers don't break.

### 1.5.2 Per-rule check function structure

The wrapper script generated by `_build_summary_wrapper` will define one check function per Step 1 rule:

Slug numbering matches SKILL.md (1-9), not the spec's 1-12 traceability numbering. Cross-ref note at top of spec.

```python
def check_rule_1_plugins(root): ...
def check_rule_2_animation_loop(root): ...        # 4 sub-checks emit separate entries
def check_rule_3_time_integration(root): ...
def check_rule_4_linear_solver(root): ...         # SearchDown scope check
def check_rule_5_constraint_handling(root): ...   # 3 sub-checks (subtree-correction, inverse-plugin-needs-QP via plugin attribution, AttachProjectiveConstraint template match)
def check_rule_6_forcefield_mapping(root): ...    # exempt PairInteraction (object1 set)
def check_rule_7_topology(root): ...              # BarycentricMapping parent + shell-FEM exemption + MeshTopology loader-extension
def check_rule_8_collision_pipeline(root): ...    # 5-cluster + Bullet exemption (was spec Rule 10)
def check_rule_9_units(root): ...                 # gravity magnitude + YM thresholds (was spec Rule 11)
```

Each function walks the scene tree and returns 0+ `{rule, severity, subject, message}` entries. The aggregator runs them all and emits a flat `checks` list.

**Test plan (23 pytest tests, table-driven):**

| Rule | Happy | Trigger | Targeted edge |
|---|---|---|---|
| 1 plugins | scene w/ all `RequiredPlugin` | missing plugin for used class | — |
| 2 animation loop | `FreeMotion`+constraint solver | no loop (silent `DefaultAnimationLoop`) | — |
| 3 time integration | `EulerImplicit` on unmapped MO | unmapped MO no integrator in ancestry | — |
| 4 linear solver | `SparseLDL` same node as integrator | only ancestor solver (SearchDown fails) | — |
| 5 constraint handling | NNCG + `GenericConstraintCorrection` | no correction in deformable subtree | `SoftRobots.Inverse` class without QP (plugin-attribution) |
| 6 forcefield mapping | FF in subtree with MO | FF subtree no MO, no PairInteraction | — |
| 7 topology | `TetrahedronFEM` + `TetrahedronSetTopologyContainer` | `TetrahedronFEM` with surface topology | `BarycentricMapping` with `TriangularFEM` parent (shell exemption) |
| 8 collision | `CollisionModel` + 5-cluster pipeline | `CollisionModel` no pipeline | — |
| 9 units | SI scene (g=-9.81, YM=1e6 Pa) | SI gravity + mm-magnitude YM | gravity = -9180 typo case |

That's 21 synthetic fixtures (9 happy + 9 trigger + 3 edge). Plus **2 upstream SOFA smoke tests** from `~/workspace/sofa/examples/Component/` (pick at test-writing time scenes that don't legitimately violate our rules) — assertion is "no `error`-severity check fires" rather than "no checks at all" since upstream may legitimately omit `FreeMotionAnimationLoop` etc.

Plus **legacy boolean back-compat**: existing tests pass (`has_animation_loop`, `has_constraint_solver`, `has_time_integration` aggregated from new checks).

Plus **LLM smoke test**: server up; Claude calls `summarize_scene` on a broken fixture; reads the right `checks` entry and surfaces it back to the user.

**LOC estimate:** ~170 impl + ~250 pytest (down from 600 — recommended-pattern + targeted edges, not full matrix).

---

# Step 2 — Subprocess foundation + sanity report skeleton 🚧 *plan refined 2026-04-29 after independent review*

> **Status:** plan drafted 2026-04-29 from spec + codebase review; refined same day after independent review surfaced 6 concrete issues (encoding-decode hardening, marker robustness, double-subprocess cost, field-name verification, deterministic timeout fixture, missing test case). All folded into the design below. Implementation pending user approval; Step 3 expands this skeleton into the smell-test catalog.

**Goal.** Stand up `diagnose_scene` end-to-end with subprocess isolation, producing a sanity report that's intentionally thin: per-step metrics + anomalies lifted from `summarize_scene`. Step 2 proves the pipe works; Step 3 fills the smell-test catalog into the same return shape.

**What is in Step 2 (the deliberately small slice):**
- Subprocess plumbing: parent creates a tempfile path for the JSON payload, calls `~/venv/bin/python sofa_mcp/observer/_diagnose_runner.py <scene_path> <steps> <dt> <output_json_path>`, captures stdout/stderr, reads JSON from the output path after subprocess exits.
- Basic metrics: `nan_first_step`, `max_displacement_per_mo`, `max_force_per_mo`, `scene_summary` (node_count, class_counts, actuators_only).
- `anomalies` populated by lifting the `checks` array from `summarize_scene(content)` in the parent — single source of truth, no rule duplication.
- New MCP tool `diagnose_scene(scene_path, complaint=None, steps=50, dt=0.01)` registered in `server.py`. `complaint` is accepted but unused in Step 2 (the agent's hint is wired in Step 5 playbook).

**What is *not* in Step 2 (deferred and explicitly stubbed):**
- `printLog` toggling on solver/correction/loop classes — the printlog-empirical pre-step test passed but the toggle exists to feed §6.B regex smell tests. With no smell tests yet, toggling produces logs nobody parses. Stub it; turn it on in Step 3 alongside the §6.B consumers.
- §6.A runtime smell tests, §6.B stdout regex, §6.C structural — all Step 3.
- Log truncation (5KB head + 25KB tail) — return raw stdout/stderr in Step 2; truncator lands in Step 3 alongside the consumers that justify it.
- `init_stdout_findings` returned as `[]`.

**Files to create / modify:**

| Path | Action | LOC |
|---|---|---|
| `sofa_mcp/observer/_diagnose_runner.py` | **Create** — subprocess-side runner. Fixed shipped file (NOT tempfile). Argv: `scene_path steps dt output_json_path`. Loads scene via `importlib.util.spec_from_file_location`, builds `rootNode`, walks for MOs, inits, animates, writes payload to `output_json_path` (NOT stdout). | ~210 |
| `sofa_mcp/observer/diagnostics.py` | **Create** — parent orchestrator. `diagnose_scene(scene_path, complaint, steps, dt) -> dict`. Reads file, calls `scene_writer.summarize_scene(content)` (30s budget), spawns `_diagnose_runner.py` as subprocess (90s budget), reads payload from output tempfile, merges into final report. | ~120 |
| `sofa_mcp/server.py` | **Modify** — add `@mcp.tool()` wrapper at end of tool registrations, before `if __name__ == "__main__":`. Mirrors the `validate_scene`/`summarize_scene` style. | ~6 |
| `test/test_observer/test_diagnostics.py` | **Create** — four pytest cases: happy-path on `archiv/cantilever_beam.py`, anomaly-lift on a hand-crafted broken-rule fixture, subprocess timeout (via `time.sleep(200)` in fixture), `createScene`-raises-exception path. | ~100 |

**Key design decisions** (refined after independent review 2026-04-29; numbering preserves traceability to review findings):

1. **Pass `scene_path` as argv, NOT embed scene content via sentinels.** `diagnose_scene` always operates on a file on disk; `importlib.util.spec_from_file_location` is the natural load path.
2. **`_diagnose_runner.py` ships as a fixed file**, invoked by `subprocess.run([PY, RUNNER, scene_path, str(steps), str(dt), output_json_path])`. Debuggable by hand: `~/venv/bin/python sofa_mcp/observer/_diagnose_runner.py archiv/cantilever_beam.py 50 0.01 /tmp/out.json`.
3. **Anomalies = `summarize_scene(content).checks` verbatim.** Single source of truth in `_summary_runtime_template.py`.
4. **Per-step metrics scope: unmapped MechanicalObjects only.** Predicate copied from `check_rule_3_time_integration` in `_summary_runtime_template.py` — do NOT re-derive.
5. **Marker via tempfile, NOT stdout** *(review-2 fix; refined after review-2b)*. Lifecycle:
   - Parent creates path via `tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False)`, closes handle, passes path on argv.
   - Runner writes payload after init+animate.
   - Parent reads in `try/finally`; `finally` calls `os.remove(output_json_path)` unconditionally.
   - **`json.JSONDecodeError`, missing file, and empty file are all treated identically**: `success: false, error: "runner produced no payload (returncode=N)", anomalies: [<from summarize_scene>]`. Implementer wraps `json.loads` in `try/except (json.JSONDecodeError, OSError)`; bare `json.loads` would propagate the exception to FastMCP.
6. **`actuators_only` extraction.** Field name verified 2026-04-29 against `QPInverseProblemSolver.cpp:141` (`initData(&d_actuatorsOnly, false, "actuatorsOnly", ...)`). Python name: `"actuatorsOnly"`. **If no `QPInverseProblemSolver` in tree (common non-inverse case), `actuators_only = false`** — runner returns `false` on no match, never raises.
7. **Parent-side decode encoding** *(review-1 fix; refined after review-2b)*. `subprocess.run(..., encoding="utf-8", errors="replace")` on every subprocess invocation in `diagnostics.py`. **Downstream caveat for Step 3:** `errors="replace"` substitutes invalid bytes with `�`. §6.B regex consumers parsing `solver_logs` must tolerate `�` between adjacent characters. Most regexes (e.g., `^\[(WARNING|ERROR|FATAL)\]`) are safe because they match ASCII anchors; any rule matching fields with non-ASCII content should `.replace("�", "")` first. Step 3 spec for §6.B will reference this.
8. **Independent timeouts** *(review-3 fix; refined after review-2b)*. `summarize_scene` 30s + runner 90s = 120s budget. **Failure-fan-out:** `scene_writer.summarize_scene` returns `{"success": False, ...}` on timeout — without a `checks` key. Parent extracts anomalies via `summary.get("checks", [])` (defensive get, NOT `summary["checks"]`). When summarize fails, anomalies default to `[]` and the runner still attempts its own pass — agent gets metrics even with no structural feedback. Step 2.5 can inline rule checks if 2× cold-start cost becomes a UX issue.

**Subprocess return shape (Step 2 contract):**

```json
{
  "success": true,
  "metrics": {
    "nan_first_step": null,
    "max_displacement_per_mo": {"/root/beam/mo": 0.0124},
    "max_force_per_mo": {"/root/beam/mo": 0.532}
  },
  "anomalies": [{"rule": "rule_4_linear_solver", "severity": "error", "subject": "/root/beam", "message": "..."}],
  "init_stdout_findings": [],
  "solver_logs": "<raw stdout/stderr, decoded with errors='replace'>",
  "scene_summary": {"node_count": 4, "class_counts": {...}, "actuators_only": false}
}
```

On subprocess failure (init exception, timeout, missing scene file, missing output JSON), return `{"success": false, "error": "...", "message": "...", "anomalies": [<from summarize_scene>], "solver_logs": "<captured>"}` — the anomalies still ship so the agent gets structural feedback even when the run can't proceed.

**Verification:**
1. `diagnose_scene("archiv/cantilever_beam.py", steps=50)` → `success: true`, `max_displacement_per_mo` non-zero on the beam MO, `nan_first_step: null`.
2. Synthesized fixture with `EulerImplicitSolver` only in an ancestor (Rule 4 SearchDown trigger): response's `anomalies` contains one entry with `rule == "rule_4_linear_solver"`. The subprocess may or may not run depending on SOFA's tolerance; the anomaly comes from the parent's summarize call regardless.
3. Subprocess timeout *(review-5 deterministic fixture)*: scene whose `createScene` does `import time; time.sleep(200)`. Runner's 90s timeout fires; response is `success: false, error: "Timeout"` with anomalies attached.
4. **`createScene` raises** *(review-6 new test case; fixture refined after review-2b)*: fixture's `createScene` does an explicit `raise RuntimeError("intentionally broken for test")`. Avoids `TetrahedronFEMForceField`-with-undefined-topology because that variant only raises during `Sofa.Simulation.init`, not during `createScene` — both produce non-zero exit but the raise-in-createScene path is more deterministic across SOFA versions.
5. MCP transport regression: extend `test/test_architect/test_mcp_transport.py` to add one round-trip call to `diagnose_scene` over the real MCP transport.

**Reusable building blocks already in the repo (don't reinvent):**
- `sofa_mcp/architect/scene_writer.py:192-255` — subprocess pattern; copy with `encoding="utf-8", errors="replace"` added.
- `sofa_mcp/architect/_summary_runtime_template.py:38-46` — `_iter_nodes(node, path)` walker.
- `sofa_mcp/architect/_summary_runtime_template.py` `check_rule_3_time_integration` — mapped-MO predicate.
- `sofa_mcp/observer/stepping.py:36-58` — `importlib.util.spec_from_file_location` + `createScene` + `Sofa.Simulation.init` load sequence.
- `summarize_scene` from `scene_writer.py` — called directly from parent.

**LOC budget:** ~440 lines impl + ~100 lines tests = ~540 lines (revised up from ~420 after review-7 noted the runner's helper count was undercounted relative to Step 1.5's 690-vs-170 actuals).

**Out of scope for Step 2, captured for later:**
- The runner's `printLog` toggling will be added in Step 3 once §6.B regex consumers exist (sequencing detail below preserved for that step).
- Log truncation (5KB head + 25KB tail with `... <N lines elided> ...`) lands in Step 3.
- A `complaint` argument is accepted by `diagnose_scene` but unused in Step 2 — used by the Step 5 playbook to bias which probe the agent picks next.
- Inlining structural rule checks into the runner (eliminating the second subprocess) — viable as Step 2.5 if 2× cold-start cost becomes a UX problem.

**Sequencing detail preserved for Step 3 (printLog activation):**

```python
# When Step 3 turns this on, subprocess will:
1. Import scene module via importlib (subprocess exits after run; sys.modules leak harmless).
2. Build rootNode via createScene.
3. Walk tree; for each component class in dynamic solver target set (computed from plugin cache):
     - findData("printLog").setValue(True)
     - findData("verbose"), findData("displayDebug"), findData("d_displayTime"), findData("computeResidual") if exist
   IMPORTANT: MUST happen BEFORE Sofa.Simulation.init() — Agent C verified that QP backend strings
   (and likely others) are emitted at init time and gated by printLog. Setting after init misses them.
4. Sofa.Simulation.init(rootNode).
5. For step in range(N): Sofa.Simulation.animate(rootNode, dt). Capture per-step metrics.
6. Write payload to <output_json_path>.
```

Step 2 ships with steps 1, 2, 4, 5, 6; step 3 (printLog toggle) is stubbed.

**Solver target set discovery (also for Step 3):**

```python
SOLVER_CLASS_PATTERNS = ("Solver", "ConstraintCorrection", "AnimationLoop")
target_set = {name for name in plugin_cache | object_factory_names()
              if any(name.endswith(p) for p in SOLVER_CLASS_PATTERNS)}
# DefaultAnimationLoop is core-builtin; add via ObjectFactory enumeration, not plugin cache.
```

---

# Step 3 — Smell test catalog (§6.A runtime + §6.B regex + §6.C structural) (NEEDS REVIEW)

> **Status: NEEDS USER REVIEW.** ~21 smell tests sourced from the multi-agent review; individual smell-test designs not walked through by you.

**Goal:** Implement the runtime-data and stdout-regex smell tests. These are the value-add layer on top of the Step 2 skeleton.

**Files:**
- Modify `sofa_mcp/observer/diagnostics.py` (~250 LOC additional) — smell-test functions.
- Modify `sofa_mcp/observer/_diagnose_runner.py` (~80 LOC additional) — capture per-MO/per-solver Data fields needed by §6.A.

### 3.1 §6.A — Per-step / runtime-data smell tests

| Rule | Severity | Trigger | Implementation note |
|---|---|---|---|
| `nan_first_step` | error | first step where any MO `position`/`velocity`/`force` contains NaN/inf | already in Step 2 metrics |
| `low_displacement` | warning | max disp per MO < 1e-3 mm over all steps | scope to unmapped MOs |
| `excessive_displacement` | warning | max disp > 100× mesh extent | scale-aware threshold |
| `low_assembled_forces` | warning | per-MO assembled `force` magnitude ~0 every step | per-MO; constraint-mediated forces don't appear here (note in message) |
| `mo_static` | warning | unmapped MO has 0 motion across all steps | exempt mapped MOs |
| `solver_iter_cap_hit` | warning | NNCG/BlockGaussSeidel: `currentIterations == maxIterations`. LCP/CG: regex `Iter=N` against maxIterations | branch on solver class (Agent 8) |
| `visual_mechanical_diff` | warning | per-step *change* in OglModel positions diverges from mapped MO change by >1e-5 mm | compare changes, not absolutes (Agent 1 M8) |
| `mapped_dof_zero_accel` | warning | mapped MO velocity doesn't change when net force ≠ 0 | catches SOFA #5999-class bugs (Agent 3) |
| `child_only_motion` | warning | mapped child MO max disp >100× parent MO max disp **AND** parent_max_disp > 1mm (guard) | guard prevents infinite-ratio FP on fixed parents (Agent B5) |
| `actuator_lambda_zero` | warning | all `lambda` entries in QP printLog block == 0 every step | parse `" lambda = ["` block (Agent C) |
| `cable_negative_lambda` | warning | any cable lambda < 0 in QP printLog AND `minForce` is absent on the actuator | only fires when minForce unset; suggested fix: `minForce=0` (Agent C) |
| `q_norm_blowup` | warning | regex `Relative variation of infinity norm through one step: ([\d.]+) %` matches >1000% on any step | percentage value; skip step 0 (countdown) (Agent C) |
| `inverse_objective_not_decreasing` | warning | `d_objective` Data field non-decreasing over ≥5 consecutive steps | read scalar Data programmatically each step (Agent C — `d_objective`, NOT `d_graph`) |
| `high_poisson_with_linear_tet` | tiered | `TetrahedronFEMForceField` with `poissonRatio` ≥ 0.45 / 0.49 / 0.499 | info / warning / error tiers; suggest `TetrahedronHyperelasticityFEMForceField` (Agent A) |

### 3.2 §6.B — Init-time stdout regex smell tests + WARN catch-all

| Rule | Severity | Regex (verified against SOFA source) |
|---|---|---|
| `factory_or_intersector_warning` | error | `Element Intersector .* NOT FOUND\|Object type .* was not created\|cannot be found in the factory` |
| `qp_infeasible_in_log` | error | `QP infeasible` |
| `broken_link_string` | warning | `Link update failed for .+ = @\|Could not read link from` *(corrected from v2's `'0+'` regex which was a pybind artifact)* |
| `pybind_numpy_warning` | warning | `Could not read value for data field .* (np\|numpy)\.float\d+` |
| `plugin_not_imported_warning` | warning | `This scene is using component defined in plugins but is not importing` *(only fires if `SceneChecking` plugin is loaded — subprocess wrapper should load it)* |
| `auto_constraint_solver_warning` | warning | `A ConstraintSolver is required by .* but has not been found` *(class-invariant; current SOFA auto-creates `BlockGaussSeidelConstraintSolver`)* |
| **WARN catch-all** | info | `^\[(WARNING\|ERROR\|FATAL)\]` for any line not matched above; surface raw line text |

### 3.3 §6.C — Pre-step structural smell tests (`diagnose_scene`-only)

Structural checks too niche for `summarize_scene` (where they'd just add noise for scene authors), but useful as anomalies when investigating a scene that's already misbehaving. Run after `summarize_scene`'s checks but before subprocess animate.

| Rule | Severity | Trigger |
|---|---|---|
| `multimapping_node_has_solver` | error | Node containing any registered `core::MultiMapping` subclass (`IdentityMultiMapping`, `SubsetMultiMapping`, `CenterOfMassMultiMapping`, `DistanceMultiMapping`; optional Cosserat: `DifferenceMultiMapping`) AND any `core::behavior::OdeSolver` subclass in the same node. **Forbidden = OdeSolver only** — linear solvers and constraint solvers in the output node are fine. **Allowed on output node:** `Mass`, any `ForceField`, `*ConstraintCorrection`, topology containers, visual models, collision models. *Mechanism:* `MechanicalIntegrationVisitor::fwdOdeSolver` returns `RESULT_PRUNE` after `solver->solve()`, so the ODE solver fires before the mapping's `apply`/`applyJ`/`applyJT`, detaching output DoFs from parent integration. STLIB `Rigidify()` explicitly removes solver before attaching `SubsetMultiMapping` — canonical confirmation. *Source:* `rule-12-multimapping-review.md`. |

### 3.4 Log truncation

Implement 5KB head + 25KB tail with `... <N lines elided> ...` separator. Apply to combined stdout+stderr after smell tests have run on the full text.

**Verification:**
- Each rule has a unit test feeding it a known-good and known-bad fixture scene/log, asserting expected anomaly emission.
- End-to-end: `diagnose_scene` on a scene with deliberately wrong `BarycentricMapping` returns at least one §6.A anomaly.
- End-to-end: `diagnose_scene` on a scene with a typo'd `RequiredPlugin` returns the `factory_or_intersector_warning` from §6.B.
- End-to-end: `diagnose_scene` on a scene with a `*MultiMapping` output node containing an ODE solver returns the `multimapping_node_has_solver` §6.C anomaly.

**LOC estimate:** ~370 lines + ~160 lines of test fixtures.

---

# Step 4 — Probe library (NEEDS REVIEW)

> **Status: NEEDS USER REVIEW.** 4 probes drafted; individual designs not walked through by you.

**Goal:** Add the focused probes the agent uses for follow-up investigation after reading the sanity report.

**Files:**
- Create `sofa_mcp/observer/probes.py`.
- Modify `sofa_mcp/server.py` — register the new tools.

**Probes:**

| Probe | Purpose | LOC est. |
|---|---|---|
| `enable_logs_and_run(scene_path, log_targets, steps)` | Toggle `printLog`/`verbose`/`displayDebug` on specific components by class name or node path; subprocess-run; return logs. | ~150 |
| `compare_scenes(scene_a_path, scene_b_path)` | Diff **runtime scene graphs** post-init (not source text): walk both trees, intersect Data field names per matched component, serialize values with float tolerance, return per-component diff. | ~200 (revised from v2's understated ~80) |
| `perturb_and_run(scene_path, parameter_changes, steps)` | Patch fields temporarily (subprocess receives the changes as a JSON arg), animate, return metrics. Used for `dt_sensitivity` re-run at 0.5×dt. | ~120 |
| `scan_init_stdout(scene_path)` | Load + init only (no animate), capture stdout/stderr, run §6.B smell tests. ~1s. Useful precheck before full diagnose. | ~50 |
| `read_field_trajectory` | Already exists as `run_and_extract` — reuse, no new code. | 0 |

**Verification:**
- Each probe has a unit test against a fixture scene.
- `compare_scenes` against `cantilever_beam.py` vs a copy with perturbed Young's modulus returns the field as a diff entry.
- `perturb_and_run` with `{"node_path": "/leg_0/ff", "field": "youngModulus", "value": 1000}` runs and returns metrics.

**LOC estimate:** ~520 lines.

---

# Step 5 — Playbook + integration tests (M5 gate) (NEEDS REVIEW)

> **Status: NEEDS USER REVIEW.** Playbook table + 4 fixture scenes drafted from earlier work; M5 milestone gate definition reviewed at plan level but step content not individually walked through.

**Goal:** Add the SKILL.md playbook so agents know how to use the toolkit; ship 4 end-to-end test scenes that exercise the M5 milestone.

**Files:**
- Modify `skills/sofa-mcp/sofa-mcp/SKILL.md` — add Debugging Playbook section.
- Modify `README.md` — mention the toolkit.
- Create `test/test_observer/test_diagnose_e2e.py` — 4 broken-scene fixtures + assertions on the agent's expected investigation flow.

**Playbook table (added to SKILL.md):**

| User complaint | First check | Confirm with |
|---|---|---|
| "nothing moves / no actuation" | sanity → `low_assembled_forces`, Rule 5 sub-check failures, `inverse_actuator_without_qp_solver` | `enable_logs_and_run` on actuator + solver |
| "cable/actuator does nothing in inverse scene" | `actuator_lambda_zero` | `enable_logs_and_run` on `QPInverseProblemSolver`, read `lambda` block |
| "explodes / NaN at step N>0" | `nan_first_step` index | `enable_logs_and_run` from step N-5; reduce dt; check Rayleigh damping |
| "passes through itself" | Rule 10 collision pipeline checks | inspect the 5 cluster components |
| "deformation way too small" | `low_displacement` + `high_poisson_with_linear_tet` (info) | `perturb_and_run` reduce YM; switch to hyperelastic FF for high-ν cases |
| "visual lags mechanical / wrong place" | `visual_mechanical_diff`, `pybind_numpy_warning` in init stdout | `enable_logs_and_run` on the Mapping |
| "scene A works, B doesn't" | `compare_scenes(A, B)` (runtime values) | `diagnose_scene` on B |
| "QP infeasible / overconstrained" | `qp_infeasible_in_log`, `q_norm_blowup` | reduce dt, raise `contactDistance`, simplify collision geometry |
| "only the master DoF moves (cables, rigids)" | `child_only_motion` | inspect mapping; compare child vs parent trajectories |
| "force/pressure scales with dt" | rerun at 0.5×dt via `perturb_and_run` | known dt-scaling on `SurfacePressureConstraint`/`CableActuator` |

**Test scenes (`test/test_observer/test_diagnose_e2e.py`):**

1. **Cables not actuated** — copy of `tri_leg_cables.py` with `QPInverseProblemSolver` removed. Expected: Rule 5 inverse-actuator-needs-QP fires.
2. **Wrong material units** — soft-tissue YM=5e9 with gravity=-9.81 (SI). Expected: Rule 11 mm/g/s+SI mismatch fires.
3. **Missing collision pipeline** — `prostate_chamber.py` with `CollisionPipeline` removed. Expected: Rule 10 fires.
4. **Broken Mapping** — scene where cable child MO has wrong `BarycentricMapping` parent. Expected: `child_only_motion` fires (with the Step 3 guard).

**M5 verification (the milestone gate):** for each test scene, the LLM agent (running with full SKILL.md + the diagnose toolkit) (a) reads the right anomaly, (b) proposes a hypothesis a human SOFA dev would also propose, (c) verifies by calling the right follow-up probe.

**LOC estimate:** ~80 lines spec/playbook + ~200 lines of E2E tests.

---

# Pre-step empirical test (run before Step 2) — ✅ PASSED 2026-04-26

**Goal:** verify `printLog=True` set post-createScene, pre-init produces SOFA-prefixed stdout output. Agent C verified the QP backend strings are gated by `f_printLog` and emit at init time; this test confirms the wrapper sequencing v2.1 relies on (set printLog AFTER createScene returns, BEFORE `Sofa.Simulation.init`).

**Test script:** `/tmp/printlog_empirical_test.py` (small FEM scene under FreeMotionAnimationLoop + NNCG + EulerImplicit + SparseLDL + GenericConstraintCorrection; walks tree post-build, sets `printLog=True` on every component whose class ends in `Solver|ConstraintCorrection|AnimationLoop`; init + 3 animate steps; captures stdout via `os.dup2` redirect).

**Result:** **46 SOFA-prefixed message lines captured** across init + 3 steps (19 KB stdout). Per-class breakdown:

| Class | `[INFO]` lines emitted |
|---|---|
| `EulerImplicitSolver` | 25 |
| `NNCGConstraintSolver` | 7 |
| `SparseLDLSolver` | 6 |
| `GenericConstraintCorrection` | 2 |

**Implications for Step 2:**

1. **Wrapper sequencing validated** — `findData("printLog").setValue(True)` post-createScene + pre-init works. No need for constructor-kwarg trickery or pre-init visitor.
2. **Log truncation is more critical than estimated.** `EulerImplicitSolver` alone emits ~6 KB/step on this 81-DOF scene (full state vectors `f`, `b`, `projected b`, `final x`, `final v`, `final f`, plus matrix-resize / factorization messages). A 200-step run on a real scene easily exceeds 1 MB. The 5 KB head + 25 KB tail truncation must be implemented in Step 3, not deferred.
3. **High-value content is at the head.** Init-time messages dominate the first few KB: `Constraint solver found: '/NNCGConstraintSolver'`, `A linear system is required, but has not been found... will be automatically added`, `An OrderingMethod is required... a default AMDOrderingMethod is automatically added`, `LinearSolver path used: '@SparseLDLSolver'`, `ODESolver path used: '@EulerImplicitSolver'`. These are exactly the diagnostic signals `factory_or_intersector_warning` / `auto_constraint_solver_warning` (§6.B) catch.
4. **NNCG emits a `W = [...]` / `delta = [...]` block similar to QP's** — useful for the `solver_iter_cap_hit` rule per Agent 8.

---

# Files (consolidated)

**Create:**
- `sofa_mcp/observer/_diagnose_runner.py` (Step 2)
- `sofa_mcp/observer/diagnostics.py` (Step 2-3)
- `sofa_mcp/observer/probes.py` (Step 4)
- `test/test_observer/test_diagnostics.py` (Step 3 unit tests)
- `test/test_observer/test_probes.py` (Step 4 unit tests)
- `test/test_observer/test_diagnose_e2e.py` (Step 5)

**Modify:**
- `sofa_mcp/server.py` (register tools across Steps 2 + 4)
- `sofa_mcp/architect/scene_writer.py` (Step 1: extend `_build_summary_wrapper`)
- `skills/sofa-mcp/sofa-mcp/SKILL.md` (Step 1 rules + Step 5 playbook)
- `CLAUDE.md` (Step 1 conventions + class names)
- `README.md` (Step 5 mention)

# Out of scope / deferred to v2.2+

- `alarm_distance_vs_mesh_scale` smell test (Agent B2) — needs ~120 LOC of mesh-loading code to compute mean edge length. Real bug class but high implementation cost; defer.
- `explicit_solver_with_large_dt` smell test gated on `*FEMForceField` co-presence (Agent B5) — useful but rarely fires (most scenes use implicit). Defer until a user reports an explicit-stiff issue.
- `bisect_scene` probe (v2 deferred).
- `read_constraint_forces` probe — extract per-contact forces via H^T·λ (Agent 6 F4).
- `count_contacts_per_step` probe (Agent 5 F8).
- `profile_scene` wrapping `runSofa -c N` (Agent 7 #11).
- `topology_changing_with_static_indices` Rule 12 sub-check — corpus shows the bug pattern doesn't exist (Agent B4); revisit if a user reports it.

# Effort estimate

| Step | Goal | Status | LOC | Test LOC |
|---|---|---|---|---|
| 1 | Health Rules docs (SKILL.md + CLAUDE.md) | reviewed | ~80 prose | n/a |
| 1.5 | `summarize_scene` rule enforcement | needs review | ~170 | ~600 |
| 2 | Subprocess foundation + sanity report skeleton | plan refined 2026-04-29 | ~440 | ~100 |
| 3 | Smell tests (§6.A + §6.B + §6.C) | needs review | ~370 | ~160 |
| 4 | Probe library | needs review | ~520 | ~120 |
| 5 | Playbook + E2E + M5 gate | needs review | ~80 | ~200 |
| **Total** | | | **~1500** | **~1140** |

**Total ~2640 LOC.** Step 1.5 test fixtures dominate the test budget — that's 35 per-rule pytest functions, each with a small fixture scene and assertion. If you'd rather trim that to the 9 most-impactful rules first and add the others later, the test LOC drops to ~250 and the per-sub-step principle is relaxed.
