# SOFA MCP

> An MCP server that bridges LLM agents with the [SOFA](https://www.sofa-framework.org/) physics simulation framework.

<!-- TODO: hero demo video (target: trimmed mp4 from mcp_demo/d-4.webm, embedded with <video> tag) -->

The server exposes SOFA's component registry, scene validation, STL→volumetric meshing, simulation stepping, and headless rendering as MCP tools, so an LLM agent can author and verify scenes directly from natural-language prompts. 

## Quick start

### Prerequisites

- SOFA Framework built with `SofaPython3`, `SoftRobots`, and `SoftRobots.Inverse`. `SOFA_ROOT` set to the install dir; `PYTHONPATH` includes `$SOFA_ROOT/plugins/SofaPython3/lib/python3/site-packages`.
- Python 3.10+ in a venv.

### Install Python deps

```bash
poetry install
# or
~/venv/bin/pip install fastmcp trimesh gmsh pymeshlab scipy pyvista
```

### Run the server

```bash
~/venv/bin/python sofa_mcp/server.py
```

The server listens on `http://127.0.0.1:8000/mcp` (streamable HTTP, JSON-RPC 2.0). On first launch it scans `$SOFA_ROOT/lib` to build the plugin → component cache (`.sofa_mcp_results/.sofa-component-plugin-map.json`); this takes ~30 seconds and only happens once.

> A `Dockerfile` packaging the entire SOFA build + plugins is in progress. Until it lands, the native install above is the supported path.

## Worked example: tri-leg cable robot

A natural-language prompt to the agent:

> I want a SOFA scene that has 3 vertical beams (as legs), fixed at one end, then each leg has 1 cable pulling so that it is actuated. The 3 cables have one common start point and end at the tip of the leg. Please help me implement the scene, validate, and output.

The agent goes through roughly these tool calls:

1. **`search_sofa_components`** to find solver / topology / forcefield components for FEM (`EulerImplicitSolver`, `SparseLDLSolver`, `RegularGridTopology`, `TetrahedronFEMForceField`).
2. **`get_plugins_for_components`** to resolve their required plugins in one batch.
3. The agent writes the `createScene(root)` body, gathering all `RequiredPlugin` calls at the top.
4. **`validate_scene`** confirms the scene initializes and animates one step.
5. **`write_scene`** saves it to [`tri_leg_cables.py`](./tri_leg_cables.py).
6. **`render_scene_snapshot`** runs the simulation for 150 steps and renders the final state:

![Three colored legs bending asymmetrically toward a common point](assets/tri_leg_cables_snapshot.png)

The cables in the rendered scene contract by 22mm, 12mm, and 5mm — asymmetric values added by hand after the agent's initial draft, to make the deformation visually clear. Each leg's color comes from its `OglModel`; the renderer auto-discovers every `MechanicalObject` and pulls colors from sibling visual nodes.

## What's inside

| Category | Tools | Purpose |
|---|---|---|
| Scene authoring | `validate_scene`, `summarize_scene`, `write_scene`, `write_and_test_scene`, `load_scene`, `patch_scene` | Generate, validate, save, and patch SOFA scene files |
| Component lookup | `query_sofa_component`, `search_sofa_components`, `get_plugins_for_components` | Find components in the registry; resolve their plugins |
| Mesh | `mesh_stats`, `find_indices_by_region`, `resolve_asset_path`, `generate_volume_mesh` | Inspect meshes; convert STL surfaces to volumetric VTK via gmsh |
| Simulation | `run_and_extract`, `process_simulation_data`, `update_data_field`, `render_scene_snapshot` | Run scenes, extract data, render final-frame snapshots |
| Misc | `health_check` | Server liveness |

18 tools total. Full schemas are exposed via MCP `tools/list`; per-tool documentation lives in [`skills/sofa-mcp/sofa-mcp/SKILL.md`](skills/sofa-mcp/sofa-mcp/SKILL.md).

## Architecture

```
LLM client (Claude / Gemini / Cursor / Copilot CLI)
     │
     ▼  MCP over HTTP :8000
┌─────────────────────────────────────────────┐
│  FastMCP server  (sofa_mcp/server.py)       │
│                                             │
│  architect/    scene authoring + validation │
│  observer/     stepping, rendering, extract │
│  optimizer/    AST-based scene patching     │
│  plugin cache  component → plugin lookup    │
└─────────────────────────────────────────────┘
     │
     ▼  subprocess / in-process
SOFA runtime  +  meshes/  +  generated scenes
```

Two execution boundaries to know about:

- **`scene_writer.py` and `mesh_generator.py`** spawn `~/venv/bin/python` subprocesses to run SOFA / gmsh — isolation by design.
- **`stepping.py` and `renderer.py`** load scenes in-process via `importlib`. Faster, but state can leak across calls.
