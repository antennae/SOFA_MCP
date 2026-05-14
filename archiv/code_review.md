# SOFA MCP — Code Review

**Date:** 2026-03-17
**Scope:** All source files under `sofa_mcp/` and `test/`

---

## Summary

The most severe issues are: an unauthenticated remote-code-execution surface (`run_math_script`), a persistent `sys.modules` leak that causes in-process simulation pollution across tool calls, and critical API contract mismatches between production code and the test suite. Several important correctness bugs and error-handling gaps follow.

---

## Critical

### 1. `run_math_script` — Full RCE, zero sandboxing
**`sofa_mcp/architect/math_sandbox.py:19`**

`exec(script)` runs with no restrictions — no `__builtins__` override, no namespace isolation, no resource limits. Any agent or prompt injection that calls this tool gets unrestricted code execution as the server's OS user. The module name and tool docstring both claim "sandboxed", which is actively misleading.

```python
exec(script)   # no globals/locals restriction, no builtins restriction
```

**Fix:** Either run user scripts via `subprocess` (as `scene_writer.py` does) or restrict builtins:
```python
exec(script, {"__builtins__": {"print": print, "range": range, ...}}, {})
```

---

### 2. `sys.modules` leak in `run_and_extract`
**`sofa_mcp/observer/stepping.py:43`**

```python
sys.modules[module_name] = scene_module   # never removed
```

No corresponding `del sys.modules[module_name]` and no `try/finally` cleanup. Each call to `run_and_extract` grows `sys.modules` permanently. SOFA's in-process component registry gets polluted across calls, and scenes loaded later can inherit state from earlier runs.

**Fix:** Clean up in a `finally` block:
```python
try:
    ...
finally:
    sys.modules.pop(module_name, None)
```

---

### 3. `tmp_path` undefined risk in `finally` blocks
**`sofa_mcp/architect/scene_writer.py:216-256` and `:270-322`**

`tmp_path` is assigned inside the `with` block but referenced in `finally`. If `NamedTemporaryFile` itself raises (disk full, permission error), `tmp_path` is undefined and the `finally` block raises `NameError`, masking the real error. The temp file is also world-readable (`0o644`) until cleanup.

```python
with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
    tmp.write(validation_wrapper)
    tmp_path = tmp.name   # only assigned if the 'with' block succeeds

try:
    result = subprocess.run(...)
finally:
    if os.path.exists(tmp_path):   # NameError if NamedTemporaryFile raised
        os.remove(tmp_path)
```

**Fix:** Initialize `tmp_path = None` before the `with` block and guard with `if tmp_path and os.path.exists(tmp_path)`.

---

## High

### 4. `sample_data` vs `data_preview` key mismatch
**`sofa_mcp/observer/stepping.py:149`**

The function returns `data_preview`, but:
- The docstring documents `sample_data`
- `test/test_observer/test_stepping.py:54` asserts `"sample_data" in result`
- All downstream callers using the documented key get a `KeyError`

```python
return {
    ...
    "data_preview": data_preview,   # docstring says "sample_data"
}
```

**Fix:** Rename to `sample_data` or update the docstring and tests to match `data_preview`.

---

### 5. `suppress_stdout_stderr.__enter__` can permanently silence stdout
**`sofa_mcp/architect/plugin_cache.py:15-37`**

If `os.dup2(self.null_fd, 1)` succeeds but a subsequent step raises, the process's stdout is permanently redirected to `/dev/null` for the rest of the server's lifetime. `__enter__` also leaks `null_fd`, `old_stdout_fd`, and `old_stderr_fd` on any exception path before `__exit__` is reached.

**Fix:** Wrap `__enter__` in a `try/except` that restores any already-redirected FDs before re-raising.

---

### 6. Plugin cache error dict returned instead of raised — silently swallowed by callers
**`sofa_mcp/architect/plugin_cache.py:82-88`**

When `SOFA_ROOT` is unset or SofaRuntime is unavailable, `generate_and_save_plugin_map()` returns `{"error": "..."}` instead of raising. All callers discard the return value:

```python
try:
    plugin_cache.generate_and_save_plugin_map()   # return value discarded
except Exception:
    pass
```

