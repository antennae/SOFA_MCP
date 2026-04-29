# Rule 9 — Visual Style review (v2.1 §1.1)

**Date:** 2026-04-26
**Reviewer:** single-rule deep-review agent
**Status:** APPROVED with one token correction

---

## 1. VisualStyle registration

Confirmed. Plugin cache at `.sofa_mcp_results/.sofa-component-plugin-map.json` maps
`"VisualStyle" → "Sofa.Component.Visual"`.
The component is in `src/Sofa/Component/Visual/src/sofa/component/visual/VisualStyle.h`.
RequiredPlugin name: `Sofa.Component.Visual`.

---

## 2. displayFlags parser — source citation and mechanics

**Source:** `src/Sofa/framework/Core/src/sofa/core/visual/FlagTreeItem.cpp`,
`read()` method (lines 139–169).

The parser reads whitespace-separated tokens via `while(in >> token)`. There is no
comma support. Tokens are matched case-insensitively against a flat map built from
the tree of `FlagTreeItem` node names. Unknown tokens call `unknownFlagFunction` (which
emits a `[WARNING]` at runtime); they are silently ignored at the data level — they do
NOT produce a parse error or exception. Incorrect-case tokens are handled via
`incorrectLetterCaseFunction` (also a warning).

**Separator:** space only. Commas are not recognized and would be treated as unknown
tokens emitting warnings.

---

## 3. Canonical token list

From `DisplayFlags.cpp` constructor (the authoritative name-to-tree-item mapping):

| Token string (show) | Token string (hide) | Level |
|---|---|---|
| `showAll` | `hideAll` | group |
| `showVisual` | `hideVisual` | group (parent of visualmodels) |
| `showVisualModels` | `hideVisualModels` | leaf |
| `showBehavior` | `hideBehavior` | group (parent of behaviormodels, forcefields, interactionforcefields) |
| `showBehaviorModels` | `hideBehaviorModels` | leaf |
| `showForceFields` | `hideForceFields` | leaf |
| `showInteractionForceFields` | `hideInteractionForceFields` | leaf |
| `showCollision` | `hideCollision` | group |
| `showCollisionModels` | `hideCollisionModels` | leaf |
| `showBoundingCollisionModels` | `hideBoundingCollisionModels` | leaf |
| `showDetectionOutputs` | `hideDetectionOutputs` | leaf |
| `showMapping` | `hideMapping` | group |
| `showMappings` | `hideMappings` | leaf (visual mappings) |
| `showMechanicalMappings` | `hideMechanicalMappings` | leaf |
| `showOptions` | `hideOptions` | group |
| `showAdvancedRendering` | `hideAdvancedRendering` | leaf (alias: `showRendering`) |
| `showWireframe` | `hideWireframe` | leaf |
| `showNormals` | `hideNormals` | leaf |

The alias mechanism (`addAliasShow` / `addAliasHide`) is used only for
`showRendering` → `showAdvancedRendering`. When an alias is matched and its index > 0,
`read_recursive` emits `msg_warning("DisplayFlags") << "FlagTreeItem '...' is deprecated,
please use '...' instead"`. No other show/hide aliases exist in this build.

---

## 4. Token-by-token verification of the recommended string

**Recommended string (v2.1 §1.1 Rule 9):**
`"showBehaviorModels showForceFields showVisual"`

| Token | Registered? | Canonical (index 0)? | Effect |
|---|---|---|---|
| `showBehaviorModels` | YES | YES | shows behavior model overlays (wireframe MO shapes) |
| `showForceFields` | YES | YES | shows force-field overlays (springs, FEM triangles) |
| `showVisual` | YES | YES | group flag: enables the entire `showVisual` subtree, which implies `showVisualModels` |

All three tokens are canonical, first-index registered names. None is an alias or
deprecated form. `showVisual` IS a registered group-level flag — not a typo for
`showVisualModels`. Setting `showVisual` propagates down via `propagateStateDown` and
sets `showVisualModels` to true as well, which is the intended behavior. The string
parses cleanly with no warnings.

**Agent 2's corpus count clarification:** Agent 2 reported "`showVisual` (62+23=85)".
Those 85 scenes ARE using the canonical group token. There is no aliasing or deprecation
warning for `showVisual`. It is fully legitimate.

**The recommended string is correct.** No correction needed on the tokens themselves.

---

## 5. Edge cases

