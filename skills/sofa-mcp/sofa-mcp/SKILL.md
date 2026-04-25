---
name: sofa-mcp
description: Provides tools for authoring and validating SOFA simulation scenes, looking up SOFA components and their plugins, meshing STL surfaces to volumetric VTK, running simulations, and rendering snapshots. Use this skill when turning a natural-language SOFA scene request into a runnable scene, or when running and analyzing a SOFA simulation.
---

# SOFA MCP Server Skill

## Server bootstrap

The MCP server must be running on `http://127.0.0.1:8000/mcp` before any tool call. Start it once per session:

```bash
~/venv/bin/python sofa_mcp/server.py
```

Wait for `Uvicorn running on http://127.0.0.1:8000` in the log before the first tool call. First start takes ~30 seconds while the plugin cache builds.

## Workflow: natural language → validated scene

When the user says "I want a SOFA scene that ...":

1. **Clarify minimally.** Only ask for details that block scene authoring (geometry, boundary conditions, actuators, units).
2. **Resolve plugins in one batch.** Collect every SOFA component class you plan to use, then call `get_plugins_for_components` with the full list. Never guess plugin names.
3. **Inspect details on demand.** For unknown component fields or links, call `query_sofa_component`. Read its `links` and `hints` for dependency requirements (e.g., a hint that the component needs an `mstate` means you must add a `MechanicalObject` in the same node or an ancestor).
4. **Write `createScene(rootNode)`.** Group all `RequiredPlugin` calls at the top. Apply the Scene Health Rules below.
5. **Self-check via summarize.** Call `summarize_scene(script_content)`. Read the `checks` field and the `nodes`/`objects` arrays. If anything in the Health Rules is missing, fix the draft before validating.
6. **Validate.** Call `validate_scene(script_content)` for a real init + animate-one-step dry run. On failure, read the traceback alongside the scene summary and fix.
7. **Write.** Call `write_scene(script_content, output_filename)` once validation passes.

**For mesh-driven scenes:** before step 4, if the user has an STL but the FEM/topology you're planning needs tetrahedra, call `generate_volume_mesh(stl_path)` first. Use `mesh_stats` to learn the bounding box and element counts. Use `find_indices_by_region` to identify boundary or tip vertex indices for fixing/actuating.

**For visual feedback:** after step 7, call `render_scene_snapshot(scene_path, steps=N)` to get a PNG of the final state. Useful for verifying the simulation produces the deformation you expected.

## Scene Health Rules (The Architect's Checklist)

Every valid SOFA scene must satisfy:

1. **Plugins:** every component class needs a corresponding `RequiredPlugin` (use `get_plugins_for_components` to resolve).
2. **Animation Loop:** root must have either `FreeMotionAnimationLoop` (with constraints) or `DefaultAnimationLoop`.
3. **Time Integration Solver:** every `MechanicalObject` needs an `EulerImplicitSolver` (or `RungeKutta4Solver`) in its ancestry.
4. **Linear Solver:** implicit time solvers require a linear solver. Default to `SparseLDLSolver` with `template="CompressedRowSparseMatrixMat3x3d"` for FEM. Use `CGLinearSolver` only for very large meshes (>100k nodes).
5. **Constraint Handling:** `FreeMotionAnimationLoop` requires a constraint solver at root and a constraint correction on each mechanical node. Reasonable defaults: `NNCGConstraintSolver` for forward-sim soft tissue/soft robotics, `QPInverseProblemSolver` for inverse-problem (`SoftRobots.Inverse`) scenes; `GenericConstraintCorrection` is a safe correction default. If you need other variants (`LCPConstraintSolver`, `BlockGaussSeidelConstraintSolver`, `LinearSolverConstraintCorrection`, etc.), use `search_sofa_components` to discover what your SOFA build offers and `get_plugins_for_components` to resolve plugins.
6. **ForceField Mapping:** every `ForceField` must live in a node that has a `MechanicalObject`.
7. **Topology Containers:** volumetric force fields (e.g., `TetrahedronFEMForceField`) require a matching topology container (e.g., `TetrahedronSetTopologyContainer`) or a generator like `RegularGridTopology`.
8. **Visual Model:** for rendering, map the mechanical state to an `OglModel` or `VisualModel` via a `Mapping` (`IdentityMapping`, `BarycentricMapping`, etc.).
9. **Visual Style (GUI only):** add a `VisualStyle` with `displayFlags="showBehavior"` if the scene will be opened in `runSofa`.

## Tool reference

Full schemas are exposed via the MCP `tools/list` endpoint. Quick reference by category:

| Category | Tools |
|---|---|
| Scene authoring | `validate_scene`, `summarize_scene`, `write_scene`, `write_and_test_scene`, `load_scene`, `patch_scene` |
| Component lookup | `query_sofa_component`, `search_sofa_components`, `get_plugins_for_components` |
| Mesh | `mesh_stats`, `find_indices_by_region`, `resolve_asset_path`, `generate_volume_mesh` |
| Simulation | `run_and_extract`, `process_simulation_data`, `update_data_field`, `render_scene_snapshot` |
| Misc | `health_check` |

For raw HTTP/curl debugging (rarely needed — agents use the MCP transport directly), see `references/curl-examples.md`.

## Conventions

- All scenes use **[mm, g, s]** units.
- The scene file must define `def createScene(rootNode):`.
- After writing, a scene can be opened in `runSofa` via `runSofa <scene>.py` for human GUI inspection.
