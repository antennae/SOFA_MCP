# Smell-test generality review — 8 candidates

**Date:** 2026-04-25.
**Inputs:** `2026-04-25-diagnose-scene-design-v2.md`, `diagnose-scene-v2-review.md` (M3 dropped-list), `diagnose-scene-review-agent-3.md` (1-4), `diagnose-scene-review-agent-7.md` (5-8).
**Corpus:** 848 scenes across `sofa/src/examples` + `SoftRobots[/{,Inverse}]/examples` + `Cosserat/examples` + `Shell/examples`.
**In-project scenes:** the 4 referenced scenes have been moved to `/home/sizhe/workspace/SOFA_MCP/archiv/` (`cantilever_beam.py`, `tri_leg_cables.py`, `prostate.py`, `prostate_chamber.py`).

## Per-candidate evaluation

### 1. `high_poisson_with_linear_tet` (poisson ≥ 0.49) — tentative ADD

- **A. Bug class:** Real and recurring. Issue #5751 (tet beam drifts laterally at ν≈0.495 under SurfacePressure). Linear-tet volumetric locking is textbook FEM.
- **B. Upstream FP:** 177 scenes use `TetrahedronFEMForceField`; **16 (9.0%)** pair it with poisson ≥ 0.49. At 0.45 the rate is 36% — too eager. 0.49 is the right knife edge.
- **C. In-project:** No trigger. `tri_leg_cables` 0.30; `prostate*` 0.45.
- **D. Remediation:** "Use `TetrahedronHyperelasticityFEMForceField`, hex elements, or lower ν to ≤0.45." All three are concrete; classes are cache-registered.

**Verdict: STRONG ADD.** Threshold 0.49, severity warning.

### 2. `alarm_distance_vs_mesh_scale` — tentative ADD

