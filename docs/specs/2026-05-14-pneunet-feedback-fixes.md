# Plan: Fix sofa-mcp issues from 2026-05-14 pneunet session

## Context

During a pneunet bending-actuator authoring session, the reporter hit a cluster of MCP issues — most importantly, `validate_scene` returned `success: true` while SOFA had silently disabled a `FixedProjectiveConstraint` and the `MeshVTKLoader` had loaded zero positions (because the validator runs from `/tmp` and `__file__`-relative mesh paths broke). That single false positive cost ~5 round-trips. The full feedback in `docs/feedback_2026-05-14_pneunet_session.md` and `docs/feedback_2026-05-14_query_component_context_bug.md` lists 7 + 1 issues. The user asked for a plan covering **all** of them.

Goal: every `success: true` from the validator should mean "scene actually works"; introspection tools should never falsely claim a registered component is missing; renamed-component round-trips should be eliminated.

---

## Scope and phasing

The fixes split naturally into three milestones. Each ends in a **stop-and-chat gate** — do not proceed without user sign-off, since these change MCP response shapes the agent skill relies on.

### Milestone 1 — Validator correctness (Issues 1, 2, 7b)

**Files:** `sofa_mcp/architect/scene_writer.py`

1. **`init_warnings` field + success demotion (Issue 1)**
   - In `validate_scene()` (lines 154–215): after stdout/stderr capture, scan for a curated set of init-time signals:
     - `Index N not valid, should be [0,0]` / `Constraint will be removed`
     - `Invalid Linear System to solve (null size)`
     - `cannot be found in the factory`
     - `MechanicalObject … size 0` / zero-position MO inits
   - Build `init_warnings: [{pattern, line}]` on every response (success or fail).
   - If any **promoted** warning fires, flip `success: false` with `message: "Scene initialized but a structural warning was promoted to failure: …"`. Keep the raw stdout intact so the agent can see context.
   - Reuse the existing `_log_compact.compact_log` allowlist infrastructure — extend it with a "promoted" tier rather than building a parallel parser.

