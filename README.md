# SOFA Sim2Real MCP Server

A Model Context Protocol (MCP) server for the **SOFA (Simulation Open Framework Architecture)** environment. This server enables LLMs and other AI agents to interact directly with SOFA simulations, facilitating autonomous scene generation and mesh analysis.

## 🎯 Overview

The SOFA MCP bridges the gap between natural language requests and runnable, validated SOFA simulations. It provides a robust toolset for:

- **Architecting Scenes:** Automated generation and validation of SOFA Python scenes.
- **Mesh Analysis:** Deep inspection of geometric assets (topology, bounding boxes, statistics).
- **Component Discovery:** Intelligent searching and querying of the SOFA component registry.
- **Simulation Control:** Stepping through simulations and extracting real-time field data.
- **Live Patching:** Safely updating simulation parameters in existing scene files.

## 🛠 Tech Stack

- **Simulation:** [SOFA Framework](https://www.sofa-framework.org/) with `SofaPython3`.
- **Server:** [FastMCP](https://github.com/jlowin/fastmcp) for Model Context Protocol.
- **Geometry:** `trimesh` for advanced mesh processing.
- **Language:** Python 3.10+.

## 🚀 Key Features

### 🏛 Scene Architect

- **Auto-Validation:** Validates generated scene snippets by initializing and animating them for a single step.
- **Scene Summary:** Provides a structured overview of the scene graph and component hierarchy.
- **Dry-run Execution:** Writes and tests scenes, reporting errors back to the agent for iterative refinement.

### 🔍 Mesh & Component Tools

- **Mesh Inspector:** Identifies surface vs. volumetric topology and provides bounding box data.
- **Registry Search:** Fuzzy-search for SOFA components and query their parameters.
- **Asset Resolver:** Resolves relative paths and validates asset existence.

### 🧪 Observer & Optimizer

- **Data Extraction:** Runs simulations for $N$ steps and extracts specific data fields (e.g., node positions).
- **Scene Patcher:** Applies structured text patches or direct field updates to existing simulation files.

## 📖 Recommended Agent Workflow

1. **Start Server:** Launch the MCP server.
2. **Mesh Preflight:** If a mesh is involved, use `mesh_stats` to determine scaling and topology.
3. **Draft Scene:** Generate Python code defining `add_scene_content(parent_node)`.
4. **Validate:** Use `validate_scene` to ensure the script is runnable.
5. **Iterate:** Auto-repair the script based on validation errors.
6. **Finalize:** Write the validated file using `write_scene`.

## ⚙️ Setup & Usage

### Prerequisites

- Python 3.10+
- SOFA Framework with `SofaPython3` plugin installed and in your `PYTHONPATH`.

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd SOFA_MCP
```

#### dependencies

- SOFA
- SofaPython3
- Trimesh
- Fastmcp

### Running the Server

```bash
python sofa_mcp/server.py
```

or

```bash
python -c "from sofa_mcp.server import mcp; mcp.run(transport='streamable-http', host='127.0.0.1', port=8000, path='/mcp', stateless_http=True, json_response=True)"
```

The server defaults to `http://127.0.0.1:8000/mcp`.

For gemini CLI, follow the [Skill Management Guide](./skill_management.md) to package and install the `sofa-mcp` skill.

## 📜 Framework Guidelines

- **Units:** Standardize on `[mm, g, s]` for consistency.
- **Template:** Used a templated SOFA scene with `FreeMotionAnimationLoop`, `NNCGConstraintSolver`, `EulerImplicitSolver`, `SparseLDLSolver`, and `GenericConstraintCorrection`.

## 📝 Examples

- `skill_test_prompts.txt` contains a list of prompts
