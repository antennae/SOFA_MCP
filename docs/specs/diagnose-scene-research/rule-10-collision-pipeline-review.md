# Rule 10 — Collision Pipeline: Mechanistic Review

**Date:** 2026-04-26
**Reviewer:** Deep-review agent (single-rule scope)
**Subject:** v2.1 §1.1 Rule 10 — "Collision pipeline (NEW)"

---

## 1. Mechanistic explanation per cluster component

**`CollisionPipeline`** (`sofa.simulation.PipelineImpl` subclass) is the orchestrator: each simulation step it calls `doCollisionDetection` then `doCollisionResponse`. Without it, no collision detection runs at all — collision models are simply ignored by the simulation loop. Failure mode: **silent**. Objects pass through each other; no error is emitted.

**`BruteForceBroadPhase`** performs an O(n²) bounding-box sweep over all active collision models and emits a candidate-pair list. Without it, `CollisionPipeline.doCollisionDetection` reaches the broadphase check at line 196 (`if broadPhaseDetection == nullptr → return`) and aborts detection silently after bounding-tree computation. `CollisionPipeline.init()` emits a `[WARNING]` at scene load, but at step time detection simply short-circuits — no crash.

**`BVHNarrowPhase`** traverses bounding-volume hierarchies for each candidate pair from the broad phase to find actual intersecting element pairs. Without it, `doCollisionDetection` short-circuits at line 220 (`if narrowPhaseDetection == nullptr → return`) after broad phase. A `[WARNING]` at init, silent skip every step.

**Intersection method** (`MinProximityIntersection`, `LocalMinDistance`, etc.) provides the per-primitive geometry test (point–point, line–triangle, sphere–triangle). `PipelineImpl.reset()` has an auto-fallback: if `intersectionMethod == nullptr`, it auto-creates `DiscreteIntersection` with a `[WARNING]`. So the intersection slot has a runtime fallback — the scene won't silently skip detection for lack of an intersection method, but it emits a `[WARNING]` and uses a coarser method than intended.

**`CollisionResponse`** (registered as `ContactManager` in factory) translates detection outputs into force-field or constraint responses. Without it, `doCollisionResponse` exits immediately (`if narrowPhaseDetection == nullptr || contactManager == nullptr → return`), `[WARNING]` at init. Contacts are detected but never resolved — objects interpenetrate after first contact step.

**Summary of failure modes:**

| Missing component | Init warning? | Step behavior |
|---|---|---|
| `CollisionPipeline` | none | no detection at all, silent |
| `BruteForceBroadPhase` | `[WARNING]` | detection aborts after bbox step |
| `BVHNarrowPhase` | `[WARNING]` | detection aborts after broad phase |
| Intersection method | `[WARNING]` | auto-fallback to `DiscreteIntersection` |
| `CollisionResponse` | `[WARNING]` | contacts detected but not resolved |

Verdict: all failures are **silent or warning-only** — scenes run without crashing but collision is entirely broken. This confirms `error` severity.

---

## 2. Class-registration audit

All queries against `.sofa_mcp_results/.sofa-component-plugin-map.json`.

### Required cluster (v2.1 spec)

| Class | Registered | Plugin |
|---|---|---|
| `CollisionPipeline` | YES | `Sofa.Component.Collision.Detection.Algorithm` |
| `BruteForceBroadPhase` | YES | `Sofa.Component.Collision.Detection.Algorithm` |
| `BVHNarrowPhase` | YES | `Sofa.Component.Collision.Detection.Algorithm` |
| `MinProximityIntersection` | YES | `Sofa.Component.Collision.Detection.Intersection` |
| `LocalMinDistance` | YES | `Sofa.Component.Collision.Detection.Intersection` |
| `CollisionResponse` | YES | `Sofa.Component.Collision.Response.Contact` |
| `DefaultContactManager` | **NOT REGISTERED** | — (pre-v24 name, removed) |

### Alternative broad phases (all registered)

| Class | Registered | Notes |
|---|---|---|
| `IncrSAP` | YES | Sweep-and-prune, O(n log n) incremental |
| `DirectSAP` | YES | Sweep-and-prune, simpler than Incr |
| `DirectSAPNarrowPhase` | YES | Combined broad+narrow |
| `ParallelBruteForceBroadPhase` | YES | MultiThreading plugin |
| `BruteForceDetection` | YES | Legacy alias |
| `RayTraceDetection` | YES | Ray-based |

### Alternative narrow phases (all registered)

| Class | Registered | Notes |
|---|---|---|
| `RayTraceNarrowPhase` | YES | — |
| `ParallelBVHNarrowPhase` | YES | MultiThreading plugin |

### Alternative intersection methods (all registered)

| Class | Registered | Notes |
|---|---|---|
| `NewProximityIntersection` | YES | Proximity-based, less conservative than Min |
| `DiscreteIntersection` | YES | Discrete, coarser; auto-fallback default |
| `CCDTightInclusionIntersection` | YES | Continuous collision detection |
| `MeshDiscreteIntersection` | YES (via init.cpp) | Mesh-specialized |

