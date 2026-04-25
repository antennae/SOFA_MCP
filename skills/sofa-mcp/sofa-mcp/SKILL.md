---
name: sofa-mcp
description: Integrates the SOFA MCP server tools for mesh inspection, math script execution, SOFA component querying, and scene generation/validation. Use this skill when turning a natural-language scene request into a runnable SOFA scene, or when analyzing SOFA simulation elements, performing calculations, or inspecting mesh properties.
---

# SOFA MCP Server Skill

This skill starts and interacts with the SOFA MCP server.

**IMPORTANT:** You must start the server using `start_sofa_mcp_server` before using any other tools.

## Recommanded Agent Workflow (Natural language → validated scene)

When the user says “I want a SOFA scene that …”, you should follow this loop:

1. **Start server (once):** call `start_sofa_mcp_server` if not already running.
2. **Clarify only what’s necessary:** if the request is underspecified, ask for the minimum missing details.
3. **Component Research & Dependencies:**
    - **Step 1: Discover Plugins (Batch Operation):**
        - First, you MUST collect all the component class names you plan to use in the scene.
        - You MUST call `get_plugins_for_components` with the list of names to find the required plugins.
        - You MUST NOT guess or assume any plugin names. For every component you add to the scene, you MUST have first found its plugin using `get_plugins_for_components`.
    - **Step 2: Inspect Component Details (As Needed):**
        - If you need to know the specific `data_fields`, `links`, or default values for a single component, use `query_sofa_component`.
    - **Step 3: Check Dependencies:**
        - When inspecting a component with `query_sofa_component`, check the returned `links` and `hints`. If it says it requires an `mstate`, ensure you add a `MechanicalObject` in the same node or a parent.

4. **Generate `script_content` (Architectural Design):**
    - You MUST define the full `createScene(root_node)` function.
    - You are responsible for adding all necessary components: plugins, solvers, animation loops, and the actual simulation objects.
    - Group your `RequiredPlugin` calls at the top of `createScene` or at the global level.
    - Ensure your scene follows the **Scene Health Rules** below for physical and visual correctness.

5. **Summarize & Reason:**
    - Call `summarize_scene(script_content)` to retrieve the structured scene graph.
    - **Perform Agent-Side Validation:** Analyze the `nodes`, `objects`, and the `checks` list in the summary.
    - Check if essential classes (AnimationLoop, ODESolver, etc.) are present in the hierarchy.
    - Check if the scene graph follows the **Scene Health Rules**, if not, identify what’s missing and fix it in your `script_content`.

6. **Validate & Auto-repair:**
    - Call `validate_scene(script_content)` for a full dry-run (this initializes the scene and steps it).
    - If validation fails, use the traceback/error AND your scene graph summary to fix the script.

7. **Write final file:** once validation succeeds, call `write_scene(script_content, output_filename)`.

## Scene Health Rules (The Architect's Checklist)

Every valid SOFA scene must satisfy these structural requirements:

1.  **Plugins:** Include all `RequiredPlugin` objects for the components used (e.g., `Sofa.Component.ODESolver.Backward` for `EulerImplicitSolver`).
2.  **Animation Loop:** The root node (or an ancestor) must have an animation loop (e.g., `FreeMotionAnimationLoop` or `DefaultAnimationLoop`).
3.  **Visual Style:** Include a `VisualStyle` object with `displayFlags="showBehavior"` to ensure the simulation is visible in a GUI.
4.  **Integration Solver:** Every `MechanicalObject` must have a Time Integration Solver (e.g., `EulerImplicitSolver`) in its ancestry.
5. **Linear Solver:** If using an implicit solver, you MUST include a linear solver. 
   - **Recommended:** `SparseLDLSolver` (template="CompressedRowSparseMatrixMat3x3d" for FEM) for stability in soft-tissue simulation.
   - Avoid `CGLinearSolver` unless dealing with extremely large meshes (>100k nodes).
6. **Constraint Handling:** If using `FreeMotionAnimationLoop`, you MUST include:
   - **ConstraintSolver:** `NNCGConstraintSolver` (or `QPInverseProblemSolver` if SoftRobots.Inverse is used).
   - **Correction:** `GenericConstraintCorrection` on the mechanical nodes.
