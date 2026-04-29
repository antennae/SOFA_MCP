# Agent B — Structural rule corpus prevalence and false-positive analysis

**Corpus baseline:** 394 Python `createScene` files, 1051 XML/SCN scenes (1445 total) in `/home/sizhe/workspace/sofa/{src,plugins}`.

## B1 — Rule 7 extension: `BarycentricMapping` with non-volumetric parent

**Upstream prevalence:**
- 298 files contain `BarycentricMapping`
- 62 also contain `TriangleSetTopologyContainer` (naïve co-occurrence)
- 104 of 298 have no named volumetric container (`TetrahedronSet*`, `HexahedronSet*`, `SparseGridTopology`)
- 79 of those 104 use `MeshTopology` (Rule 7 already accepts this — legitimate)
- Complete scene false positives: 4 scenes with `TriangularFEMForceField + BarycentricMapping` — **all legitimate shell FEM**

**Key finding:** The canonical pattern is `TriangleSetTopologyContainer + BarycentricMapping` in the **child** node, whose **parent** has volumetric topology. The shell FEM case (`skybox.scn`, `stenosis.scn`) is the only realistic false positive — shell/cloth simulations legitimately use `TriangleSetTopologyContainer` as the primary topology and `BarycentricMapping` onto visual meshes.

**Recommended refinement:** Exempt parent nodes that also contain `TriangularFEMForceField`, `QuadBendingFEMForceField`, or similar 2D/shell force fields.

**Verdict: CONDITIONAL ADD.** Severity warning. Ship with shell-FEM exemption.

## B2 — Rule 10: collision pipeline 5-cluster

**Upstream prevalence (corrected for false matches):** 372 scenes with real collision model components. Of those:
- `CollisionPipeline` present: 294 (79%)
- `BruteForceBroadPhase` present: 311 (84%)
- `BVHNarrowPhase` present: 311 (84%)
- Intersection method: ~316 (85%)
- Contact manager (`CollisionResponse`/`DefaultContactManager`): ~310 (83%)
- **All 5 present: 224 of 372 (60%)**

78 of 372 scenes (21%) have collision models but no `CollisionPipeline`. Breakdown:
- ~11: `Objects/` XML fragments (incomplete by design)
- ~5: `BulletCollisionDetection` plugin (Bullet replaces SOFA pipeline — legitimate)
- ~3: `DefaultPipeline` old name (pre-v24 rename)
- ~59 remaining: complete scenes with genuine missing pipeline — silently broken

**Recommended threshold:** Gate the rule to exclude `RequiredPlugin BulletCollisionDetection`. Don't treat `Objects/` snippets as complete scenes.

**Verdict: STRONG ADD.** Severity: error. Prevalence high enough (21% of collision-equipped scenes) to justify.

## B3 — Rule 12: `multimapping_node_has_solver`

**Upstream prevalence:** 24 files contain any `*MultiMapping`. Of those, 15 also contain an ODE solver in the same file. **Zero** of the 24 have an ODE solver placed inside the MultiMapping output node.

Verified across `SubsetMultiMapping.scn`, `IdentityMultiMapping.scn`, `DistanceMultiMapping.scn`, `NearestPointROI.scn`, `rigidification.py` (STLIB), `SoftArmGripper/scene.py`, `Tripod/tripod.py`, `NeedleInsertion.py`. Pattern is consistent: multimapped output child nodes are always solver-free.

**Verdict: CONDITIONAL ADD.** Zero FP rate, but also zero corpus coverage (recall). The rule only catches newly-authored mistakes. Severity: error.

## B4 — Rule 12: `topology_changing_with_static_indices` plugin gating

**Upstream prevalence:**
- `SofaCarving`/`CarvingManager`: 5 files, all in `src/applications/plugins/SofaCarving/examples/`
- `TearingEngine`: 0 files in the entire corpus
- `TetrahedronSetTopologyModifier`: 122 files (used broadly for dynamic topology, NOT limited to carving)
- Both `SofaCarving` and `TearingEngine` are absent from the plugin cache

**Critical finding on alternative detectors:**
If using `TetrahedronSetTopologyModifier` as proxy: 84 of 122 such scenes also have `FixedProjectiveConstraint`. Zero of those 84 use `TopologySubsetIndices`. False-positive rate using this proxy: **100%** — every trigger would be a false positive.

If gating on `RequiredPlugin SofaCarving`: 5 scenes trigger. All 5 use `BoxROI` with Data-link notation (`indices="@ROI1.indices"`) — a topology-aware spatial query that survives carving. **Zero** use hardcoded index arrays. The rule's actual target pattern is **absent from the corpus entirely**.