### Alternative contact managers

| Class | Registered | Notes |
|---|---|---|
| `CollisionResponse` | YES | Standard, recommended |
| `RuleBasedContactManager` | YES | Subclass of `CollisionResponse`, adds per-pair rules |
| `ContactListener` | YES | Observer only, NOT a contact manager |

**Key finding on contact managers:** `RuleBasedContactManager` inherits from `CollisionResponse` and is registered under `Sofa.Component.Collision.Response.Contact`. It is a legitimate alternative — used in `NeedleInsertion.py` (Cosserat). The rule's detection logic must accept any subclass of `ContactManager` (i.e., `CollisionResponse` OR `RuleBasedContactManager`), not just the literal string `CollisionResponse`.

---

## 3. Bullet exemption — concrete verification

All 4 Bullet example scenes (`BulletSphere.scn`, `BulletConvexHullDemo.scn`, `BulletLMDragon.scn`, `GlobalBulletCollision.scn`) show a consistent pattern:

```xml
<CollisionPipeline .../>
<BulletCollisionDetection .../>
<BulletIntersection .../>
<CollisionResponse .../>
```

**Finding: Bullet does NOT replace `CollisionPipeline` — it coexists.** `BulletCollisionDetection` fills the `BroadPhaseDetection` slot (it implements that interface). `BulletIntersection` fills the intersection slot. `CollisionResponse` is retained unchanged. `BVHNarrowPhase` is **absent** in all 4 Bullet scenes — Bullet handles the narrow phase internally via `BulletCollisionDetection`.

Consequence for the rule: the exemption as written ("Exempt scenes with `RequiredPlugin BulletCollisionDetection`") is the right approach because Bullet's component roster looks like a missing-`BVHNarrowPhase`/missing-`BruteForceBroadPhase` scene to the static checker. The exemption is correct and necessary.

The Bullet plugin is not in this build's plugin cache, confirming it is a separate build artifact.

---

## 4. Edge cases

### 4a. `simulated=False` collision model (static collider)

In `RobSouple-SOFA/projet.py` lines 113–115 and `projet.py` lines 27–29, floor geometry uses:
```python
floor.addObject('TriangleCollisionModel', moving=False, simulated=False, contactStiffness=...)
```

**The rule should still fire.** A static collider still participates in collision detection — it is registered with the pipeline and detected against other models. The collision pipeline must be present to detect contacts between the static floor and the dynamic robot. `simulated=False` only prevents the contact from applying forces back onto the floor; it does not remove the model from collision detection. The rule firing for this case is **correct behavior**.

### 4b. Custom contact manager (`RuleBasedContactManager`)

`RuleBasedContactManager` is registered and is a subclass of `CollisionResponse`. The rule's detection regex or class-check must be: "any registered `ContactManager` subclass", not just the string `CollisionResponse`. Implementation note: `PipelineImpl` discovers the contact manager by `getTreeObjects<ContactManager>()` — so any registered subclass satisfies the slot. The rule should do the same: accept `CollisionResponse` OR `RuleBasedContactManager` in the scene's class list as satisfying the contact-manager slot.

### 4c. Multiple `CollisionPipeline`s at different nodes

Not found in any corpus scene. `PipelineImpl::reset()` uses `getTreeObjects<>()` which returns the first match — multiple pipelines at sibling nodes would be unusual and likely erroneous. The rule is safe to require exactly one (or at least one) at root and not handle multi-pipeline scenarios.

The "2 occurrences" found in scene files like `chainHybrid.scn` are one real instance + one in a `RequiredPlugin` XML comment — not genuine multi-pipeline.

### 4d. XML fragment / `Objects/` subscene

