# Agent 2 — Empirical Health-Rules validation against upstream SOFA

**Date:** 2026-04-25
**Source corpus:** `/home/sizhe/workspace/sofa/` (upstream SOFA git checkout)
**Method:** `grep`/`find` mining of all `def createScene` Python files and all `*.scn` / `*.xml` XML scenes under `src/` and `plugins/`. Cross-tabulations via piped `xargs grep`.

> **CORRECTION (2026-04-25, post-mining):** the source-tree grep counted *references* to component classes in `.py` / `.scn` / `.xml` / test / archived files. Several of those classes (notably `GenericConstraintSolver`, with 193 "uses" below) are **not actually registered in this project's runtime SOFA build** — verified via the project's own `search_sofa_components` MCP tool and direct factory instantiation. The grep's "prevalence" numbers reflect *upstream source* presence, not what's compiled and callable. Treat solver-name prevalence claims below with skepticism; cross-check against the plugin cache (`.sofa_mcp_results/.sofa-component-plugin-map.json`) before acting on them. Specifically: **`GenericConstraintSolver` does NOT exist in this build** — keep `NNCGConstraintSolver` as the recommended forward-sim default. The other registered `*ConstraintSolver` classes are `LCPConstraintSolver`, `BlockGaussSeidelConstraintSolver`, `ImprovedJacobiConstraintSolver`, `UnbuiltGaussSeidelConstraintSolver`, plus `QPInverseProblemSolver` from `SoftRobots.Inverse`.

## Executive summary

The 9 Scene Health Rules are *structurally* correct but contain several recommendations that **directly contradict upstream prevalence**. Most important contradictions: (a) the rule recommends `NNCGConstraintSolver` as the soft-robotics default, but upstream uses `NNCGConstraintSolver` in **only 1 example scene** and prefers `GenericConstraintSolver` (193 of 254 FreeMotion files); (b) the rule recommends `SparseLDLSolver` as the default linear solver, but upstream uses `CGLinearSolver` 3.4x more often (1480 vs 440); (c) the rule recommends `displayFlags="showBehavior"`, but upstream typically uses `showBehaviorModels` / `showVisual` / `showWireframe` and `showBehavior` appears only 33 times. Rules 2, 3, 5, 7 also miss several common solver/topology variants and would silently mark valid scenes as unhealthy.

## Corpus stats

- **273** Python `createScene` files; **1040** XML/SCN scenes; **1313** total
- Top sources by Python scene count: `plugins/SoftRobots` (136), `plugins/Cosserat` (44), `plugins/ModelOrderReduction` (39), `plugins/SoftRobots.Inverse` (23), `plugins/Shell` (10), `src/` (11)
- Top sources by XML scene count: `src/` (729), `plugins/Shell` (147), `plugins/SoftRobots.Inverse` (4), `plugins/SoftRobots` (1), `plugins/Cosserat` (1)

## Per-rule validation