7.  **ForceField Mapping:** Every `ForceField` (like `TetrahedronFEMForceField`) must be in a node that contains a `MechanicalObject`.
8.  **Topology:** Volumetric force fields require a corresponding Topology Container (e.g., `TetrahedronSetTopologyContainer`).
9.  **Visual Model:** For high-quality rendering, map the mechanical state to a visual state using a `VisualModel` or `OglModel` and a `Mapping`.

## Available Tools

### 1. `start_sofa_mcp_server` (Self-Instruction)

*   **Description:** Starts the SOFA MCP server in the background. 
    **CRITICAL:** This must be run once per session using `run_shell_command` with `is_background: true`.
                  It must be waiting for the server to be fully ready before any other tools are called, otherwise you will get connection errors.
*   **Usage:**
    ```python
    # Use run_shell_command with is_background=True
    command = "~/venv/bin/python sofa_mcp/server.py"
    ```
*   **Mandatory Header:** Every `curl` request to the server **MUST** include `-H "Accept: application/json"`. Failure to do so will result in a `406 Not Acceptable` error.

### 2. `resolve_asset_path`

*   **Description:** Expands `~`, resolves a filesystem path to an absolute path, and checks whether it exists.
*   **Parameters:**
        *   `path` (string, required): Asset path (relative or absolute).
*   **Returns (shape):** `{ "input": string, "path": string, "exists": boolean, "is_file": boolean, "size_bytes"?: number, "error"?: string }`
*   **Usage:**
        ```bash
        curl -X POST http://127.0.0.1:8000/mcp \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"resolve_asset_path","arguments":{"path":"<path>"}}}'
        ```

### 5. `mesh_stats`

*   **Description:** Returns mesh statistics useful for scene generation: bounding box, topology classification, and basic counts (vertices/faces for surface meshes; points/cells for simple ASCII VTK meshes).
*   **Parameters:**
        *   `mesh_path` (string, required): The file path to the mesh.
*   **Returns (shape):** On success includes `{ "path": string, "bounding_box": {min,max}, "topology_kind": "surface"|"volumetric"|"unknown", ... }`; on failure `{ "error": string, ... }`.
*   **Usage:**
        ```bash
        curl -X POST http://127.0.0.1:8000/mcp \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"mesh_stats","arguments":{"mesh_path":"<mesh_path>"}}}'
        ```

### 5. `query_sofa_component`

*   **Description:** Queries the SOFA framework's component registry for details about a specific component. This tool includes robust, multi-stage repair logic: it automatically attempts to load missing plugins and can accept a user-defined context to satisfy complex dependency requirements.
*   **Parameters:**
    *   `component_name` (string, required): The class name of the SOFA component to query.
    *   `template` (string, optional): A template to apply to the component (e.g., 'Vec3d', 'Rigid3d').
    *   `context_components` (list of objects, optional): A list of components to create before the target component. Each object should be a dictionary with a `type` key and other keys for component attributes (e.g., `[{"type": "MechanicalObject", "name": "mo", "template": "Rigid3d"}]`). Use this to resolve dependency errors reported in previous `hints`.
*   **Returns (shape):** Includes `data_fields`, `links` (dependency info), and `hints` if instantiation was difficult.
*   **Usage:**
    ```bash
    # Simple query
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"query_sofa_component","arguments":{"component_name":"EulerImplicitSolver"}}}'
    
    # Advanced query for a component requiring a specific context
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"query_sofa_component","arguments":{"component_name":"SomeComplexComponent","template":"Rigid3d","context_components":[{"type":"MyCustomTopology","name":"topo"}]}}}'
    ```

### 8. `search_sofa_components`

*   **Description:** Searches SOFA's registered component class names using a fuzzy query.
*   **Parameters:**
    *   `query` (string, required): Case-insensitive search string. If it ends with `*`, performs a prefix match (e.g., `Tetra*`). Otherwise performs a substring match.
    *   `limit` (number, optional): Maximum number of matches to return (default: 50).
*   **Returns (shape):**
    *   On success: `{ "query": string, "limit": number, "count": number, "matches": string[] }`
    *   On failure: `{ "error": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"search_sofa_components","arguments":{"query":"<query>","limit":50}}}'
    ```