`summarize_scene` (via `scene_writer.py`) requires a `createScene(rootNode)` Python function — it exits with `ERROR: createScene function missing` if absent. XML `.scn` fragments and Python prefabs (like `trunk.py`'s `Trunk` class) do not define `createScene`, so they **cannot be passed to `summarize_scene`** at all. The tool will return an error before the Rule 10 check runs.

However, a Python file that defines `createScene` but delegates collision model setup to a prefab (e.g., calls `trunk.addCollisionModel()`) can have collision models without the pipeline if the author forgot to also call `setupCollisionPipeline`. This is the real target of the rule — and it correctly fires.

---

## 5. Sample scenes

### Canonical (should NOT trigger Rule 10)

| Path | Why clean |
|---|---|
| `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/tutorials/PneunetGripper/details/step7-grabTheCube.py` | Full 5-cluster with `LocalMinDistance`; `FrictionContactConstraint` response |
| `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/tutorials/SoftArmGripper/header.py` | Full 5-cluster with `LocalMinDistance`; `FrictionContactConstraint` response |
| `/home/sizhe/workspace/sofa/src/examples/Tutorials/Collision/MultipleObjectsTwoCubes.scn` | Full 5-cluster; `MinProximityIntersection` + `PenalityContactForceField` response |

### Violations (should trigger Rule 10)

| Path | Missing |
|---|---|
| `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/tutorials/Trunk/trunk.py` | Has `TriangleCollisionModel`, `LineCollisionModel`, `PointCollisionModel` — no `CollisionPipeline` or any other cluster component |
| `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/tutorials/DiamondRobot/DiamondRobot.py` | Has `TriangleCollisionModel` references — no pipeline |
| `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/tutorials/SoftArmGripper/scene.py` | Has `SphereCollisionModel` — no pipeline |

### Bullet exemption (should NOT trigger)

| Path | Reason |
|---|---|
| `/home/sizhe/workspace/sofa/src/applications/plugins/BulletCollisionDetection/examples/BulletSphere.scn` | `RequiredPlugin BulletCollisionDetection` → `BulletCollisionDetection` fills broad phase slot, `BulletIntersection` fills intersection slot; `BVHNarrowPhase` legitimately absent |

### Parallel variant (should NOT trigger, but needs rule update)

| Path | Note |
|---|---|
| `/home/sizhe/workspace/SOFA_MCP/RobSouple-SOFA/projet.py` | Uses `ParallelBruteForceBroadPhase` + `ParallelBVHNarrowPhase` from `MultiThreading` plugin — NOT `BruteForceBroadPhase`/`BVHNarrowPhase`. The rule as written would fire on this canonical project scene! |

---

## 6. Severity verdict

**`error` is justified.**

Mechanistic confirmation: when any of the non-fallback components (`CollisionPipeline`, `BruteForceBroadPhase`, `BVHNarrowPhase`, `CollisionResponse`) is missing, collision detection silently does not run. The scene produces no error, no NaN, no crash — just wrong physics. Objects that should collide pass through each other. This is the hardest class of bug to diagnose manually, which is exactly the class `diagnose_scene` is designed to catch.

B2 corpus data: ~59 of 78 missing-pipeline scenes are complete scenes (not fragments, not Bullet). That is a 15.9% miss rate among all collision-equipped scenes in the upstream corpus — more than 1 in 7. The false-positive rate after excluding Bullet and fragments is near zero.

---

## 7. Final rule wording (revised)

```
Rule 10 — Collision pipeline.

If any node in the scene graph contains a *CollisionModel class
(TriangleCollisionModel, LineCollisionModel, PointCollisionModel,
SphereCollisionModel, CylinderCollisionModel, TetrahedronCollisionModel,
TriangleOctreeCollisionModel, RayCollisionModel, MORPointCollisionModel),
the root node must contain all of the following five slots:

  1. CollisionPipeline                        (orchestrator)
  2. Any broad phase:
       BruteForceBroadPhase | IncrSAP | DirectSAP | DirectSAPNarrowPhase |
       ParallelBruteForceBroadPhase | BruteForceDetection
  3. Any narrow phase:
       BVHNarrowPhase | ParallelBVHNarrowPhase | RayTraceNarrowPhase |
       DirectSAPNarrowPhase
  4. Any intersection method:
       MinProximityIntersection | LocalMinDistance | NewProximityIntersection |
       DiscreteIntersection | CCDTightInclusionIntersection
       (absent → auto-fallback to DiscreteIntersection with WARNING; rule
        does NOT fire for missing intersection method — it is advisory only)
  5. Any contact manager:
       CollisionResponse | RuleBasedContactManager

Exempt: scenes with RequiredPlugin BulletCollisionDetection (Bullet
supplies its own broad-phase and intersection via BulletCollisionDetection
+ BulletIntersection; BVHNarrowPhase is legitimately absent).

Severity: error for missing slots 1, 2, 3, or 5.
          info for missing slot 4 (auto-fallback exists but may not match
          intended geometry; suggest adding MinProximityIntersection or
          LocalMinDistance explicitly).

Fragment caveat: the rule only applies to scenes that define
createScene(rootNode). summarize_scene already enforces this requirement
(exits with ERROR if createScene is absent), so no additional guard needed.
```

---

## 8. Confidence verdict

**High** on the class-registration audit (directly from plugin cache) and the mechanistic analysis (read from `CollisionPipeline.cpp` + `PipelineImpl.cpp` source). The null-check behavior and `[WARNING]` vs silent-skip distinction is directly in source; no runtime experiment needed.

**Medium** on the Bullet exemption mechanism — the 4 upstream scenes show a consistent pattern (Bullet replaces broad phase + intersection but keeps `CollisionPipeline` + `CollisionResponse`), but the plugin is not built in this environment so the claim cannot be runtime-verified.

**High** on the parallel-variant gap — `ParallelBruteForceBroadPhase` and `ParallelBVHNarrowPhase` (from `MultiThreading` plugin) are registered in the plugin cache and used in `projet.py`, but are not in the v2.1 rule wording. This is a confirmed false-positive risk on the project's own canonical scene.

**One actionable change required before implementation:** add `ParallelBruteForceBroadPhase` to the broad-phase allow-list and `ParallelBVHNarrowPhase` to the narrow-phase allow-list. The revised wording above includes this fix.
