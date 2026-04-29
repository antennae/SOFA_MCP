# Agent 5 — SOFA Q&A discussions review (recent ~18mo)

**Source:** `sofa-framework/sofa` GitHub Discussions, Q&A and "Write/Run a simulation" categories. Mining via WebFetch + WebSearch. Sample: 17 substantive answered/closed threads from 2024-04 through 2025-12 plus one 2025 dev-meeting note. No duplicates of Agent 4's 12 patterns.

## Executive summary

Recent Q&A confirms the spec's first-line probes — `printLog`-style log capture, NaN onset tracking, constraint-iteration parsing, units checks — match how SOFA maintainers actually triage user reports. The most diagnostic signals come from **stdout warnings emitted at init time** (e.g. "Element Intersector ... NOT FOUND") and **solver-emitted infeasibility messages** (e.g. "QP infeasible"), not from numerical fields. Maintainers routinely ask "does the NaN appear at t=0 or after N steps?" — meaning the trajectory-aware design is well-aligned. Two new smell tests fall out: **factory/intersector warnings in stdout** and **template/precision mismatch across mappings (CUDA vs CPU)**. One contradiction: the spec's `monotonic_velocity_norm_growth` rule will frequently fire on stable hyperelastic/haptic scenes that *should* oscillate before settling — needs a cool-down window. Strong external validation: SOFA's own 2025 exec committee wrote "Scene explosion: how to detect/avoid this by pausing SOFA … Might be good to try to detect when a NaN appears."

## Findings (17)