### 9. `get_plugins_for_components`

*   **Description:** For a list of SOFA component names, returns a mapping to their required plugins. This is highly efficient for batch-checking all components for a new scene. It can also accept a custom context for components with special dependencies.
*   **Parameters:**
    *   `component_names` (list of strings, required): The class names of the SOFA components to query.
    *   `context_components` (list of objects, optional): A list of components to create before checking the components in `component_names`. Use this if any of your components require a non-default context to be instantiated.
*   **Returns (shape):** A dictionary mapping component names to plugin names (e.g., `{"CGLinearSolver": "Sofa.Component.LinearSolver.Iterative", "MechanicalObject": "Already Loaded"}`).
*   **Usage:**
    ```bash
    # Simple batch query
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d '{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"get_plugins_for_components","arguments":{"component_names":["EulerImplicitSolver","CGLinearSolver"]}}}'

    # Advanced query with context
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d '{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"get_plugins_for_components","arguments":{"component_names":["AnisotropicForceField"],"context_components":[{"type":"MechanicalObject","template":"Vec2d"}]}}}'
    ```

### 10. `validate_scene`
*   **Description:** Validates a proposed SOFA scene snippet by embedding it into a baseline scene wrapper, initializing the scene, and animating one simulation step (`dt=0.01`).
*   **Parameters:**
    *   `script_content` (string, required): Python source code (as a plain string) that **must** define a function `createScene(rootNode)`.