| # | Rule | Verdict | Prevalence (upstream) | Notes |
|---|---|---|---|---|
| 1 | RequiredPlugin per component class | partial | 670/1040 XML (64%); 154/273 Py (56%) | Most upstream scenes use it; many still rely on implicit factory or `loadPluginByName`. Rule guidance is correct (post-PLUGINIZE, the strict rule); just be aware it isn't universally honored upstream. |
| 2 | `FreeMotionAnimationLoop` or `DefaultAnimationLoop` at root | contradicted (incomplete enumeration) | 414 FreeMotion + 652 Default; **also** 76 BaseAnimationLoop, 57 CollisionAnimationLoop, 38 ConstraintAnimationLoop, 20 MultiStepAnimationLoop, 19 MultiTagAnimationLoop, 11 SofaGeneralAnimationLoop | Rule omits at least 5 valid loop classes. False-positive risk in `summarize_scene` checks. |
| 3 | Every MO has `EulerImplicitSolver` or `RungeKutta4Solver` ancestor | partial / incomplete | 857/1417 MO files (60%) have a recognized integrator at file level; 1785 EulerImplicit, 94 EulerExplicit, 30 NewmarkImplicit, 24 RK4, 10 VariationalSymplecticImplicit | `NewmarkImplicitSolver`, `EulerExplicitSolver`, `StaticSolver`, `VariationalSymplecticSolver`, `CentralDifferenceSolver` are all in regular use upstream and the rule omits them. Sub-scene patterns lower the file-level co-occurrence number; the *node-level* rule itself is sound. |
| 4 | Linear solver for implicit time solver; default `SparseLDLSolver` w/ `template="CompressedRowSparseMatrixMat3x3d"` | contradicted | 798/843 (94.7%) EulerImplicit files have a linear solver. **But** `CGLinearSolver` (1480) > `SparseLDLSolver` (440); 49 PCGLinearSolver, 40 EigenSimplicialLDLT, 31 BTDLinearSolver. Of 440 SparseLDL uses, only 40 set `template="CompressedRowSparseMatrixMat3x3d"` — alternatives `Mat3x3` (25), `d` (25), `CompressedRowSparseMatrix` (7). | The "default to SparseLDL with that exact template" recommendation is far from upstream prevalence. CG is the de-facto default; SparseLDL is preferred for FEM contact problems. |
| 5 | `FreeMotionAnimationLoop` requires constraint solver at root + correction on each mechanical node | partial; suggested defaults contradicted | 242/254 (95%) of FreeMotion files have a constraint solver; 234/254 (92%) have a constraint correction. **But** dominant solver is `GenericConstraintSolver` (193, ~76%), not `NNCGConstraintSolver` (3 occurrences, only 1 example scene). LCPConstraintSolver (96), BlockGaussSeidelConstraintSolver (57). Dominant correction: `UncoupledConstraintCorrection` (420), then `LinearSolverConstraintCorrection` (162), then `GenericConstraintCorrection` (149). In `SoftRobots/`: GenericConstraintSolver (98) + GenericConstraintCorrection (57); in `SoftRobots.Inverse/`: QPInverseProblemSolver (26) + UncoupledConstraintCorrection (22). | Structural claim supported. **Specific defaults are wrong**. |
| 6 | Every `ForceField` lives in node with a `MechanicalObject` | structurally correct (file-level proxy too weak to test directly) | 1058/1876 (56%) at file level | Rule is correct at node level (which is what matters); file-level co-occurrence undercounts because of subscene fragments. |
| 7 | Volumetric force fields require a topology container or generator | confirmed | 249/300 (83%) `TetrahedronFEMForceField` files have a recognized topology. With loaders + `SparseGridTopology`: 254/300 (84.7%). | Rule is sound. Should explicitly accept `MeshTopology` and `*GridTopology` (1502 TriangleSet, 756 TetrahedronSet, 749 RegularGrid, 273 HexahedronSet, 246 SparseGrid). |
| 8 | Visual model needs a Mapping | partial | 768/1092 (70%) | IdentityMapping (1322) + BarycentricMapping (1129) + RigidMapping (880) cover ~76% of mappings. Rule correct as guidance. |
| 9 | `VisualStyle` w/ `displayFlags="showBehavior"` for runSofa | contradicted on the recommended flag string | 877 VisualStyle uses (~67%). `showBehavior` only **33** uses. More common: `showWireframe` (62), `showVisual` (62+23=85), `showBehaviorModels showVisual` (49+28=77), `showBehaviorModels showForceFields` (44), `showAll` (30). | Intent correct; flag string wrong. Suggest `displayFlags="showBehaviorModels showForceFields showVisual"`. |

## 10 patterns we haven't codified

