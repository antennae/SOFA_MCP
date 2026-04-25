---
marp: true
theme: default
paginate: true
title: SOFA_MCP
description: MCP server bridging LLM agents with the SOFA simulation framework
---

<!-- _class: lead -->
# SOFA Simulation via Model Context Protocol (MCP)

Sizhe Tian

---
# What Is MCP?

- **Model Context Protocol (MCP)** — open standard by Anthropic for connecting LLMs to external tools and data sources.
- Defines a client/server protocol: LLM clients discover and call **tools** exposed by MCP servers.
- Servers can be local processes or remote HTTP services; clients include Claude Desktop, Gemini CLI, Cursor, etc.

---
# SOFA_MCP

- An **MCP server** that bridges LLM agents with the **SOFA simulation framework**.
- Exposes 19 tools covering scene authoring, mesh inspection, component discovery, and simulation control.
- Accepts natural language requests → produces validated, runnable SOFA `.py` scene files.

---
# Architecture

```
LLM Client
    |
    v
FastMCP Server  sofa_mcp/server.py  (HTTP :8000/mcp)
    |
    +-- architect/   scene writing, validation, component queries
    +-- observer/    simulation stepping, data extraction
    +-- optimizer/   AST-based scene patching
    |
    v
SOFA Runtime  +  meshes/  +  generated scene scripts
```

---
# MCP Tools — 19 Total

| Category | Tools |
|----------|-------|
| Scene management | `validate_scene`, `summarize_scene`, `write_scene`, `write_and_test_scene`, `load_scene`, `patch_scene` |
| Mesh / geometry | `mesh_stats`, `find_indices_by_region`, `resolve_asset_path`, `generate_volume_mesh` |
| Component discovery | `query_sofa_component`, `search_sofa_components`, `get_plugins_for_components` |
| Simulation | `run_and_extract`, `process_simulation_data`, `update_data_field`, `health_check` |

---
# Core Workflow

1. **Inspect** mesh → `mesh_stats`, `find_indices_by_region`
2. **Discover** components → `search_sofa_components`, `get_plugins_for_components`
3. **Draft** scene (Python `createScene(rootNode)` function)
4. **Validate & write** → `write_and_test_scene` (subprocess-isolated)
5. **Patch & run** → `update_data_field`, `run_and_extract`, `process_simulation_data`

---
# Scene Rules (enforced by `validate_scene`)

- All components must have their plugin declared.
- `FreeMotionAnimationLoop` requires a `ConstraintSolver`.
- Every `MechanicalObject` needs a time integration solver + linear solver.
- `ForceField` on a mapped node requires both `MechanicalObject` and `Mapping`.
- `VisualStyle` must be present at root.

---
# Plugin Cache

- Built once upon startup, stored at `.sofa_mcp_results/.sofa-component-plugin-map.json`.
- Maps every SOFA component class name → required plugin.
- Consulted by `search_sofa_components` and `get_plugins_for_components` without starting SOFA.

---
# Demo

- Tooling: **Gemini CLI** with `sofa-mcp` skill
- Prompt → agent calls MCP tools → validated, runnable SOFA scene


**Videos**


