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

**For visual feedback:** after step 7, call `render_scene_snapshot(scene_path, steps=N)` to get a PNG of the final state. The renderer reads explicit triangles from any `OglModel` in the scene, so for clean output add an `OglModel` (with `IdentityMapping` or `BarycentricMapping` to your mechanical state) before rendering. Without a visual model the renderer falls back to a point glyph cloud — useful as a debug view, not as a presentable image.

## Workflow: debug an existing scene that runs but misbehaves

When the user says "this scene runs but the behavior is wrong" (robot doesn't move, deformation too small, things pass through, position explodes), this is a **behavioral bug**, not an authoring bug. There's no traceback; the scene is physically wrong.

The loop is: **symptom → sanity report → run + measure → hypothesis → modify minimally → re-measure**. Start with `diagnose_scene(scene_path, steps=N)` — it folds the 9 Health Rules and runtime smell tests (`excessive_displacement`, `solver_iter_cap_hit`, `inverse_objective_not_decreasing`, `qp_infeasible_in_log`, `multimapping_node_has_solver`) into one response with per-MO metrics and captured solver logs. Don't recommend a fix without running the modified scene to falsify or confirm.

For the full investigative procedure, the symptom-to-hypothesis table, and a worked example, read `references/debugging-playbook.md`.

## Scene Health Rules (The Architect's Checklist)

Agent-facing summary of what makes a SOFA scene physically well-formed. When the recommended class doesn't fit, look up alternatives in `references/component-alternatives.md` (organized by category) or call `search_sofa_components('keyword')` for live discovery.

1. **Plugins.** Every component class needs a `RequiredPlugin`. Resolve via `get_plugins_for_components`.

2. **Animation Loop.** Use `FreeMotionAnimationLoop` if the scene has any `*LagrangianConstraint`, `*Actuator`, or `*ConstraintCorrection`; `DefaultAnimationLoop` otherwise. Don't omit the loop — SOFA silently auto-instantiates `DefaultAnimationLoop`, hiding constraint-related bugs.

3. **Time Integration.** Every unmapped `MechanicalObject` needs an integrator in its ancestry. Default: `EulerImplicitSolver` for almost everything; `EulerExplicitSolver` only for explicit dynamics with bounded stiffness.

4. **Linear Solver.** Implicit ODE solvers need a linear solver in the same node or a descendant (an ancestor's solver does NOT count). Recommended: `SparseLDLSolver` with `template="CompressedRowSparseMatrixMat3x3d"`. Backup: `CGLinearSolver` for very large systems where direct factorization is too expensive.

5. **Constraint Handling.** Under `FreeMotionAnimationLoop`, two distinct components are required:
   - **Constraint solver** at root: `NNCGConstraintSolver` for forward simulation, `QPInverseProblemSolver` for any inverse-problem scene (any class from the `SoftRobots.Inverse` plugin requires `QPInverseProblemSolver`).
   - **Constraint correction** in each deformable subtree: `GenericConstraintCorrection` is the safe default.

6. **ForceField Mapping.** Every `ForceField` must reach a `MechanicalObject`. Most force fields look up the `MechanicalObject` in their ancestor chain; pair/mixed-interaction force fields (e.g. `SpringForceField`, `JointSpringForceField`) instead reference two MOs explicitly via `object1`/`object2` Data fields, which may live in different subtrees.

7. **Topology Containers.** Volumetric force fields (e.g. `TetrahedronFEMForceField`) need a volumetric topology container or mesh. `BarycentricMapping`'s parent must be volumetric — except when the parent has a shell FEM like `TriangularFEMForceField` or `QuadBendingFEMForceField`.

8. **Collision pipeline.** If any node has a `*CollisionModel`, the root needs five components. Defaults: `CollisionPipeline`, `BruteForceBroadPhase`, `BVHNarrowPhase`, `MinProximityIntersection` (or `LocalMinDistance` for tighter contacts), `CollisionResponse`.

9. **Units consistency.** Pick SI or mm/g/s and stay internally consistent. Detect from gravity magnitude `|g|`:
    - `|g| ≈ 9.81` → SI; `youngModulus < 100` is suspicious
    - `|g| ≈ 9810` → mm/g/s; `youngModulus > 1e9` is suspicious
    - `|g| ≈ 9180` → likely typo of `-9810`

## Visual setup tips (reference, not enforced)

- **Visual Model:** for rendering, map the mechanical state to an `OglModel` via `IdentityMapping` or `BarycentricMapping`. Other registered concrete classes: `VisualModelImpl`, `CylinderVisualModel`, `VisualMesh`, `OglShaderVisualModel`. (`VisualModel` is an abstract base class; `addObject("VisualModel")` works at runtime as an alias to `VisualModelImpl`.)
- **Visual Style:** for GUI runs, add a `VisualStyle` at root with `displayFlags="showBehaviorModels showForceFields showVisual"`.

## Tool reference

Full schemas are exposed via the MCP `tools/list` endpoint. Quick reference by category:

| Category | Tools |
|---|---|
| Scene authoring | `validate_scene`, `summarize_scene`, `write_scene`, `write_and_test_scene`, `load_scene`, `patch_scene` |
| Component lookup | `query_sofa_component`, `search_sofa_components`, `get_plugins_for_components` |
| Mesh | `mesh_stats`, `find_indices_by_region`, `resolve_asset_path`, `generate_volume_mesh` |
| Simulation | `run_and_extract`, `process_simulation_data`, `update_data_field`, `render_scene_snapshot` |
| Diagnose | `diagnose_scene` (sanity report: Health Rules + runtime smell tests + per-MO metrics + truncated logs) |
| Probes | `enable_logs_and_run` (toggle printLog on targets, animate, capture filtered logs), `perturb_and_run` (apply Data-field overrides before init, animate, return per-MO metrics) |
| Misc | `health_check` |

For raw HTTP/curl debugging (rarely needed — agents use the MCP transport directly), see `references/curl-examples.md`.

### `verbose` flag on log-returning tools

`diagnose_scene`, `validate_scene`, and `summarize_scene` accept `verbose: bool = False`. By default they compact captured SOFA stdout/stderr to plugin loads, convergence summaries, errors/warnings, and tracebacks — the f-vector dumps from `EulerImplicitSolver`'s `printLog` are dropped. The response carries `log_lines_dropped: int` when the filter removed lines.

Flip `verbose=True` only when you suspect the filter dropped a useful line: e.g. an unfamiliar `[INFO]` channel, an obscure deprecation message, or when the agent needs to debug the filter itself. Smell-test detection (`qp_infeasible_in_log` etc.) always runs against the full pre-compaction log, so `verbose=False` does not hide detected anomalies — it only hides the raw text those anomalies were derived from.

### Probe tools (Step 4)

`enable_logs_and_run` and `perturb_and_run` are follow-up instruments after `diagnose_scene` flags an anomaly. Use `enable_logs_and_run` when you want to see what a specific solver, mapping, or constraint says at runtime (the targets argument matches by class name like `"EulerImplicitSolver"` or by node-path fragment like `"/leg_0/odesolver"`). Use `perturb_and_run` to test a hypothesis by modifying one Data field and re-measuring — e.g. halve `youngModulus`, see if displacement doubles.

## Conventions

- The scene file must define `def createScene(rootNode):`.
- Pick one unit system per scene and stay internally consistent (Rule 9 enforces this). Common choices: SI (`gravity=(0,-9.81,0)`, YM in Pa) or mm/g/s (`gravity=(0,-9810,0)`).
- After writing, a scene can be opened in `runSofa` via `runSofa <scene>.py` for human GUI inspection.
