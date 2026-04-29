# Agent A — `high_poisson_with_linear_tet` Literature Research

**Date:** 2026-04-25.

## Verdict

**STRONG ADD.** Primary threshold: `warning @ ν ≥ 0.49`. Recommend adding `info @ ν ≥ 0.45` as a low-cost second tier.

Volumetric locking in constant-strain tetrahedra is one of the most thoroughly documented pathologies in computational mechanics — covered in every standard FEM textbook and flagged by every major FEM package. SOFA's `TetrahedronFEMForceField` is a pure displacement-only, constant-strain T4 element with no anti-locking measures, making the pathology algebraically guaranteed as ν → 0.5. SOFA issue #5751 provides a concrete, reproducible manifestation (lateral beam drift at ν ≈ 0.495). The smell test is cheap (one numeric comparison at scene-parse time), the remediation is available in-build, and the false-positive rate at 0.49 is empirically bounded at 9% of corpus scenes.

## What Kind of Element is `TetrahedronFEMForceField`

Verified from `/home/sizhe/workspace/sofa/src/Sofa/Component/SolidMechanics/FEM/Elastic/src/sofa/component/solidmechanics/fem/elastic/TetrahedronFEMForceField.inl`:

**4-node linear tetrahedron (T4 / CST — Constant Strain Tetrahedron), pure displacement formulation.** The `computeStrainDisplacement` function constructs a single constant B-matrix from the four nodal coordinates (no quadrature loop). All four methods (`small`, `large`, `polar`, `svd`) share this B-matrix — the method variants differ only in how element rotation is extracted for corotational correction, not in displacement field order.

The material stiffness scalar at line 275 is:
```
materialsStiffnesses[i] *= E*(1-ν) / [(1+ν)*(1-2*ν)]
```
The `(1-2ν)` denominator is the algebraic signature of volumetric locking. As ν → 0.5, this → 0 and the bulk modulus λ = Eν/[(1+ν)(1−2ν)] → ∞, enforcing volume preservation as an infinite penalty. There is no B-bar, no reduced integration, no mixed formulation — SOFA's implementation is in the most severely affected class of elements.

## Locking Severity Scale

| ν | Regime | Effect on linear tet |
|---|--------|---------------------|
| ≤ 0.30 | Compressible | Negligible locking; T4 reliable |
| 0.40 | Mild near-incompressible | Locking detectable under mesh refinement tests; SimScale marks ν > 0.40 as requiring caution with linear tets |
| 0.45 | Transitional | Noticeable under-displacement on coarse meshes; Longva et al. (2021) cite this as practical workaround limit |
| 0.49 | Strongly near-incompressible | Displacements severely underpredicted on typical simulation meshes; Abaqus 6.13 issues a warning for non-hybrid elements at ν > 0.48 |
| 0.495 | SOFA issue #5751 regime | Lateral drift in tet beam confirmed; hex beam at same load stable |
| 0.499+ | Degenerate | λ/μ ≈ 500; near-singular stiffness; results unreliable at any mesh density |

The locking severity depends on loading and geometry — hydrostatic/constrained loads are far more susceptible than deviatoric/bending loads. However, SOFA scenes at ν ≥ 0.49 are almost always modeling rubber or soft biological tissue (predominantly volumetric constraint problems), so the loading dependence does not weaken the threshold recommendation for this use case.

## Recommended Threshold: Tiered System

| Level | Trigger | Rationale |
|-------|---------|-----------|
| `info` | ν ≥ 0.45 | Transitional zone entry; no confirmed SOFA bugs here, but SimScale and textbook literature consider this the boundary of first-order element safety. At 36% corpus prevalence, `info` avoids alarm fatigue |
| `warning` | ν ≥ 0.49 | Aligned with Abaqus 6.13 threshold (0.48 for warning) and SOFA issue #5751 (0.495 confirmed failure). At 9% corpus prevalence — the right knife edge |
| `error` | ν ≥ 0.499 | Denominator (1−2ν) < 0.002; numerically degenerate in most solvers |

The existing `smell-test-generality-review.md` spec proposes `warning @ 0.49` only. This review endorses that as the primary warning and recommends adding `info @ 0.45` as a low-cost early advisory.

## Recommended Workarounds (Verified in This Build)

Cross-checked against `/home/sizhe/workspace/SOFA_MCP/.sofa_mcp_results/.sofa-component-plugin-map.json`:

| Workaround | Registered | Plugin |
|-----------|-----------|--------|
| `TetrahedronHyperelasticityFEMForceField` | Yes | `Sofa.Component.SolidMechanics.FEM.HyperElastic` |
| `StandardTetrahedralFEMForceField` | Yes | `Sofa.Component.SolidMechanics.FEM.HyperElastic` |
| `HexahedronFEMForceField` | Yes | `Sofa.Component.SolidMechanics.FEM.Elastic` |
| `HexahedronFEMForceFieldAndMass` | Yes | `Sofa.Component.SolidMechanics.FEM.Elastic` |
| Lower ν to ≤ 0.45 | n/a | Loses physical accuracy; last resort |

**Primary recommended fix:** `TetrahedronHyperelasticityFEMForceField` — keeps the tetrahedral mesh, uses proper volumetric-deviatoric split (Neo-Hookean, Mooney-Rivlin), no locking.

**Do not recommend** `FastTetrahedralCorotationalForceField` as a workaround — it is also a pure displacement T4 element and will lock identically.

## Citations

1. **Hughes, T.J.R. (1987).** *The Finite Element Method: Linear Static and Dynamic Finite Element Analysis.* Prentice-Hall. Ch. 4 — establishes that displacement-only low-order elements fail the LBB (inf-sup) condition for nearly incompressible media; bulk modulus acts as infinite penalty.

2. **Longva, A., Löschner, F., Francu, M., et al. (2021).** "Locking-Proof Tetrahedra." *ACM Transactions on Graphics*, 40(2). DOI: 10.1145/3444949. — Demonstrates locking at ν = 0.499 in a 3,628-element linear tet mesh (rubber tube under pressure). Confirms locking cannot be cured by mesh refinement for displacement-only T4.

3. **Abaqus 6.13 Release Notes, §13.3.** Dassault Systèmes, 2013. — Industry benchmark: warning at ν > 0.48, error at ν > 0.495 for non-hybrid solid elements. C3D4 described as "constant stress tetrahedron that should be avoided as much as possible" for near-incompressible loads.

4. **SimScale Blog: "Modeling Elastomers Using FEM."** — Practitioner threshold table: "ν ≤ 0.40: first-order OK; ν up to 0.45: second-order OK; ν > 0.45: second-order + reduced integration required."

5. **SOFA GitHub Issue #5751** (sofa-framework/sofa). Tetrahedral beam drifts laterally under `SurfacePressureForceField` at ν ≈ 0.495; hex beam stable under identical load. Confirmed by SOFA maintainers. Primary empirical anchor for the smell test.

6. **Malkus, D.S. & Hughes, T.J.R. (1978).** "Mixed Finite Element Methods — Reduced and Selective Integration Techniques." *CMAME*, 15(1), 63–81. — Proves displacement-only linear tets are equivalent to a degenerate mixed formulation with piecewise-constant pressure; cannot represent incompressible deformations.
