# Bug: `query_sofa_component` cannot introspect components that require parent context

**Date:** 2026-05-14
**Reporter:** Claude (session: MOR_scene)
**Severity:** Medium — silently misleads callers into thinking registered components don't exist.
**Status:** RESOLVED (2026-06-13). The `query_sofa_component` rework (`docs/specs/2026-06-13-query-sofa-component-rework.md`) adopted suggested fixes (1) + (3): the scaffold now provides a template-matched `MechanicalObject` plus tet/tri topology, and registered classes that still can't be instantiated return `success: true` with `introspection: "metadata_only"` (never "misspelled"). In practice the improved scaffold went further than fix (3) anticipated — `SurfacePressureConstraint` and `CableConstraint` now introspect *fully* (23/27 fields), not metadata-only.

## What happened

While authoring a pneunet bending-actuator scene, I called:

```
query_sofa_component(component_name="SurfacePressureConstraint")
```

with the `SoftRobots` plugin loaded. The tool returned:

```
"Object type SurfacePressureConstraint<> was not created
 The component 'SurfacePressureConstraint' cannot be found in the factory."
```

and the `hints` field suggested the name was misspelled. Based on this I almost rewrote the whole scene against `SurfacePressureEquality` — a different, weaker API.

Cross-checking with `search_sofa_components(query="SurfacePressure")` returned `SurfacePressureConstraint` cleanly in the registered-class list. The component exists and is fully usable. The query tool was wrong.

## Root cause

`query_sofa_component` introspects by asking SOFA's object factory to construct a bare instance, then reads `Data` fields off the live object. This works for self-contained components (e.g. `SurfacePressureForceField`, `SurfacePressureEquality` — both queried successfully in the same session).

It fails for any component whose `init()` or constructor requires a parent context — typically:

- SoftRobots constraints (`SurfacePressureConstraint`, `CableConstraint`, …) — need a linked `MechanicalState` + triangle/edge topology.
- Most mappings (`BarycentricMapping`, `SubsetMultiMapping`, …) — need from-/to-mstates.
- Many topology-dependent force fields.

Passing `context_components=[{"type": "RequiredPlugin", "params": {"name": "SoftRobots"}}, {"type": "MechanicalObject", "params": {"template": "Vec3d"}}]` did not help — the factory still failed, presumably because no real topology container is in scope and no link between the constraint and the dummy mstate is wired up.

The error message also lies in a way that compounds the problem: it suggests "misspelling or plugin not loaded" when in fact the class IS registered.

## Suggested fixes (in increasing order of robustness)

1. **Improve the error message.** When the requested name exists in the registry but factory construction fails, say so explicitly — e.g. *"`SurfacePressureConstraint` is registered but cannot be instantiated in an empty context; pass a scaffolded parent node or use `search_sofa_components` to confirm existence."* Stops the false negative from looking like a "doesn't exist" answer.

2. **Auto-fallback to registry metadata.** When factory construction fails, fall back to whatever the class metadata exposes (class name, template parameters, plugin source, base classes) instead of returning an error. Even a partial response is more useful than a misleading one.

3. **Scaffold a parent node for introspection.** Before construction, build a temporary `Node` containing a dummy `MechanicalObject` (`Vec3d`), a `TriangleSetTopologyContainer` with one triangle, and an `EulerImplicitSolver`. Attempt construction inside it. This should cover most constraints, mappings, and topology-dependent FFs.

4. **Read `Data` schema off the C++ class directly,** without instantiating. SOFA's `BaseClass::create` machinery exposes Data registrations via reflection in some paths. Heavier lift but the cleanest solution — no fragile scaffold needed.

(3) is probably the best cost/benefit; (1) should be done regardless.

## How a caller should work around it today

- Treat `search_sofa_components` as the authoritative existence check, not `query_sofa_component`.
- For schema, write a candidate scene snippet using the API you know and pipe it through `write_and_test_scene`; SOFA's init errors will name unknown fields. Slower but accurate.
- For SoftRobots specifically, the plugin headers at `~/workspace/sofa/applications/plugins/SoftRobots/src/SoftRobots/component/constraint/` are the ground truth.