**F1. [#3019 Simple stretch test](https://github.com/sofa-framework/sofa/discussions/3019)** — Hexa beam oscillates under SparseLDLSolver, stable under CGLinearSolver. Diagnosis came from swapping CG↔LDL and watching attenuation. *Adds:* smell test `solver_class_sensitivity` (a `perturb_and_run` use case).

**F2. [#5275 SOFA CUDA collision instability](https://github.com/sofa-framework/sofa/discussions/5275)** — Cylinder unstable on CUDA, stable on Vec3d. **First clue was a stdout warning** `"Element Intersector TriangleCollisionModel<...CudaVec3f...> NOT FOUND"`. *Adds:* `factory_or_intersector_warning_in_stdout` regex smell — high signal, near-zero false positive. Massively validates `log_solvers=True` default.

**F3. [#4734 NaN cable displacement](https://github.com/sofa-framework/sofa/discussions/4734)** — `cable.findData('displacement').value` returns NaN. Maintainer's first question was "Are NaNs at t=0 or after N steps?" then "shrink dt." *Adds:* the spec must record **first-NaN step index**, not just boolean. Add `nan_first_step` to metrics.

**F4. [#4962 Gripping with QPInverseProblemSolver](https://github.com/sofa-framework/sofa/discussions/4962)** — QP becomes infeasible when cube added. **`QP infeasible` log line drove the diagnosis.** *Adds:* `qp_infeasible_in_log` regex; new playbook complaint "QP infeasible / overconstrained" → reduce dt, raise contactDistance, simplify collision geometry.

**F5. [#5063 Neo Hookean haptic blow-up](https://github.com/sofa-framework/sofa/discussions/5063)** — StableNeoHookean stable initially, unstable under sustained haptic. Maintainer (alxbilger): "stabler, but not stable." *Caveat for spec:* `monotonic_velocity_norm_growth` will misfire on hyperelastic/haptic scenes. Gate on settle window OR generous growth factor (e.g. 10×).

**F6. [#4225 Contact force unit confusion](https://github.com/sofa-framework/sofa/discussions/4225)** — Contact forces appear in wrong units; scale linearly with dt. SOFA returns `h*lambda`, not `lambda` — divide by dt. *Adds:* forces-vs-dt scaling check belongs in the playbook; strengthens Agent 4's `units_inconsistency` rule.

**F7. [#4537 Force values zero from DOFs](https://github.com/sofa-framework/sofa/discussions/4537)** — `LinearSolverConstraintCorrection` shows 0 force on impact. **Constraint-mediated forces aren't in `MO.f`** — read constraint Jacobian. Validates Agent 1's M6 critique. Document this in `low_assembled_forces` rule docstring.

**F8. [#5711 Tongue passes through candy](https://github.com/sofa-framework/sofa/discussions/5711)** (2025-12) — One of three rigid bodies has no collision response. Maintainer's first probe: enable "Show Detection Outputs" to see whether contacts detect at all. *Adds:* "contacts detected vs contacts responded" is a fork in the playbook tree. New probe: `count_contacts_per_step`.

**F9. [#4033 Soft-rigid collision artifacts](https://github.com/sofa-framework/sofa/discussions/4033)** — Visual artifacts, mesh distortion, vanishing. Fix: migrate from PenalityContactForceField → FreeMotionAnimationLoop + GenericConstraintSolver + FrictionContactConstraint + LinearSolverConstraintCorrection. *Adds:* playbook entry "penalty contact + deformable = inherently unstable."

**F10. [#5290 Cable Gripper tutorial: empty box](https://github.com/sofa-framework/sofa/discussions/5290)** — Logs flag `"Could not read value for data field rotation/scale3d/translation: np.float64(...)"`. Fix: pybind11/numpy ABI mismatch. *Adds:* `environment_pybind_numpy_warning_in_stdout` smell — env bug, not scene bug, but user blames the scene.

**F11. [#4072 ConstantForceField "no deformation"](https://github.com/sofa-framework/sofa/discussions/4072)** — Inverted BoxROI bounds silently selected many nodes; force was also too small. *Adds:* `empty_or_huge_roi_indices` smell — flag if `BoxROI.indices` is empty or covers >50% of parent MO. Cheap, high-signal.

**F12. [#4452 Surface force via cable-actuator](https://github.com/sofa-framework/sofa/discussions/4452)** — User couldn't get surface force on rigid topology mapped to gripper. *Adds:* when `low_displacement` fires, an obvious next probe is "does the actuator's parent MO have the DoF type the actuator expects (Vec3 vs Rigid3)?"

**F13. [#4032 AttachConstraint template mismatch](https://github.com/sofa-framework/sofa/discussions/4032)** — `"Object type AttachConstraint<> was not created"`. Projective constraints require both MOs share template. *Adds:* `template_mismatch_on_constraint_or_spring` — structural check before run.

**F14. [#4731 Organ slow after FixedConstraint removed](https://github.com/sofa-framework/sofa/discussions/4731)** — Maintainer's request was literally "check all numerical settings (mechanical parameters, mesh quality)" + repro script. **This is the canonical use-case for `diagnose_scene` — automate exactly that triage.**

**F15. [#4368 forceSensor class](https://github.com/sofa-framework/sofa/discussions/4368)** + #4537 cont. — `Monitor` component + constraint-Jacobian extraction is the de-facto debugging tool maintainers point users to. Worth wiring `Monitor`-style export paths into `read_field_trajectory`.

**F16. [#4642 Spring on articulated link](https://github.com/sofa-framework/sofa/discussions/4642)** — Spring "only attached to cube." Causes: (a) spring not in root node, (b) Vec3↔Vec1 DoF mismatch. Same fix family as F13.

**F17. [SOFA 2025 dev report (exec committee)](https://github.com/sofa-framework/sofa/wiki/Sofa-dev-reports-(2025))** — Maintainers themselves wrote: *"Scene explosion: how to detect/avoid this by pausing SOFA … Might be good to try to detect when a NaN appears."* Strongest possible external validation of the project niche.

## printLog=True confirmation

No thread in the recent Q&A sample showed a user posting raw `printLog=True` solver output. **But three threads (#5275, #4962, #5290) were diagnosed primarily from stdout warnings already emitted at default verbosity** (factory/intersector/numpy ABI warnings). This means `log_solvers=True` is necessary but not sufficient — the spec must also surface non-solver stdout from `Sofa.Simulation.init()` onward and run regex smell tests on the full text. Suggest renaming the spec flag conceptually to `capture_full_stdout=True`. One indirect reference (PR #4170) wrapped a hot-loop computation behind `if (printLog)` — confirms the per-component `printLog` lever is the right one. Net: keep `log_solvers=True` default, but **don't only log solvers** — capture everything.

## Recommended additions to smell tests / playbook

New smell tests:
- `factory_or_intersector_warning_in_stdout` (F2, F10)
- `qp_infeasible_in_log` (F4)
- `nan_first_step` numeric (F3) — replaces boolean
- `empty_or_huge_roi_indices` (F11)
- `template_mismatch_on_constraint_or_spring` structural (F13, F16)
- `monotonic_velocity_norm_growth` gated by settle window or growth factor (F5)

New playbook entries:
- "QP infeasible / overconstrained" → dt, contactDistance, geometry
- "NaN at step N>0" → identify what changes at step N, `enable_logs_and_run` from N-5
- "penalty contact on deformable" → migrate to constraint pipeline (F9)
- "contacts detected vs no contacts" → branch on collision-pipeline count (F8)
- "force=0 in MO under Lagrange" → expected, read constraint Jacobian (F7)

## Contradictions / corrections

1. **vs Agent 1 M3 (`monotonic_velocity_norm_growth`):** misfires on hyperelastic/haptic; gate it.
2. **vs spec stdout truncation:** the *first* 5KB matters most (init-time warnings) — don't shrink head budget.
3. **vs spec smell-test list:** add stdout-regex rules as a first-class category; they're cheaper and higher-signal than per-step numerical rules.
4. **vs Agent 4 #10 (RequiredPlugin missing):** F2 generalizes — it's any silent factory/intersector failure. Use the broader regex.

## Suggested new v1.5 probe

`scan_init_stdout(scene_path)` — load + init only (no animate), capture stdout/stderr, run regex smell tests. ~1s, useful precheck before the full 200-step `diagnose_scene`. Maps to F2/F4/F10/F13.
