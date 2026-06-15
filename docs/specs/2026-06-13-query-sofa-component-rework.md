# `query_sofa_component` rework — design spec

**Date:** 2026-06-13
**Status:** Design approved; implementation pending.
**Motivates:** Most-called MCP tool across sessions (17× in one MOR session). Three open issues from `docs/feedback_2026-05-20_cantilever_pendulum_session.md` (#1 template ignored, #2 no template list, #3 universal-field noise) plus the false-negative bug in `docs/feedback_2026-05-14_query_component_context_bug.md`.

## Problem

`query_sofa_component` introspects by instantiating the class in a dummy scaffold and reading `Data` fields off the live object. Four defects:

1. **`template` is not honored.** The default scaffold provides only a `Vec3d` `MechanicalObject`. Requesting `template="Rigid3d"` for a multi-template class (e.g. `PartialFixedProjectiveConstraint`) silently degrades: SOFA logs *"Requested template 'Rigid3d' is not compatible with the current context. Falling back to ... Vec3d"* and returns the **wrong** Data shapes (`fixed_array<bool,3>` instead of `<bool,6>`). Verified 2026-06-13.
2. **No discoverable template list.** Response has no `templates` field; the agent had to grep the `.cpp` to learn a class is registered for `Vec1/2/3/6`, `Rigid2/3`.
3. **Universal-field noise.** Every response carries 6 `BaseObject` fields (`name`, `printLog`, `tags`, `bbox`, `componentState`, `listening`) — constant across all components, pure context burn at 17+ calls/session.
4. **False-negative on context-dependent classes.** When instantiation fails (e.g. `SurfacePressureConstraint` needs real topology), the tool returns `"Could not create an instance"` and a "might be misspelled" hint — even though the class is registered. This misled an agent into rewriting a scene against the wrong API.

## Feasibility (verified 2026-06-13)

`Sofa.Core.ObjectFactory.getComponent(name)` returns a `ClassEntry` exposing — **without instantiation** — `templates` (set), `defaultTemplate`, `targets` (plugin), `description`, `locations` (header path), `aliases`, `dataAlias`. **Caveat:** `templates` only populates once the registering plugin is loaded (we have the plugin name from `plugin_cache`). It does **not** expose Data-field schema; that still requires a live instance.

Confirmed: a template-matched scaffold (Rigid3d `MechanicalObject`) makes `template="Rigid3d"` instantiate correctly and report `fixed_array<bool,6>`. A mismatched scaffold reproduces the silent Vec3d fallback bug.

## Approach

Keep instantiate-to-introspect as the source of `data_fields`/`links` (no reflection path exists for Data schema), but (a) make the scaffold **template-matched** so per-template shapes are correct, and (b) layer `ClassEntry` metadata on top — free, instantiation-independent, and turns a failed instantiation into a useful partial answer.

## Changes

### 1. Honor `template` (template-matched scaffold)

Resolve the effective template: `template` arg → else `ClassEntry.defaultTemplate` → else `Vec3d`. Build the scaffold's `MechanicalObject` to match:

| Template family | mstate template | position dim |
|---|---|---|
| `Rigid3d` / `Rigid3` | `Rigid3d` | 7 (x y z qx qy qz qw) |
| `Rigid2d` / `Rigid2` | `Rigid2d` | 3 (x y angle) |
| `Vec1d` | `Vec1d` | 1 |
| `Vec2d` | `Vec2d` | 2 |
| `Vec3d` (and unknown) | `Vec3d` | 3 |
| `Vec6d` | `Vec6d` | 6 |

Topology containers (triangle/tet) stay template-agnostic. After instantiation, report the **actual** instantiated template in `template` (read from the live object), which catches any residual SOFA-side fallback.

### 2. `templates` + metadata

Before building the scaffold, ensure the registering plugin is loaded (look it up via `plugin_cache`/`_is_registered_component`, then `SofaRuntime.importPlugin`). Read `ClassEntry` and add to every response: `templates` (sorted list), `default_template` (or `null`), `plugin`, `description`, `source_header` (first `locations` entry, or `null`).

### 3. Strip universal fields

Constant `_UNIVERSAL_DATA_FIELDS = {"name","printLog","tags","bbox","componentState","listening"}`. Drop these from `data_fields` by default. New param `include_universal: bool = False` opts back in. Applies only to the success path's `data_fields`.

### 4. Metadata fallback (kills the false negative)

When instantiation fails: call `_is_registered_component`. If registered, return a **success** response carrying the `ClassEntry` metadata (class name, plugin, templates, default_template, description, source_header) with `data_fields: null`, `links: null`, `introspection: "metadata_only"`, and a `note` explaining fields couldn't be introspected in the scaffold but the class exists and the listed templates are valid. Never emit "might be misspelled" for a registered class. Only when **not** registered do we return `success: false` (truly unknown / typo), keeping rename-suggestion logic (`_parse_replacements_from_error`, `renames.json`).

## Response shape

Success (full introspection):
```json
{
  "name": "...", "class_name": "PartialFixedProjectiveConstraint",
  "template": "Rigid3d",
  "templates": ["Rigid2d","Rigid3d","Vec1d","Vec2d","Vec3d","Vec6d"],
  "default_template": null,
  "plugin": "Sofa.Component.Constraint.Projective",
  "description": "...", "source_header": "/.../PartialFixedProjectiveConstraint.h",
  "data_fields": { "fixedDirections": {"type":"fixed_array<bool,6>", "value":"...", "help":"..."}, ... },
  "links": [...],
  "introspection": "full",
  "success": true
}
```

Registered but not instantiable (metadata only):
```json
{
  "class_name": "SurfacePressureConstraint",
  "templates": ["Vec3d"], "default_template": "Vec3d",
  "plugin": "SoftRobots", "description": "...", "source_header": "/.../SurfacePressureConstraint.h",
  "data_fields": null, "links": null,
  "introspection": "metadata_only",
  "note": "Registered, but could not be instantiated in the scaffold to read Data fields. The class exists and the listed templates are valid; to get field-level schema, write a candidate scene and run write_and_test_scene.",
  "success": true
}
```

Unknown class (typo / plugin truly absent): `success: false` with `hints`, `suggested_replacements` (unchanged from current behavior).

### Decisions (resolved)

- **`success` is not overloaded with introspection completeness.** `success: true` means "trustworthy answer about this component"; `introspection: "full"|"metadata_only"` carries completeness; `data_fields: null` is the explicit signal for strict callers. (Avoids re-triggering the 5-14 bug where an agent reads `success:false` and abandons a valid component.)
- **Requested/default template only**, not a full per-template matrix. The `templates` list lets the agent re-query a specific template. Returning `data_fields_by_template` for all templates duplicates the ~95% of fields that don't vary — contradicts change #3's context-economy goal.

## Out of scope (deferred)

- **Inline template-dependence annotation** (instantiate all templates, diff field type-strings, annotate only varying fields like `fixedDirections: {by_template:{Vec3d:"...3",Rigid3d:"...6"}}`). More robust than relying on the agent to re-query, but gold-plates the feedback and costs N instantiations per call. Revisit if agents are observed failing to re-query.
- **Reflection-based Data schema** (read Data registrations off the C++ class without instantiating). No API path found; heavy lift.

## Testing

- **Mocked unit tests** (`test/test_architect/test_component_query.py`, no real SOFA): keep `ClassEntry` access defensive so the existing `MagicMock`-based tests don't break; update them for the new additive fields; add a test that universal fields are stripped by default and present with `include_universal=True`.
- **Real-SOFA integration tests** (gated on SOFA, matching repo pattern):
  - `PartialFixedProjectiveConstraint` with `template="Rigid3d"` → `data_fields["fixedDirections"]["type"]` contains `bool,6`; with `template="Vec3d"` → `bool,3`.
  - `templates` contains the full registered set after plugin load.
  - `SurfacePressureConstraint` with empty context → `success: true`, `introspection: "metadata_only"`, `data_fields: null`, `plugin == "SoftRobots"`, no "misspelled" text.
  - A genuine typo (`SurfacePressureConstraintXYZ`) → `success: false`.
  - Universal fields absent by default; present with `include_universal=True`.

## Docs to update

- `skills/sofa-mcp/sofa-mcp/SKILL.md` — note `templates`/`template` round-trip and `introspection` field in the discovery workflow (keep tight per house style).
- `server.py` tool docstring for `query_sofa_component` (add `include_universal`, mention metadata fallback).
- `README.md` tool table (no shape change needed; mention template-awareness if space).

## Implementation note (2026-06-13, post-build)

**The fix landed bigger than this spec assumed.** The template-matched 4-point scaffold + tet/tri topology now **fully introspects `SurfacePressureConstraint`** (23 fields, `introspection: "full"`) and `CableConstraint` (27 fields) — the SoftRobots constraints that motivated the 5-14 false-negative bug are now *completely* introspectable, not merely `metadata_only`. So the "Registered but not instantiable" worked example above (which used `SurfacePressureConstraint`) is **stale**; the accurate `metadata_only` fixture is a class still needing wired from-/to-states, e.g. `BarycentricMapping` (`plugin: Sofa.Component.Mapping.Linear`). The integration test (`test_registered_but_not_instantiable_fallback`) uses `BarycentricMapping` accordingly. The `metadata_only` path and its contract are unchanged — only which classes exercise it. Final state: 74 tests pass across `test/test_architect/`.
