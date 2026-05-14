# sofa-mcp feedback — pneunet authoring session

**Date:** 2026-05-14
**Reporter:** Claude (session: MOR_scene)
**Task:** Build a Mosadegh-style fast PneuNet bending actuator from scratch — gmsh-based mesh + SOFA scene with `SurfacePressureConstraint`, validated end-to-end via the MCP.

The session converged: scene validates, renders cleanly, bends to equilibrium under pressure. But several MCP-side issues cost real time. Notes below ordered by severity.

## 1. `validate_scene` / `write_and_test_scene` reports `success: true` even when init-time constraint warnings silently disable the scene

**Worst issue of the session.** I spent ~5 round-trips chasing why my `MeshVTKLoader` produced zero positions. The validator response was:

```json
{"success": true, "message": "Scene validated and saved.", ...}
```

with `stdout` containing **110 lines** of:

```
[WARNING] [FixedProjectiveConstraint(clamp)] Index 48 not valid, should be [0,0]. Constraint will be removed.
[WARNING] [SparseLDLSolver] Invalid Linear System to solve (null size)…
```

The scene initialized and stepped one step, so the success criterion was met — but the constraint was silently removed and the resulting "validated" scene was structurally broken. The success flag pulled me into investigating cantilever-style data-link fixes (`position="@loader.position"`, `tetrahedra="@loader.tetrahedra"`, etc.) when the actual cause was completely different.

**Root cause** (see issue 2): the validator runs the scene from `/tmp/tmp<hash>.py`, so `os.path.dirname(os.path.abspath(__file__))` evaluates to `/tmp`, the `MeshVTKLoader` reads a non-existent `/tmp/pneunet.vtk`, and the MO inits at size zero — but no error is raised.

**Suggested fixes:**

1. **Promote a curated set of init-time `[WARNING]` lines to `success: false`.** At minimum: `Index N not valid, should be [0,0]`, `Invalid Linear System to solve`, `cannot be found in the factory` from the SOFA registry. These mean the scene didn't really validate.
2. **Add a structured field** like `"init_warnings": [...]` on every response so the caller can decide. Today these warnings are buried inside `stdout` and the agent has to grep them out by hand.
3. **Promote "constraint removed" warnings even louder** — they're a near-guaranteed sign the scene won't behave.

## 2. `write_and_test_scene` runs scenes from `/tmp`, breaking `__file__`-relative paths

The validator copies `script_content` to `/tmp/tmp<hash>.py` and exec's it there. Any scene that resolves mesh/data files relative to `__file__` (the natural pattern for a checked-in scene) will silently fail when validated — the loader returns "I loaded nothing" rather than an error, and you get the constraint-vs-empty-MO chase described above.

I worked around it with a fallback:

```python
HERE = (os.path.dirname(os.path.abspath(__file__))
        if "__file__" in globals() and os.path.exists(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "pneunet.vtk"))
        else "/home/sizhe/workspace/MOR/scene/pneunet")
```

which is ugly and only works because I know the on-disk path up-front.

**Suggested fix:** before exec'ing, copy or symlink the script into the same directory as `output_filename` (or its declared dir if `output_filename` is just a basename), and run from there. Then `__file__` resolves correctly and scenes written to disk behave identically under validation and `runSofa`.

Alternative: pass an explicit `working_directory` argument to the tool.

## 3. `query_sofa_component` can't introspect anything that needs parent context

Already documented in `feedback_2026-05-14_query_component_context_bug.md` — flagging here for cross-reference. `SurfacePressureConstraint` returned `"cannot be found in the factory"` with a `"misspelled or plugin not loaded"` hint, which was simply wrong (the class is registered; `search_sofa_components` found it). Combined with issue 1, this almost made me rewrite the scene against a different constraint API.

## 4. `get_plugins_for_components` could surface SOFA-side rename hints, but doesn't

When asking for `FixedConstraint` and `GenericConstraintSolver`, the response was:

```json
{"FixedConstraint": "Component not found in cache",
 "GenericConstraintSolver": "Component not found in cache", ...}
```

When I then *used* `GenericConstraintSolver` in a scene, SOFA itself printed a rich, actionable error:

> `GenericConstraintSolver has been replaced since v25.12 by a set of new components, whose names relate to the method used:`
> &nbsp;&nbsp;`- BlockGaussSeidelConstraintSolver (if you were using this component without setting 'resolutionMethod' …)`
> &nbsp;&nbsp;`- UnbuiltGaussSeidelConstraintSolver (…)`
> &nbsp;&nbsp;`- NNCGConstraintSolver (…)`

`get_plugins_for_components` should fold this in: when a name isn't found, attempt a factory query (which surfaces the renamed-component message), and return that as a `"hint"` field. Without it the agent has to do a round-trip through `write_and_test_scene` just to discover a rename.

## 5. `search_sofa_components` is pure substring; doesn't help find renamed replacements

Searching `"Generic"` returned `GenericConstraintCorrection` and `SerialPortBridgeGeneric` but not the actual modern replacements (`BlockGaussSeidelConstraintSolver`, `NNCGConstraintSolver`, `UnbuiltGaussSeidelConstraintSolver`). Substring search can't span renames.

**Suggested fix:** maintain a small `renames.json` mapping retired SOFA class names → current equivalents (you can scrape these out of SOFA's own factory error messages over time). When a search query matches a retired name, include the modern replacements at the top of results with a `"replaces"` annotation.

## 6. MCP server crashed mid-session and required manual restart

After ~40 minutes of normal use (no obviously heavy operations between healthy calls), `mesh_stats` returned `MCP error -32000: Connection closed`. The Python process was still alive (`pgrep` showed it), but the registered stdio transport was broken — I couldn't reach the server at all and the user had to `/mcp` reconnect manually.

No reproducer; flagging it in case the server log captured anything. Worth adding a heartbeat or graceful-recovery path so a transient crash doesn't kill mid-session productivity.

## 7. Smaller observations (not blockers, just polish)

- **`render_scene_snapshot` was a real workflow win.** Calling it at `steps=1` gave me an instant "did I screw up the geometry" signal that text-based diagnostics can't. Worth featuring more prominently in the README.
- **`diagnose_scene` is excellent.** The `solver_iter_cap_hit` rule and per-step `solver_iterations` array let me localize a NaN to *step 11* with no manual log scraping.
- **`find_indices_by_region` saved me writing throwaway numpy.** Great fit for boundary-condition workflows.
- **Health rules need `"max_displacement_per_mo": null` handling.** When the sim NaNs partway, `max_displacement` becomes `null` but the `excessive_displacement` rule still fires with `"Max displacement inf is infx the mesh extent"` — the message is wrong-flavoured for a NaN case (should say "NaN at step N" instead).
- **One-shot warning that one was ignored:** the validator always prints `WARNING: Missing key components: ConstraintSolver` even with `BlockGaussSeidelConstraintSolver` correctly wired (it IS the constraint solver). Probably the health rule looking for class name `ConstraintSolver` exactly.

## Top three to fix first

1. **Validator success ≠ scene works.** Promote constraint-removal warnings and missing-file silent failures to `success: false`. (Issue 1.)
2. **Run validation in the scene's eventual on-disk directory.** Eliminates the `__file__`-relative trap. (Issue 2.)
3. **Surface SOFA's rename hints through `get_plugins_for_components` / `search_sofa_components`.** Cheap to add, big agent-side speedup. (Issues 4–5.)
