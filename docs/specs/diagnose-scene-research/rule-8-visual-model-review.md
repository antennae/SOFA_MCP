# Rule 8 — Visual Model: Pre-Implementation Review

**Date:** 2026-04-26
**Reviewer:** Single-rule deep-review agent
**Rule under review (v2.1 §1.1, unchanged from v1):**
> "for rendering, map the mechanical state to an `OglModel` or `VisualModel` via a `Mapping` (`IdentityMapping`, `BarycentricMapping`, etc.)."

---

## 1. Mechanistic explanation

SOFA's rendering pipeline walks the scene graph via `VisualVisitor`/`VisualDrawVisitor` (`Simulation/Core/src/sofa/simulation/VisualVisitor.cpp`). For each node, it calls `drawVisual` on every object that inherits `sofa::core::visual::VisualModel`. If no such object exists in the subtree, the node renders nothing — the simulation runs normally but the GUI shows a blank scene (or only behavior-model wireframes if `showBehaviorModels` is set in `VisualStyle`).

The Mapping is the bridge that keeps the visual surface in sync with the deforming mechanical state. At each simulation step, `MechanicalPropagateOnlyPositionAndVelocityVisitor` calls `Mapping::apply()` on every Mapping in the tree. For a visual child node containing `OglModel` + `IdentityMapping`, this copies the MO's positions into the OglModel's vertex positions every step. Without a Mapping, the OglModel stays frozen at its load-time pose regardless of what the MO does.

**What fails without a visual model:** The simulation is entirely unaffected — physics, constraints, and outputs are identical. Only the GUI display is blank (unless `showBehaviorModels` is on, in which case wireframes of MOs and force fields are shown). For headless/batch use (`runSofa --no-display`, subprocess, Python script with no viewer), the absence of a visual model has zero impact.

---

## 2. Concrete vs base-class: the `VisualModel` issue

This is the key concern. The class hierarchy is:

```
sofa::core::visual::VisualModel          ← ABSTRACT C++ interface (SOFA_ABSTRACT_CLASS)
    └── sofa::component::visual::VisualModelImpl   ← abstract-ish; registered + alias "VisualModel"
            └── sofa::gl::component::rendering3d::OglModel  ← concrete GL class
```

**Registration facts (verified from source + plugin cache):**

| Name | Type | In plugin cache? | Usable in `addObject`? |
|---|---|---|---|
| `VisualModel` | alias for `VisualModelImpl` | **No** | **Yes** (alias in ObjectFactory registry) |
| `VisualModelImpl` | registered concrete | Yes | Yes |
| `OglModel` | registered concrete | Yes | Yes |
| `CylinderVisualModel` | registered concrete | Yes | Yes |
| `VisualMesh` | registered concrete | Yes | Yes |

**Critical finding:** `VisualModel` is NOT in the plugin cache (`plugin_cache.load_plugin_map()` returns it absent), but it IS in SOFA's ObjectFactory registry as an alias for `VisualModelImpl`. This means:
- `addObject("VisualModel", ...)` at runtime: **works** — the alias resolves to `VisualModelImpl`.
- `search_sofa_components("VisualModel")` via the MCP tool: **will not find it** — the tool queries only the plugin cache, which lacks the alias.
- SOFA's own description of `VisualModelImpl` says: *"If a viewer is active it will replace the VisualModel alias, otherwise nothing will be displayed."* This confirms `VisualModel` is a UI-binding alias, not a standalone component.

**The rule's wording is misleading.** Telling a beginner to use `OglModel` or `VisualModel` implies parity, but:
- `OglModel` is the concrete GL-backed class; it renders when a viewer is present.
- `VisualModel` (alias) resolves to `VisualModelImpl`, which renders only if a viewer is active — the SOFA docs explicitly say "otherwise nothing will be displayed."
- In practice, all corpus scenes use `OglModel`, not `VisualModel`.

**Recommended concrete class set for the rule:**
- `OglModel` — the canonical choice for all GUI/viewer scenes (95%+ of corpus).
- `VisualModelImpl` — technically usable but only relevant when swapping backends; not a beginner choice.
- `OglShaderVisualModel` — registered; used for shader-based visual models.
- `CylinderVisualModel`, `VisualMesh` — registered; niche uses (cables, point clouds).

Drop `VisualModel` from the rule's class list. Keep it in a footnote: *"`VisualModel` is a runtime alias for `VisualModelImpl` and works in `addObject` calls, but is absent from the plugin cache and should not be used in `RequiredPlugin` or `search_sofa_components`."*

---

## 3. Mapping requirement — is it strict?

**Verified from corpus (768/1092 visual model scenes, Agent 2):**
- `IdentityMapping`: most common for deformable solids where the visual surface matches the simulation mesh (surface triangles mapped from volumetric tet/hex MO). Also used post-`Tetra2TriangleTopologicalMapping`.
- `BarycentricMapping`: used when visual mesh ≠ simulation mesh geometry (surface `.stl` visual over tet volumetric FEM parent). The standard soft-robotics pattern.
- `RigidMapping`: for rigid bodies (Rigid3d MO → surface OglModel).
- `AdaptiveBeamMapping`: for Cosserat/beam elements.

**Is the mapping strictly required?** Not always:
- **Static visual (rigid floor/background):** `OglModel` alone in a node with no parent MO — no mapping needed, no deformation to track. The OglModel reads from a loader and stays fixed. Example: `CircularRobot/circularrobot.py` floor, `index.md` T2 tutorial.
- **Deformable visual:** a mapping IS required for the OglModel to follow the MO. Without it, the OglModel loads geometry at rest and never updates — the mesh appears frozen while the MO deforms invisibly.