Result: `search_sofa_components` silently returns empty results with no actionable hint about the misconfiguration.

**Fix:** Raise an exception, or at minimum have callers inspect the return value and surface the error.

---

### 7. `patch_scene` false-negative on identity patches in multi-op batches
**`sofa_mcp/architect/scene_writer.py:558-563`**

```python
if updated == original:
    return {"success": False, "message": "No changes applied.", ...}
```

A multi-op batch where all ops succeed but the final op is an identity replacement causes the entire batch to be reported as failed and rolled back — even though `applied_ops > 0`. The caller has no way to distinguish "nothing matched" from "all matched but net result was identical text".

**Fix:** Check `applied_ops > 0` as the success criterion rather than comparing the final strings.

---

### 8. Non-atomic file write in `update_data_field` — data loss on crash
**`sofa_mcp/optimizer/patcher.py:132-133`**

```python
with open(scene_path, "w", encoding="utf-8") as f:
    f.write(new_source)
```

The file is truncated immediately on open. A crash, disk-full, or exception during `f.write()` destroys the original with no backup.

**Fix:** Write to a temp file in the same directory, then `os.replace(tmp, scene_path)` for an atomic swap.

---

### 9. Output directory resolved from CWD, not project root
**`sofa_mcp/observer/stepping.py:109`**

```python
results_dir = os.path.abspath(".sofa_mcp_results")
```

`plugin_cache.py` computes the same directory from `__file__`. When the server is launched from a different working directory, simulation results and the plugin cache land in different places.

**Fix:** Compute from `__file__` consistently, as `plugin_cache.get_cache_path()` does.

---

## Medium

### 10. `inspect_mesh_topology` discards the loaded mesh and classifies by extension only
**`sofa_mcp/architect/mesh_inspector.py:165-186`**

```python
trimesh.load(mesh_path)   # return value discarded
file_extension = os.path.splitext(mesh_path)[1].lower()
if file_extension == ".vtk" or file_extension == ".msh":
    return "Volumetric mesh ..."
```

The loaded mesh object is thrown away. trimesh can determine topology from the mesh itself (tetrahedra vs. triangles). Any surface `.vtk` file is incorrectly classified as volumetric, causing LLM agents to select wrong SOFA topology containers.

**Fix:** Inspect `mesh.faces` / `mesh.cells` on the loaded object to determine actual topology type.

---

### 11. Validation warnings never fail validation
**`sofa_mcp/architect/scene_writer.py:53-66`**

`_assert_required_components` only `print()`s to stdout, never calls `sys.exit(1)`. `validate_scene` returns `success: True` for scenes missing `AnimationLoop`, `TimeIntegration`, or `LinearSolver`. The warning is buried in unstructured `stdout` where agents may miss it.

**Fix:** Either exit on missing required components, or promote the warning to a structured field in the return dict (e.g., `"warnings": [...]`).

---

### 12. Empty step slice + `calculate_metrics` raises `IndexError`, swallowed silently
**`sofa_mcp/observer/stepping.py:235-282`**

`raw_data[start_step:end_step]` is empty when `start_step >= end_step`. The `arr[-1] - arr[0]` path then raises `IndexError`, caught by the outer `except` and returned as a generic `{"success": False}`, losing any partial results.

**Fix:** Guard with `if len(arr) == 0: return {"success": False, "error": "Empty step range"}` before computing metrics.

---

### 13. `_AUTO_IMPORTED_PLUGINS` module-level flag causes test contamination
**`sofa_mcp/architect/component_query.py:13`**

```python
_AUTO_IMPORTED_PLUGINS = False
```

Set to `True` permanently after the first import attempt (including mock detection). In the test suite, a test that triggers the mock branch prevents all subsequent tests in the same process from loading real plugins. In production, a transient error during startup permanently skips plugin loading for the lifetime of the process.

**Fix:** Use a function-level guard or allow forced re-initialization via a parameter.

---

### 14. `write_scene` allows arbitrary filesystem writes
**`sofa_mcp/architect/scene_writer.py:325-342`**

```python
output_path = pathlib.Path(output_filename).absolute()
output_path.parent.mkdir(parents=True, exist_ok=True)
```

