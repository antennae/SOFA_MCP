# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Server

```bash
python sofa_mcp/server.py
```

This starts the MCP server at `http://127.0.0.1:8000/mcp`. On first launch, it regenerates the plugin cache (`.sofa_mcp_results/.sofa-component-plugin-map.json`) by scanning SOFA plugin libraries — requires `SOFA_ROOT` env var and SOFA runtime in `PYTHONPATH`.

## Running Tests

Tests require a running SOFA environment (SofaPython3 in `PYTHONPATH`, `~/venv/bin/python` pointing to the venv with SOFA).

```bash
# Run all tests
python -m pytest test/

# Run a specific test file
python -m pytest test/test_architect/test_scene_writer.py

# Run a single test
python -m pytest test/test_architect/test_scene_writer.py::TestSceneWriter::test_validate_scene_success
```

There is also a stray test file at `sofa_mcp/optimizer/test_patcher.py` (not under `test/`).

## Architecture

The server (`sofa_mcp/server.py`) is a FastMCP app that registers ~18 tools. All tool logic lives in submodules; `server.py` is thin wrappers only.

### Subprocess isolation boundary

**Critical design decision**: `scene_writer.py` and `component_query.py` execute SOFA via `~/venv/bin/python` subprocess — this is intentional isolation. `stepping.py` loads scenes in-process via `importlib`, which is faster but not isolated. Do not "simplify" subprocess calls into in-process calls.

### Scene format contract

Scenes passed to MCP tools must be **complete Python files** defining `createScene(rootNode)`. Validation wraps user content with SOFA imports and a `validate()` runner before spawning a subprocess.

Required physics components checked during validation. The check is now **plugin-category-based**, not a hand-list of class names — the embedded plugin map (built by `plugin_cache.py`) is consulted in the validation wrapper, and any class belonging to the relevant SOFA plugin counts. This means renamed classes (e.g. `GenericConstraintSolver` → `BlockGaussSeidel/UnbuiltGaussSeidel/NNCG ConstraintSolver`) don't require code updates here.

| Category | Plugin / class match |
|---|---|
| AnimationLoop | Plugin starts with `Sofa.Component.AnimationLoop`, plus `FreeMotionAnimationLoop` / `DefaultAnimationLoop` by name |
| ConstraintSolver | Plugin == `Sofa.Component.Constraint.Lagrangian.Solver` or `SoftRobots.Inverse` |
| TimeIntegration (ODE) | Plugin starts with `Sofa.Component.ODESolver.` |
| LinearSolver | Plugin starts with `Sofa.Component.LinearSolver.` |

Missing categories emit a soft `WARNING: Missing key components: ...` line — they do not fail validation by themselves. Hard failures come from `_PROMOTED_WARNING_PATTERNS` in `scene_writer.py` (constraint removed, invalid linear system, factory miss, mesh-file missing, zero-size mstate) which flip `success: false`.

The full set of registered alternatives the agent can discover via `search_sofa_components` is documented in `skills/sofa-mcp/sofa-mcp/SKILL.md` Scene Health Rules.

### Plugin cache

`sofa_mcp/architect/plugin_cache.py` builds `.sofa_mcp_results/.sofa-component-plugin-map.json` by loading every `.so` in `$SOFA_ROOT/lib` and diffing the ObjectFactory before/after. Load order matters: SoftRobots plugins first, then Sofa.* by descending name length, then others. This cache is read by `search_sofa_components` and `get_plugins_for_components`.

### Units convention

No project-wide unit-system enforcement. Each scene picks SI or mm/g/s and stays internally consistent — `summarize_scene` Rule 9 (in SKILL.md) will detect mismatches (gravity magnitude vs Young's modulus magnitude).

## Known Issues

- `math_sandbox.run_math_script`: uses bare `exec()` — not actually sandboxed.
- `stepping.py` `run_and_extract`: runs scenes in-process (no subprocess isolation).
- `inspect_mesh_topology`: determines topology by file extension only (unreliable).
- Python interpreter is hardcoded to `~/venv/bin/python` in `scene_writer.py`.