**Does OglModel auto-discover the sibling MO?** No. `OglModel`/`VisualModelImpl` inherit `VisualState<Vec3Types>` and use `Mapping` propagation exclusively. There is no auto-link mechanism.

---

## 4. Edge cases

| Case | Should Rule 8 fire? | Verdict |
|---|---|---|
| Headless/batch scene (no GUI, no viewer) | No | Suppress rule for headless contexts; but detecting headless intent from source text is unreliable. Recommend: make the rule **info** severity, not warning/error. |
| Static visual (OglModel in root/floor node, no parent MO) | No — no deformation to map | Exempt: if OglModel's node has no ancestor MO, no mapping is needed. |
| MO present, no visual model at all | Fire (info) | Common and valid for headless/computation-only scenes (`cantilever_beam.py`, `written_scene.py`, SoftRobots `Tetra.py`). |
| OglModel + no Mapping, but parent MO present | Fire (warning) | Visual will be frozen at rest pose. The simulation is correct but display is wrong. |
| Multiple OglModels per MO | OK — no issue | Valid (e.g., transparent outer + opaque inner). |
| Visual surface (OglModel) + volumetric MO → BarycentricMapping | OK | Covered by Rule 7 parent-topology check. Cross-check: if Rule 7 would fire, Rule 8 mapping is nominally present but may malfunction. |
| VisualModel string in `addObject` | OK at runtime | Flag if found via `search_sofa_components` (tool won't find it); don't flag the scene itself. |

---

## 5. Sample scenes

### Canonical (correct)

1. **`archiv/prostate.py`** — `OglModel` + `BarycentricMapping` in visual child node of volumetric tet prostate. Correct.
2. **`archiv/tri_leg_cables.py`** — `OglModel` + `IdentityMapping` per leg. Correct for surface-mesh MO.
3. **`SoftRobots/examples/thematicalDocs/T4-DirectActuation/DriveTheRobot/Simulation.py`** — `OglModel` + `BarycentricMapping` (visual surface mesh over tet volumetric MO). Canonical for soft robotics.

### Violations (rule should fire)

4. **`archiv/cantilever_beam.py`** — has MO but no visual model. Rule fires (info): scene is intentionally headless. No mapping violation — just absence.
5. **Hypothetical:** `OglModel` added to same node as deformable MO without any Mapping → visual frozen at rest. Rule fires (warning). Easy beginner mistake when copying a static-floor example and adding it to a deformable robot node.
6. **`VisualModel` used as class name** → works at runtime but `search_sofa_components("VisualModel")` returns nothing; beginner confused why the MCP tool can't find it.

---

## 6. Severity verdict

| Condition | Severity | Rationale |
|---|---|---|
| MO present, no `OglModel`/`VisualModelImpl`/`VisualMesh` anywhere in subtree | **info** | Valid for headless; important for interactive scenes. Cannot distinguish intent from source. |
| `OglModel` in same subtree as MO but no Mapping in same child node | **warning** | Display will be wrong (frozen mesh), simulation unaffected. Easy fix. |
| `VisualModel` as class name (alias, not in plugin cache) | **info** (footnote) | Won't fail at runtime; confuses tooling. |

**Do not fire as error.** A missing visual model never breaks the physics. Headless scenes are a legitimate and common pattern (30%+ of SoftRobots examples lack visual models).

---

## 7. Revised rule wording

Replace the current Rule 8 with:

> **Rule 8 — Visual Model.**
> For interactive rendering, place an `OglModel` (plugin `Sofa.GL.Component.Rendering3D`) in a child node of the deformable MO node, accompanied by a `Mapping` to keep it synchronized. Common mappings:
> - `IdentityMapping` — when visual mesh geometry matches the simulation mesh.
> - `BarycentricMapping` — when visual surface differs from volumetric FEM mesh.
> - `RigidMapping` — for Rigid3d MO parents.
> Static visual objects (rigid floor, background mesh) do not need a Mapping.
> Headless/batch scenes (no viewer) do not need any visual model.
>
> *Note: `VisualModel` is a runtime alias for `VisualModelImpl` and works in `addObject`, but is absent from the plugin cache. Use `OglModel` as the canonical name.*
>
> *Check fires as:*
> - **info** — MO present but no `OglModel`/`VisualModelImpl`/`VisualMesh` in its subtree.
> - **warning** — `OglModel` in subtree of deformable MO but no Mapping found in same child node.

---

## 8. Confidence verdict

| Finding | Confidence |
|---|---|
| `VisualModel` is abstract/base class | **Confirmed** — `SOFA_ABSTRACT_CLASS` in `VisualModel.h` |
| `VisualModel` is a usable runtime alias | **Confirmed** — `.addAlias("VisualModel")` in `VisualModelImpl.cpp`, ObjectFactory `addAlias` puts it in registry |
| `VisualModel` absent from plugin cache | **Confirmed** — checked `plugin_cache.load_plugin_map()` programmatically |
| Mapping is required for deformable visual sync | **Confirmed** — no auto-discovery mechanism in OglModel/VisualModelImpl source |
| Static visuals do not need a Mapping | **Confirmed** — corpus examples (floor node in CircularRobot) |
| Rule 8 severity should be info/warning, not error | **High confidence** — headless pattern ubiquitous in upstream corpus |
| OglModel is the canonical registered name | **Confirmed** — 100% of corpus uses `OglModel`, not `VisualModel` or `VisualModelImpl` |

**Overall confidence: HIGH.** The `VisualModel` naming issue is a genuine ambiguity that will confuse beginners and break the MCP `search_sofa_components` tool. The rule wording needs correction before implementation.