No path restriction on `output_filename`. An LLM agent or prompt injection can write to `/etc/cron.d/`, `~/.bashrc`, or any other path writable by the server process. `mkdir(parents=True, exist_ok=True)` also creates arbitrary directory trees.

**Fix:** Enforce an allowlist of output directories (e.g., a configurable `SOFA_MCP_OUTPUT_DIR`).

---

### 15. `summarize_scene` JSON missing `has_mechanical_object` and `baseline_components_present` checks
**`sofa_mcp/architect/scene_writer.py:177-180`**

The generated wrapper outputs only 3 checks (`has_animation_loop`, `has_constraint_solver`, `has_time_integration`). `test/test_architect/test_scene_writer.py:29` asserts `has_mechanical_object` and `baseline_components_present` exist — these tests will always fail.

**Fix:** Either add the missing checks to the generated wrapper, or remove the assertions from the tests to match actual behavior.

---

### 16. Multi-token prefix query silently degrades to substring mode
**`sofa_mcp/architect/component_query.py:384-386`**

```python
if prefix_mode:
    return any(n.startswith(t) for t in tokens) if len(tokens) == 1 else all(t in n for t in tokens)
```

When query contains multiple tokens and a `*` suffix (e.g., `"tet topology*"`), the prefix flag is consumed but the logic falls back to `all(t in n)` — identical to non-prefix behavior. The `*` has no effect for multi-token queries. This is undocumented.

**Fix:** Apply `startswith` to the last token and `in` to all preceding tokens, or document the limitation.

---

## Low

### 17. Hardcoded plugin exclusion list in cache generation
**`sofa_mcp/architect/plugin_cache.py:99-106`**

```python
if any(s in plugin_name for s in ["SofaValidation", "SofaExporter", "SofaSimpleFem"]):
    continue
```

Will miss newly problematic plugins as the SOFA ecosystem evolves. Should be configurable.

---

### 18. All tests in `test_scene_writer.py` use stale `add_scene_content` API
**`test/test_architect/test_scene_writer.py` — all 7 test methods**

Production `_build_scene_source` is a passthrough that expects `createScene(rootNode)`. Every test defines `def add_scene_content(rootNode):` instead. `test_write_scene_writes_file` also asserts `"def createScene" in contents` (line 59) — which will never appear since no wrapper is generated. **All 7 tests in this file are broken against the current production code.**

---

### 19. `find_indices_by_region` on multi-mesh files returns meaningless indices
**`sofa_mcp/architect/mesh_inspector.py:313-319`**

```python
for g in mesh.geometry.values():
    all_pts.append(g.vertices)
points = np.concatenate(all_pts, axis=0)
```

Returned indices index into the concatenated array, not any single geometry's vertex buffer. Agents using these indices for SOFA boundary condition assignment will silently get wrong results.

---

### 20. `test_stepping.py` asserts the non-existent `sample_data` key
**`test/test_observer/test_stepping.py:54`**

Companion to issue #4. The test asserts `"sample_data" in result` but production returns `data_preview`. The test will always fail.

---

## Test Coverage Gaps

| Area | Gap |
|------|-----|
| `process_simulation_data` | Zero tests |
| `get_plugins_for_components` | Zero tests |
| `find_indices_by_region` | Zero tests |
| `patch_scene` | Only `insert_after` and missing anchor tested; `replace`, `prepend`, `append`, multi-op, and `count > 1` are untested |
| `suppress_stdout_stderr` | Zero tests |
| `generate_and_save_plugin_map` | Zero tests |
| `plugin_cache.get_cache_path()` fallback branch | Untested |

---

## Priority Order for Fixes

| Priority | Issue | Reason |
|----------|-------|--------|
| 1 | #1 — `exec()` RCE | Active security risk on any networked deployment |
| 2 | #18, #20 — Broken tests | CI is meaningless until tests reflect actual API |
| 3 | #4 — `sample_data` key mismatch | Breaks every caller of `run_and_extract` |
| 4 | #2 — `sys.modules` leak | Server degrades over time; state pollution across simulations |
| 5 | #8 — Non-atomic write | Data loss on any crash during `update_data_field` |
| 6 | #14 — Arbitrary filesystem write | Prompt injection escalation path |
| 7 | #3, #5 — FD and file cleanup | Correctness on error paths |