2. **Run validation in the scene's eventual directory (Issue 2)**
   - Today: `tempfile.NamedTemporaryFile(suffix=".py")` writes to `/tmp`, subprocess runs without `cwd` (lines 172–178).
   - Change: accept an optional `output_filename` parameter on `validate_scene()` (already plumbed through `write_and_test_scene`). When provided:
     - Resolve `out_dir = pathlib.Path(output_filename).absolute().parent`
     - Write tmp script as `<out_dir>/.sofa_mcp_validate_<hash>.py`
     - Pass `cwd=str(out_dir)` to `subprocess.run`
   - When not provided: keep current `/tmp` behavior (don't break the in-memory `validate_scene` callers).
   - The agent skill (SKILL.md) gets one line: "validate against the scene's eventual directory by passing `output_filename`".

3. **ConstraintSolver detection by base class, not name enumeration (Issue 7b)**
   - Currently `_assert_required_components` at line 79 hand-lists `NNCGConstraintSolver | QPInverseProblemSolver`. The agent feedback hit a false-positive with `BlockGaussSeidelConstraintSolver`.
   - Per the [[feedback_principle_over_enumeration]] memory: detect via SOFA base class instead — walk the tree and check `obj.getClass().hasParent("ConstraintSolver")` (or equivalent base-class API; fall back to a `BaseConstraintSolver` check). Same approach for `AnimationLoop`, `TimeIntegration`, `LinearSolver`.
   - Mirror the change in `_summary_runtime_template.py` Rule 5A (lines 304–368) so structural anomalies stay consistent.

**Stop-and-chat gate 1:** Run `pytest test/test_architect/test_scene_writer.py` and a hand pneunet-style scene with a deliberately-broken `__file__`-relative mesh path; show output. Confirm response shape changes are acceptable before continuing.

---

### Milestone 2 — Introspection truthfulness (Issues 3, 4, 5)

**Files:** `sofa_mcp/architect/component_query.py`, new `sofa_mcp/architect/renames.json`

4. **Truthful `query_sofa_component` error path (Issue 3)**
   - In the failure branch (lines 200–215): before returning, check whether `component_name` is in the plugin-map cache or `_try_get_registered_component_names()` output.
   - If registered: change message to `"<name> is registered (plugin: <X>) but cannot be instantiated in the dummy context. Try passing context_components or use search_sofa_components to confirm the schema."` — kill the "misspelled or plugin not loaded" hint in that case.
   - If not registered: keep the existing hint.

5. **Beefier dummy parent for instantiation (Issue 3, fix 3)**
   - Add a `TriangleSetTopologyModifier` + a single dummy triangle and a `BlockGaussSeidelConstraintSolver` to the registryQueryNode (lines 158–162). Most SoftRobots constraints, mappings, and topology-dependent FFs should construct against this.
   - Keep the existing context-passing API; the scaffold is the new *default*.

6. **Registry-metadata fallback (Issue 3, fix 2)**
   - On instantiation failure, return whatever we *do* know — class name, plugin source from `plugin_map`, and (if available) base classes via `Sofa.Core.ObjectFactory.getInstance().getEntry(name)` — in a `registry_metadata` field. Partial > misleading.

7. **`get_plugins_for_components` rename hints (Issue 4)**
   - In `get_plugin_for_component()` (line 284): when name is not in cache, attempt a factory `createObject` call. SOFA's own retired-component error message (e.g. "GenericConstraintSolver has been replaced since v25.12 by …") is the gold. Capture it, return:
     ```json
     {"plugin": null, "hint": "SOFA renamed this. Suggested replacements: [...]"}
     ```
   - Parse the bullet list out of the error to populate `suggested_replacements`. Cheap regex.

8. **`renames.json` for `search_sofa_components` (Issue 5)**
   - Add `sofa_mcp/architect/renames.json` with a starter dict scraped from observed SOFA error messages:
     ```json
     {
       "GenericConstraintSolver": ["BlockGaussSeidelConstraintSolver", "UnbuiltGaussSeidelConstraintSolver", "NNCGConstraintSolver"]
     }
     ```
   - In `search_sofa_components()` (lines 348–399): before the substring match, also check if any query token matches a retired key. If so, prepend the replacements to results with `{"name": ..., "replaces": "GenericConstraintSolver"}`.
   - Source the seed entries by **observing** factory errors during Milestone 2 testing — don't hand-curate a long list. Per [[feedback_principle_over_enumeration]], the file is a cache of observed renames, not a maintained enumeration.

**Stop-and-chat gate 2:** Demo: `query_sofa_component("SurfacePressureConstraint")` and `get_plugin_for_component("GenericConstraintSolver")` give helpful answers. User confirms before Milestone 3.

---

### Milestone 3 — Polish (Issues 6, 7a)

**Files:** `sofa_mcp/server.py`, `sofa_mcp/observer/diagnostics.py`, `sofa_mcp/observer/_diagnose_runner.py`

9. **Server crash logging (Issue 6)**
   - In `server.py` `main()` (lines 237–248): wrap `mcp.run()` in a try/except that logs to `~/.sofa_mcp_results/server.log` with timestamps before re-raising. No heartbeat/auto-restart — only "if it crashes again, we'll have something."
   - Add a `server_status` MCP tool that returns uptime, plugin-cache mtime, and last-N log lines. Cheap to add via FastMCP; eliminates "is the server alive?" guessing.

10. **NaN-aware `excessive_displacement` rule (Issue 7a)**
    - In `_check_excessive_displacement()` (`diagnostics.py` lines 78–119): when `max_displacement` is `inf` or `NaN`, emit a distinct anomaly `solver_diverged` with `{"first_nan_step": metrics["nan_first_step"]}` instead of the "infx the mesh extent" string. The existing `nan_first_step` metric (`_diagnose_runner.py` lines 483–486) already tracks this; just route it through to the anomaly payload.

**Stop-and-chat gate 3:** Smoke test the polish fixes; confirm before closing the branch.

---

## Skill / docs updates

Per [[feedback_concise_agent_docs]], `skills/sofa-mcp/sofa-mcp/SKILL.md` gets:

- A one-liner under Scene Health Rules: "validator now demotes init-warning patterns X/Y/Z to `success: false`; check `init_warnings` for the full list".
- A one-liner under file-writing flow: "pass `output_filename` so validation runs from the scene's directory — required for `__file__`-relative mesh loaders".

Update `CLAUDE.md` Architecture > "Required physics components": replace the hand-list with "any object inheriting from SOFA's `ConstraintSolver` / `AnimationLoop` / `OdeSolver` / `LinearSolver` base classes counts."

---

## Critical files

| Path | Lines | What changes |
|---|---|---|
| `sofa_mcp/architect/scene_writer.py` | 13–110, 154–230 | init-warnings parse + success demotion; `output_filename`→`cwd`; base-class checks |
| `sofa_mcp/architect/_summary_runtime_template.py` | 304–368 | mirror base-class checks (Rule 5A) |
| `sofa_mcp/architect/component_query.py` | 103–250, 254–299, 348–399 | truthful errors, scaffold, rename hints, renames.json lookup |
| `sofa_mcp/architect/renames.json` | new | seed retired→current map |
| `sofa_mcp/_log_compact.py` | extend | add "promoted" pattern tier reusable from validator |
| `sofa_mcp/server.py` | 237–248 | crash logging + `server_status` tool |
| `sofa_mcp/observer/diagnostics.py` | 78–119 | `solver_diverged` anomaly when displacement is non-finite |
| `skills/sofa-mcp/sofa-mcp/SKILL.md` | — | 2 one-liners |
| `CLAUDE.md` | 42–46 | base-class wording |

## Existing helpers to reuse (do NOT reimplement)

- `_strip_success_sentinel()` (scene_writer.py:16) — already filters stdout
- `compact_log` (`_log_compact`) — extend its allowlist tier rather than parsing in scene_writer
- `factory_utils.get_object_factory_instance()` / `collect_component_names_from_factory()` — for the registry-metadata fallback and rename-error capture
- `plugin_cache.load_plugin_map()` — for the "is the name actually registered?" check in `query_sofa_component` failure path
- `_maybe_auto_import_component_plugins()` (component_query.py:17) — already auto-imports plugin libs; do not duplicate

## Verification

End-to-end checks, in order:

1. **Repro the original bug.** Write a scene that loads `MeshVTKLoader(filename="some_local_mesh.vtk")` next to the output file path, with a `FixedProjectiveConstraint` on indices that only exist in the real mesh. Call `write_and_test_scene` with the correct `output_filename`. **Before fix:** `success: true`, MO inits at size zero. **After fix:** `success: true` with mesh loaded (because cwd is now correct) — and if we deliberately break the mesh path, `success: false` with `init_warnings` populated.
2. **`query_sofa_component("SurfacePressureConstraint")`** — must return a `registry_metadata` block (or full schema if scaffold succeeds), not a "misspelled" hint.
3. **`get_plugins_for_components(["GenericConstraintSolver"])`** — must return `suggested_replacements: ["BlockGaussSeidel...", "NNCG...", "Unbuilt..."]`.
4. **`search_sofa_components("Generic")`** — must include the modern replacements at the top with `replaces: "GenericConstraintSolver"`.
5. **`pytest test/`** — full suite. Update `test/test_architect/test_scene_writer.py` to cover the new `init_warnings` shape and the `output_filename`→`cwd` plumbing.
6. **Diagnose a known-NaN scene** — confirm anomaly is `solver_diverged` with `first_nan_step`, not the "infx the mesh extent" string.
7. **Smoke-test `server_status`** and check `~/.sofa_mcp_results/server.log` is written on a deliberate crash.