- **A. Bug class:** Real (#5130: layered tissue interpenetrates because alarmDistance ≪ tet edge length). Generalises beyond the issue.
- **B. Upstream FP:** 176 scenes use `LocalMinDistance`/`MinProximityIntersection`; alarmDistance values span 0.02→15. Rule needs mean-edge-length from mesh, so its FP rate depends on whether the implementation can load the mesh. Bounded <5% if implemented properly; unimplementable as a pure-source-text check.
- **C. In-project:** No trigger (no collision pipelines).
- **D. Remediation:** Clear — `alarmDistance ≈ 1.5 × mean_edge`, `contactDistance ≈ 0.5 × alarmDistance`. Implementation cost is real (~80-150 LOC: resolve `MeshOBJLoader`/etc., compute mean edge, compare). Not the "trivial" framing of the original Agent 3 finding.

**Verdict: CONDITIONAL ADD.** Add but flag implementation cost in §11; ship after rules 1/5. Severity warning. If mesh isn't loadable (procedural geometry), emit `info` "alarm/contact ratio not checkable."

### 3. `overlapping_subtopology_indices` — tentative SKIP

- **A. Bug class:** Real but single-issue (#4706, multi-material hyperelasticity).
- **B. Upstream FP:** Only **5 scenes** use `TetrahedronHyperelasticityFEMForceField` corpus-wide. The pattern is vanishingly rare.
- **C. In-project:** No trigger.
- **D. Remediation:** Clear, but rule is run against every scene to catch a workflow that's almost never used.

**Verdict: SKIP confirmed.** Defer to v3 if a real user reports it.

### 4. `bilateral_constraint_pair_distance_drift` — tentative SKIP

- **A. Bug class:** Real (#2486, regression v19→v21). One historical issue.
- **B. FP:** Runtime-only; not measurable from source.
- **C. In-project:** No bilateral constraints in the 4 scenes.
- **D. Remediation:** The original buggy class `BilateralInteractionConstraint` isn't even in the v2 plugin cache (only `BilateralLagrangianConstraint` is). The bug shape doesn't apply to this build.

**Verdict: SKIP confirmed** — and somewhat obsolete.

### 5. `explicit_solver_with_large_dt` (dt > 1e-3) — tentative ADD

- **A. Bug class:** Real (Agent 7 #6, doc-confirmed example uses dt=1e-5).
- **B. Upstream FP:** 30 scenes use `EulerExplicitSolver`. Of these, **17 (57%)** use dt > 1e-3 and run fine: tutorial pendulums (1-DOF, low stiffness) at dt=0.01; benchmark momentum scenes at dt=0.04. The rule has no stiffness signal — it'll fire constantly on tutorials.
- **C. In-project:** No trigger (no scene uses explicit).
- **D. Remediation:** "Switch to implicit, or lower dt." Both clear. But in 57% of trigger cases, the fix is inappropriate (the scene is fine).

**Verdict: CHALLENGE the tentative ADD → CONDITIONAL ADD.** Gate on a stiffness signal: trigger only when `EulerExplicitSolver` is paired with `*FEMForceField` or `MeshSpringForceField` AND dt > 1e-3. Tutorial pendulums (which are spring-only or particle-only with `SpringForceField`) would still false-trigger; consider tightening to `*FEMForceField` only as a v1, opening the door to spring-based scenes later.

### 6. `uniform_mass_on_volumetric_topology` — tentative SKIP

- **A. Bug class:** Not a bug — Agent 7 #8 cites accuracy guidance. Doc says "should be carefully used if accuracy is a criterion."
- **B. Upstream FP:** **41% (201/488)** of `UniformMass` scenes are on volumetric topology. This IS upstream norm, including the official `EulerExplicitSolver_diagonal.scn` example.
- **C. In-project:** **2/4 trigger** (`cantilever_beam`, `tri_leg_cables`).
- **D. Remediation:** "Use `MeshMatrixMass`" — fine but contradicts widespread upstream practice.

**Verdict: SKIP confirmed.** A 41% upstream trigger rate disqualifies it. If kept anywhere, demote to an `info`-level note in §10 Rule 12 with no anomaly emission.

### 7. `nonlinear_mapping_with_symmetric_solver` — tentative SKIP

- **A. Bug class:** Documented in theory (Agent 7 #12); no upstream user-facing issue cites it as the root cause of a runtime bug.
- **B. Upstream FP:** **37% (67/179)** of `BarycentricMapping` scenes pair with `SparseLDLSolver`. The "non-linear" qualifier (mismatched topologies) is hard to detect without runtime data.
- **C. In-project:** **2/4 trigger** (`prostate.py`, `prostate_chamber.py`) on the user's own working scenes.
- **D. Remediation BLOCKED:** `SparseLUSolver` is **not registered** in this build (verified against `.sofa-component-plugin-map.json` — only `SparseLDLSolver` and `AsyncSparseLDLSolver` exist in `Sofa.Component.LinearSolver.Direct`). The suggested fix is uncallable.

**Verdict: SKIP confirmed, strongly.** Triple-disqualified. Re-evaluate only if upstream registers `SparseLUSolver`.

### 8. `rayleigh_overdamped` (>~0.1) — tentative SKIP

- **A. Bug class:** Real symptom ("deformation too small" via over-damping), wrong threshold.
- **B. Upstream FP:** rayleighStiffness/Mass = **0.1 is the upstream-corpus default** — 340 of `rayleighMass="0.1"`, 316 of `rayleighStiffness="0.1"`, vs only ~21 explicit `0`. Anything `≥0.1` fires on the entire `EulerImplicitSolver` corpus.
- **C. In-project:** Both `prostate*.py` use exactly `0.1` — at threshold.
- **D. Remediation:** "Lower damping" implies the upstream default is wrong. It's not.

**Verdict: SKIP confirmed.** "Use SOFA defaults" holds up empirically: 0.1 IS the SOFA default. The playbook already mentions Rayleigh as a hypothesis under `low_displacement` — that's the right place for it, not an enshrined rule.

## Revised summary

| # | Candidate | Tentative | Revised | Refinement |
|---|---|---|---|---|
| 1 | `high_poisson_with_linear_tet` | ADD | **STRONG ADD** | Threshold 0.49, warning severity |
| 2 | `alarm_distance_vs_mesh_scale` | ADD | **CONDITIONAL ADD** | ~120 LOC for mesh-loading; ship after 1/5; warning severity |
| 3 | `overlapping_subtopology_indices` | SKIP | SKIP | — |
| 4 | `bilateral_constraint_pair_distance_drift` | SKIP | SKIP | — (also obsolete: `BilateralInteractionConstraint` unregistered) |
| 5 | `explicit_solver_with_large_dt` | ADD | **CONDITIONAL ADD** | Gate on `*FEMForceField` co-presence + dt > 1e-3; warning severity |
| 6 | `uniform_mass_on_volumetric_topology` | SKIP | SKIP | (or demote to info-only Rule 12 note) |
| 7 | `nonlinear_mapping_with_symmetric_solver` | SKIP | SKIP | — |
| 8 | `rayleigh_overdamped` | SKIP | SKIP | — |

**Net additions:** 3 confirmed (1 unconditionally, 2 + 5 with refinements). User's tentative call held in 6/8; #2 and #5 deserve refinements, not flat ADD.

## Push-back on items already in v2

1. **Rule 5 `AttachConstraint template match`** — v2 review B1 already flagged: `AttachConstraint` is unregistered; only `AttachProjectiveConstraint` is. Restating because this is the same class-cache hygiene failure.
2. **Rule 12 `topology_changing_with_static_indices`** cites `SofaCarving` and `TearingEngine` — neither in the plugin cache. The rule should be gated on plugin availability, not unconditional.
3. **§6.A `child_only_motion`** (threshold child max-disp >>100× parent) — cable scenes routinely have child cable disp ≫ rigid base disp; user's `tri_leg_cables.py` could over-trigger. Audit needed.
4. **Rule 11 units consistency follow-on check** ("YM in MPa magnitude with SI gravity") — needs an explicit threshold. Soft-tissue scenes at YM=5000 look ambiguous between SI-Pa and mm/g/s. Recommend: derive unit system from gravity first, then check YM against that system's expected range.

**Meta-concern:** the v2 spec lists ~13 smell rules; only ~3 (after this review) have upstream-prevalence backing. The other 10 are theory-grounded but unmeasured. The same kind of corpus analysis run here should be done for each before it lands in `summarize_scene` — otherwise we ship the v2 review's "FP-rate problem" at scale.