**Headless / pytest / CI scenes.** `VisualStyle` is a visual-only component — it has
no effect in headless mode (no `draw()` calls, no VisualParams dispatch). It does not
affect physics or performance. Adding it to a headless scene is harmless, but it adds
dead XML/Python noise. Rule 9 is correctly scoped as GUI-only: it should only fire as
`info` severity when running `summarize_scene` for a scene that will be opened in
`runSofa`. The tool has no reliable way to know the intended execution context from
the scene source alone, so the check should always emit `info` (never `warning` or
`error`) and phrase the message as a recommendation.

**Multiple VisualStyle nodes.** Supported by design: the comment in `VisualStyle.h`
says "It merges the DisplayFlags conveyed by the VisualParams with its own DisplayFlags."
Child nodes can override parent `VisualStyle` settings (hierarchical merging via
`merge_displayFlags`). No bug here. `summarize_scene` need not flag multiple instances.

**VisualStyle at root vs child node.** Both are valid. At root, it sets the global
default. At a child node, it overrides within that subtree only. Rule 9 recommends
root placement for the common case; nothing to enforce.

---

## 6. Sample scenes (3 canonical, verified against source)

**Scene 1 — `src/examples/Component/Topology/Container/Grid/RegularGridTopology.scn`**
```xml
<VisualStyle displayFlags="showBehaviorModels showForceFields showVisual" />
```
Exact match of the recommended string. Physics + visual debug view.

**Scene 2 — `plugins/SoftRobots/examples/thematicalDocs/T1-Elements_TetraHexaBeam/Hexa/Hexa.py`**
```python
rootNode.addObject('VisualStyle', displayFlags='showBehaviorModels showForceFields')
```
Mechanical-only debug view (no visual mesh); valid narrower subset.

**Scene 3 — `plugins/SoftRobots.Inverse/examples/sofapython3/robots/Diamond.py`**
```python
rootNode.addObject('VisualStyle', displayFlags='showCollision showVisualModels showForceFields showInteractionForceFields')
```
Adds collision + interaction forces; uses mix of group and leaf tokens.

All three parse without warnings. None uses commas.

---

## 7. Severity verdict

**`info`, GUI-only.**

- `VisualStyle` has zero effect in headless/subprocess runs; never emit `warning` or
  `error` for its absence.
- The `summarize_scene` check should be phrased as: "No VisualStyle found at root.
  Add `VisualStyle(displayFlags='showBehaviorModels showForceFields showVisual')` for
  visual debugging in runSofa."
- `summarize_scene` runs in both GUI and headless contexts, so the check must always
  be `info`. The agent reading the output can choose to surface or suppress it based
  on the user's complaint.

---

## 8. Final rule wording

> **Rule 9 — Visual Style (GUI-only recommendation)**
>
> *Recommend:* Add a `VisualStyle` at the root with
> `displayFlags="showBehaviorModels showForceFields showVisual"` for scenes that will
> be opened in `runSofa`. This enables mechanical overlays (`showBehaviorModels`,
> `showForceFields`) and renders visual meshes (`showVisual` → propagates to
> `showVisualModels`).
>
> *Severity:* `info` always. Never `warning` or `error`.
>
> *Trigger:* no `VisualStyle` component found anywhere in the scene tree.
>
> *No trigger on:* headless/subprocess validation scenes, scenes that already have
> `VisualStyle` anywhere (root or child node). Multiple `VisualStyle` nodes are valid.
>
> *Plugin requirement:* `RequiredPlugin(name="Sofa.Component.Visual")` must be present
> (or auto-loaded) — flag this with the existing Rule 1 plugin check, not here.

---

## 9. Confidence verdict

**HIGH** on all sub-questions:

- Registration: confirmed from live plugin cache (not just source grep).
- Parser mechanics: read directly from `FlagTreeItem.cpp` `read()` implementation.
- Token validity: all three tokens are canonical index-0 names in `DisplayFlags.cpp`.
- `showVisual` status: fully canonical group flag, not deprecated, not aliased —
  Agent 2's 85-occurrence count is legitimate.
- The v2.1 recommended string `"showBehaviorModels showForceFields showVisual"` is
  **correct and ready for implementation as-is**.

The only pre-existing error this review surfaces: Agent 7's §10 description listed
the flags as "showForceFields, showCollisionModels, showBoundingCollisionModels,
showInteractionForceFields, showMappings, showWireframe, showNormals" and said "Notice:
no `showVisual`." That list is the set of leaf-level flags mentioned on the SOFA docs
page — it is incomplete; the docs page omitted the group-level tokens (`showVisual`,
`showBehavior`, etc.). The source code is authoritative; `showVisual` is unambiguously
valid.