1. **`UncoupledConstraintCorrection` + deformable FEM** is widespread (420 UCC uses, 849 TetraFEM) but a known footgun (Agent 4 #4). Smell test: flag this combo when linear solver is not SparseLDL.
2. **`FixedProjectiveConstraint` has overtaken `FixedConstraint`** (1217 vs 586). Recent rename. Older scenes may still use `FixedConstraint`.
3. **Rayleigh damping is part of the de-facto integrator default**: 610/843 (72%) EulerImplicit files set Rayleigh; canonical `rayleighStiffness=0.1` (536) and `rayleighMass=0.1` (549).
4. **Collision pipeline is a 5-component cluster**: `CollisionPipeline` + `BruteForceBroadPhase` (736) + `BVHNarrowPhase` (736) + `MinProximityIntersection` (487) + a contact manager. Codify the cluster.
5. **`UniformMass` is the ubiquitous default** (2645), then `DiagonalMass` (722), `MeshMatrixMass` (504). For FEM, MeshMatrixMass is physically correct but unpopular.
6. **Cable `minForce` is widely set in upstream**: 83 in SoftRobots.Inverse, 59 in SoftRobots. Agent 4's smell test should fire only on instances missing it explicitly.
7. **`RestShapeSpringsForceField` is the soft-attach default** (412 uses, 54 in SoftRobots) — soft alternative to `FixedConstraint` that avoids the velocity-drift gotcha.
8. **Gravity is overwhelmingly SI (`-9.81`), not mm/g/s**: ~600 SI uses vs ~22 mm/g/s. SOFA_MCP's `[mm,g,s]` convention is a project override, not the upstream norm.
9. **`CGLinearSolver` is upstream default; `SparseLDLSolver` is contact-problem default**. The MCP's reverse heuristic is opinionated.
10. **Topology mappings (`TetraTopologicalMapping`, `TriangleTopologicalMapping`, `QuadTopologicalMapping`)** are common (648 combined). Missing one is a "visual lags mechanical" cause — worth a smell test.

## Common-default values

- **dt:** 308 x `0.01`, 229 x `0.02`, 104 x `0.05`, 64 x `0.005`, 50 x `0.04` — `0.01` is canonical.
- **Young's modulus:** 101 x `10000`, 87 x `1000`, 57 x `4000`, 44 x `1.092e6`, 43 x `60` — highly diverse.
- **Poisson ratio:** 337 x `0.3`, 196 x `0.45`, 88 x `0.5`, 74 x `0.4`, 58 x `0.33`, 42 x `0.49` — `0.3` for stiff, `0.45-0.49` for soft tissue.
- **Gravity:** 344 x `0 0 0`, 294 x `0 -9.81 0`, 110 x `0 0 -9.81`, 79 x `0 -10 0`. Only ~22 use mm/g/s.

## Recommended additions / changes to Scene Health Rules

- **Rule 2:** expand allow-list to include `ConstraintAnimationLoop`, `MultiStepAnimationLoop`, `MultiTagAnimationLoop`, `CollisionAnimationLoop`.
- **Rule 3:** expand to include `NewmarkImplicitSolver`, `EulerExplicitSolver`, `StaticSolver`, `VariationalSymplectic{Implicit,Explicit}Solver`, `CentralDifferenceExplicitSolver`.
- **Rule 4:** change default guidance. `SparseLDLSolver` for FEM-with-contact; `CGLinearSolver` for FEM-without-contact (upstream default). Accept any of the four upstream-prevalent template strings.
- **Rule 5:** rewrite defaults.
  - Forward-sim soft robotics: `GenericConstraintSolver` + per-node `GenericConstraintCorrection` or `LinearSolverConstraintCorrection`. **Not** `NNCGConstraintSolver`.
  - Inverse-problem: `QPInverseProblemSolver` + `UncoupledConstraintCorrection` (upstream pattern, contradicting SKILL's GenericConstraintCorrection-as-safe-default for inverse scenes).
  - Add warning: UCC + deformable FEM without SparseLDL is a footgun.
- **Rule 7:** explicitly accept `MeshTopology`, `*GridTopology`, any `*SetTopologyContainer`.
- **Rule 9:** change recommended flag string to `"showBehaviorModels showForceFields showVisual"` or `"showAll"`.
- **New Rule 10 — Rayleigh damping.** For `EulerImplicitSolver`, set `rayleighStiffness=0.1`, `rayleighMass=0.1` (72% upstream prevalence).
- **New Rule 11 — Collision pipeline cluster.** All five: `CollisionPipeline`, `BruteForceBroadPhase`, `BVHNarrowPhase`, intersection (`MinProximityIntersection` dominant), contact manager.
- **New Rule 12 — `FixedProjectiveConstraint` preferred over `FixedConstraint`** for new scenes.
- **Replace blanket `[mm,g,s]` claim with a units-consistency smell test.** Enforce internal consistency (gravity magnitude, YM unit, density unit, mesh extent).

## Contradictions with spec / Agents 1 & 4

- Agent 1 had no opinion on Rule defaults; my findings are additive.
- Agent 4's UCC-with-deformable-FEM smell is *too noisy* if applied universally (420 UCC uses upstream). Refine: flag UCC + deformable FEM **only when linear solver is not SparseLDLSolver**.
- Agent 4's "CableConstraint without `minForce`" smell — corpus shows `minForce` is widely set (142 occurrences). Smell test stands but only fires when `minForce` is absent.
- Spec assumes `[mm,g,s]` is project convention. Corpus shows upstream is overwhelmingly SI. The diagnose tool's `units_inconsistency` smell test must detect *which* convention a scene declares (parse gravity magnitude) before flagging — only an internal-consistency answer is meaningful, not a single "right" convention.