*   **Returns (shape):**
    *   On success: `{ "success": true, "message": string, "stdout": string }`
    *   On failure: `{ "success": false, "message": string, "error": string, "stdout": string }` (or timeout with `error: "Timeout"`)
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
            -d '{"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"validate_scene","arguments":{"script_content":"<script_content>"}}}'
    ```

### 11. `summarize_scene`
*   **Description:** Builds the scene graph (without running a simulation step) and returns a structured JSON summary of nodes and objects. **Use this for agent-side structural reasoning.**
*   **Parameters:**
    *   `script_content` (string, required): Python source code (as a plain string) that **must** define a function `createScene(rootNode)`.
*   **Returns (shape):**
    *   On success: `{ "success": true, "node_count": number, "object_count": number, "class_counts": object, "checks": array, "nodes": array }`
    *   On failure: `{ "success": false, "message": string, "error": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
            -d '{"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"summarize_scene","arguments":{"script_content":"<script_content>"}}}'
    ```

### 12. `write_scene`
*   **Description:** Writes the generated SOFA scene file to disk **without** running validation. Prefer calling `validate_scene` first.
*   **Parameters:**
    *   `script_content` (string, required): Python source code (as a plain string) that **must** define a function `createScene(rootNode)`.
    *   `output_filename` (string, required): Filesystem path (relative or absolute) to write the SOFA scene Python file to (typically ends with `.py`). The parent directory will be created if needed, and the file is overwritten if it already exists.
*   **Returns (shape):**
    *   On success: `{ "success": true, "message": string, "path": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
            -d '{"jsonrpc":"2.0","id":12,"method":"tools/call","params":{"name":"write_scene","arguments":{"script_content":"<script_content>","output_filename":"<output_filename>"}}}'
    ```

### 13. `write_and_test_scene`
*   **Description:** Drafts a SOFA scene from a provided Python script, dry-runs it, and reports any errors or issues found during the process.
*   **Parameters:**
    *   `script_content` (string, required): Python source code (as a plain string) that **must** define a function `createScene(rootNode)`. Validation attempts to initialize the scene and animate one simulation step (`dt=0.01`).
    *   `output_filename` (string, required): Filesystem path (relative or absolute) to write the validated SOFA scene Python file to (typically ends with `.py`). The parent directory will be created if needed, and the file is overwritten if it already exists. The file is only written when validation succeeds.
*   **Returns (shape):**
    *   On success: `{ "success": true, "message": string, "path": string, "stdout": string }`
    *   On failure: `{ "success": false, "message": string, "error": string }` (or timeout with `error: "Timeout"`)
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
            -d '{"jsonrpc":"2.0","id":13,"method":"tools/call","params":{"name":"write_and_test_scene","arguments":{"script_content":"<script_content>","output_filename":"<output_filename>"}}}'
    ```

### 14. `load_scene`

*   **Description:** Loads an existing SOFA scene Python file from disk and returns its contents.
*   **Parameters:**
    *   `scene_path` (string, required): Path to an existing `.py` file.
*   **Returns (shape):**
    *   On success: `{ "success": true, "message": string, "path": string, "size_bytes": number, "content": string }`
    *   On failure: `{ "success": false, "message": string, "error": string, "path": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d '{"jsonrpc":"2.0","id":14,"method":"tools/call","params":{"name":"load_scene","arguments":{"scene_path":"<scene_path>"}}}'
    ```

### 15. `patch_scene`

*   **Description:** Applies a small structured text patch to an existing scene file. This enables workflows like “modify my existing scene to add …” instead of regenerating from scratch.
*   **Parameters:**
    *   `scene_path` (string, required): Path to an existing `.py` file.
    *   `patch` (object, required): One patch operation.
        *   Replace: `{ "op": "replace", "old": "<old>", "new": "<new>", "count"?: 1 }`
        *   Insert: `{ "op": "insert_before"|"insert_after", "anchor": "<anchor>", "text": "<text>", "occurrence"?: 1 }`
        *   Append/Prepend: `{ "op": "append"|"prepend", "text": "<text>" }`
*   **Returns (shape):**
    *   On success: `{ "success": true, "message": string, "path": string, "applied_ops": number, "size_bytes": number }`
    *   On failure: `{ "success": false, "message": string, "error": string, "path": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
            -d '{"jsonrpc":"2.0","id":15,"method":"tools/call","params":{"name":"patch_scene","arguments":{"scene_path":"<scene_path>","patch":{"op":"insert_after","anchor":"def createScene(rootNode):","text":"\n    # patched\n"}}}}'
          ```
      
### 16. `run_and_extract`

*   **Description:** Runs a SOFA simulation for a specified number of steps and extracts data from a specific component field at each step. **Results are saved to a JSON file to prevent large response payloads.** Returns only a metadata summary and shape.
*   **Parameters:**
    *   `scene_path` (string, required): Path to the SOFA scene Python file.
    *   `steps` (integer, required): Number of simulation steps to run.
    *   `dt` (number, required): Time step for the simulation.
    *   `node_path` (string, required): Path to the node/component (e.g., `/solver_node/mo`).
    *   `field` (string, required): The field to extract data from (e.g., `position`).
*   **Returns (shape):**
    *   On success: `{ "success": true, "output_file": string, "steps": number, "data_shape": number[], "data_preview": array, "message": string }`
    *   On failure: `{ "success": false, "error": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","id":16,"method":"tools/call","params":{"name":"run_and_extract","arguments":{"scene_path":"cantilever_beam.py","steps":5,"dt":0.01,"node_path":"/solver_node/mo","field":"position"}}}'
    ```

### 20. `run_and_extract_multi`

*   **Description:** Runs a SOFA simulation and extracts data from **multiple fields/nodes in a single run**. Use this instead of calling `run_and_extract` repeatedly when you need several fields (e.g., position + velocity, or data from multiple nodes). All fields are resolved before the simulation starts — if any path is wrong, the tool fails immediately before wasting simulation time.
*   **Parameters:**
    *   `scene_path` (string, required): Path to the SOFA scene Python file.
    *   `steps` (integer, required): Number of simulation steps to run.
    *   `dt` (number, required): Time step for the simulation.
    *   `fields` (array of objects, required): List of field descriptors. Each object must have:
        *   `node_path` (string): Path to the node/object in the scene graph (e.g., `mechanics/mo`).
        *   `field` (string): Data field name to extract (e.g., `position`).
        *   `key` (string, optional): Alias for this field in the output. Defaults to `<node_path>/<field>`.
*   **Returns (shape):**
    *   On success: `{ "success": true, "output_file": string, "steps": number, "fields": { "<key>": { "data_shape": number[], "data_preview": array } }, "message": string }`
    *   On failure: `{ "success": false, "error": string }`
*   **Output JSON format** (saved to `.sofa_mcp_results/sim_data_multi_<timestamp>.json`):
    ```json
    {
      "metadata": { "scene_path": "...", "steps": 50, "dt": 0.01, "fields": [...] },
      "fields": {
        "pos":  [[step_0_data], [step_1_data], ...],
        "vel":  [[step_0_data], [step_1_data], ...]
      }
    }
    ```
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","id":20,"method":"tools/call","params":{"name":"run_and_extract_multi","arguments":{"scene_path":"cantilever_beam.py","steps":10,"dt":0.01,"fields":[{"node_path":"solver_node/mo","field":"position","key":"pos"},{"node_path":"solver_node/mo","field":"velocity","key":"vel"}]}}}'
    ```

### 17. `process_simulation_data`

*   **Description:** Processes a simulation data file (generated by `run_and_extract`) to extract a subset of results or calculate physical metrics (net displacement, stability/convergence). It automatically detects data dimensions (e.g., Vec3d vs. scalars) to provide physically meaningful metrics. Use `indices` to select specific vertices from a large mesh.
*   **Parameters:**
    *   `file_path` (string, required): Path to the JSON file containing simulation data.
    *   `start_step` (integer, optional): The first step to include (default: 0).
    *   `end_step` (integer, optional): The last step to include (exclusive). -1 means all steps (default: -1).
    *   `indices` (array of integers, optional): Specific indices (e.g., vertex IDs) to extract from the data array at each step.
    *   `calculate_metrics` (boolean, optional): Whether to calculate net displacement, stability (convergence), and peak magnitude (default: false).
    *   `include_data` (boolean, optional): Whether to include the full (filtered) time-series data array in the response (default: false).
*   **Returns (shape):**
    *   On success: `{ "success": true, "metadata": object, "total_steps": number, "subset_range": [start, end], "data_shape": number[], "data"?: array, "metrics": { "net_displacement_vector": any, "max_displacement_magnitude": number, "stability_measure": number, "is_converged": boolean, "peak_magnitude": number, "final_values": any } }`
    *   **Metric Details:** 
        *   For `Vec3d` data, `max_displacement_magnitude` and `stability_measure` use Euclidean distances (L2 norm). 
        *   `is_converged` is `True` if the stability measure is `< 1e-3`.
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"jsonrpc":"2.0","id":17,"method":"tools/call","params":{"name":"process_simulation_data","arguments":{"file_path":".sofa_mcp_results/sim_data_20260225_120000.json","indices":[0, 42],"calculate_metrics":true}}}'
    ```

### 18. `update_data_field`

*   **Description:** Updates a specific field of a SOFA object in a Python scene file. This tool parses the Python code to locate the object by name and safely updates or inserts the field value, preserving the rest of the file structure.
*   **Parameters:**
    *   `scene_path` (string, required): Path to the SOFA scene Python file.
    *   `object_name` (string, required): The `name` of the object to target (e.g., `mo`).
    *   `field_name` (string, required): The argument/field to update (e.g., `position`).
    *   `new_value` (any, required): The new value for the field (string, number, list, etc.).
*   **Returns (shape):**
    *   On success: `{ "success": true, "message": string }`
    *   On failure: `{ "success": false, "error": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d '{"jsonrpc":"2.0","id":18,"method":"tools/call","params":{"name":"update_data_field","arguments":{"scene_path":"scene.py","object_name":"mo","field_name":"totalMass","new_value":5.0}}}'
    ```

### 19. `find_indices_by_region`

*   **Description:** Finds vertex indices in a mesh (STL, VTK) or simulation JSON based on spatial criteria (min, max, or range) along a specific axis (x, y, or z). Useful for identifying tip vertices or fixed boundary indices.
*   **Parameters:**
    *   `file_path` (string, required): Path to the mesh or simulation JSON file.
    *   `axis` (string, required): 'x', 'y', or 'z'.
    *   `mode` (string, required): 'min', 'max', or 'range'.
    *   `value` (any, optional): Required for 'range' mode as `[min, max]`.
    *   `tolerance` (number, optional): Distance tolerance for matching (default: 1e-5).
*   **Returns (shape):**
    *   On success: `{ "success": true, "indices": number[], "count": number, "axis": string, "mode": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d '{"jsonrpc":"2.0","id":19,"method":"tools/call","params":{"name":"find_indices_by_region","arguments":{"file_path":"prostate.stl","axis":"z","mode":"max"}}}'
    ```