**Verdict: SKIP.** The rule needs a complete redesign before adding. Defer to v3.

## B5 — §6.A `child_only_motion` 100× threshold

**Threshold analysis:**

In canonical SoftRobots scenes (`Trunk.py`, `SoftArmGripper`, `CableGripper`):
- Parent (deformable elastic body with `PartialFixedProjectiveConstraint`): tip displacement ~15–30mm
- Child cable MO (via `BarycentricMapping`): tracks parent surface → similar magnitude (~15–30mm). Ratio ≈ 1.

**Critical flaw with the 100× ratio:** 503 upstream scenes have a mapping component + `FixedProjectiveConstraint`. If the parent body is **fully fixed** (floor, wall, rigid base with zero motion), `parent_max_disp = 0` and the ratio is **always infinite**, regardless of whether the mapping is correct.

**Recommended refinement:**
- Minimum fix: guard clause `parent_max_disp > 1mm` before computing ratio
- Better fix: change the metric from max-magnitude ratio to per-sample residual: for each child DOF, compute `|child_displacement - BarycentricWeight × parent_displacement|`. If the residual exceeds 5× parent's overall displacement magnitude AND is >10mm absolute, the mapping is functionally broken.

**Verdict: CONDITIONAL ADD** with mandatory guard `parent_max_disp > 1mm`. Severity: warning.

## B6 — Rule 11: units consistency thresholds

**Corpus gravity survey:**
- `gravity ≈ -9.81` (SI): ~452 occurrences (dominant)
- `gravity ≈ -9810` (mm/g/s): ~100 occurrences
- `gravity ≈ -981` (cm/g/s): ~29 occurrences
- `gravity ≈ -98.1` and others: ~8 occurrences

**Young's modulus ranges by gravity system:**

In mm/g/s scenes (gravity ≈ -9810): YM spans 70–4,400,000. Soft robotics silicone: 250–600; stiffer materials: up to 4.4e6.

In SI scenes (gravity ≈ -9.81): YM spans 70–1.2e11. Soft tissue: 1,000–18,000; cartilage: 3.2e7; steel Cosserat beam: 1.2e11.

**Key finding:** Since 1 Pa = 1 g/(mm·s²), the numerical value of Young's modulus is *identical* in SI and mm/g/s systems for the same physical material. The ranges overlap completely (YM=5000 is valid in both). A discriminating rule **cannot** use YM magnitude alone.

**Recommended discriminators:**
1. **mm/g/s context** (gravity magnitude 9810): flag `YM > 1e9` as warning — 1 GPa is above any biological tissue or silicone; suggests SI GPa value used without conversion. Zero upstream mm/g/s scenes would trigger.
2. **SI context** (gravity magnitude 9.81): flag `YM < 100` as warning — sub-100 Pa is physically implausible. One upstream scene triggers (YM=70, genuinely suspicious). Flag `YM < 10` as error.
3. **Gravity ambiguity info note:** gravity magnitude between 90–200 (e.g., -98.1, -981 partial) is unusual.

**Verdict: CONDITIONAL ADD.** False-positive rate ~0% for mm/g/s, <0.3% for SI. Severity: warning for both.

## Summary table

| # | Smell test | Verdict | Upstream trigger count | Est. FP rate | Recommended threshold |
|---|---|---|---|---|---|
| B1 | `BarycentricMapping` with surface-only parent | **CONDITIONAL ADD** | 4 shell-FEM scenes | ~100% FP without exemption | Exempt `TriangularFEMForceField`/`QuadBendingFEM*` parents |
| B2 | Collision pipeline 5-cluster | **STRONG ADD** | 78/372; ~59 complete and broken | ~28% FP among 78 (Bullet, fragments) | Exclude `BulletCollisionDetection`; severity error |
| B3 | `multimapping_node_has_solver` | **CONDITIONAL ADD** | 0/24 (0% FP) | 0% | Rule correct as written; low recall on legacy corpus |
| B4 | `topology_changing_with_static_indices` | **SKIP** | 0 static-index instances anywhere | 100% FP under any proxy | Redesign needed; defer to v3 |
| B5 | `child_only_motion` 100× threshold | **CONDITIONAL ADD** | Silently incorrect for fixed-parent scenes | High FP for fully-fixed parent | Guard: `parent_max_disp > 1mm`; ideal: per-sample residual |
| B6 | Rule 11 YM/units consistency | **CONDITIONAL ADD** | 0 FP at recommended thresholds | ~0% | mm/g/s: YM > 1e9 → warning; SI: YM < 100 → warning, < 10 → error |
