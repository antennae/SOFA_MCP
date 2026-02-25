---
name: sofa-mcp
description: Integrates the SOFA Sim2Real MCP server tools for mesh inspection, math script execution, SOFA component querying, and scene generation/validation. Use this skill when turning a natural-language scene request into a runnable SOFA scene, or when analyzing SOFA simulation elements, performing calculations, or inspecting mesh properties.
---

# SOFA Sim2Real MCP Server Skill

This skill starts and interacts with the SOFA Sim2Real MCP server.

**IMPORTANT:** You must start the server using `start_sofa_mcp_server` before using any other tools.

## Recommended Agent Workflow (Natural language → validated scene)

When the user says “I want a scene that …”, follow this loop:

1. **Start server (once):** call `start_sofa_mcp_server` if not already running.
2. **Clarify only what’s necessary:** if the request is underspecified, ask for the minimum missing details.
3. **Component Research & Dependencies:**
    - Use `query_sofa_component` for **every** new component you plan to use.
    - Check the returned `links` and `hints`. If it says it requires an `mstate`, ensure you add a `MechanicalObject` in the same node or a parent.
    - If `query_sofa_component` reports it had to load a plugin, note that plugin name for your `RequiredPlugin` list.
4. **Generate `script_content` (Safety for LLM):**
    - **Avoid multi-line JSON escaping issues:** When calling tools with `script_content`, use simple Python strings. If using a model like 2.5 Flash, keep the script concise.
    - Always define `add_scene_content(parent_node)`.
    - Group your `RequiredPlugin` calls at the top of `add_scene_content`.
5. **Validate & Summarize:**
    - Call `summarize_scene(script_content)` to check the hierarchy **before** full validation.
    - Pay attention to `health_warnings` in the summary (e.g., missing MOs or Solvers).
    - Call `validate_scene(script_content)` for a full dry-run.
6. **Auto-repair on failure:** use error messages and `health_warnings` to patch and retry (bounded attempts, e.g. up to 3).
7. **Write final file:** once validation succeeds, call `write_scene(script_content, output_filename)`.
8. **Stop condition:** on success, report the returned output `path` and any warnings.

## Available Tools

### 1. `start_sofa_mcp_server`

*   **Description:** Starts the SOFA MCP server in the background. This must be run once per session before using other tools.
*   **Usage:**
    ```bash
    ~/venv/bin/python -c "from sofa_mcp.server import mcp; mcp.run(transport='streamable-http', host='127.0.0.1', port=8000, path='/mcp', stateless_http=True, json_response=True)"
    ```

### 2. `get_mesh_bounding_box`

*   **Description:** Reads a mesh file and returns its minimum and maximum bounding box coordinates.
*   **Parameters:**
    *   `mesh_path` (string, required): The file path to the mesh.
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_mesh_bounding_box","arguments":{"mesh_path":"<mesh_path>"}}}'
    ```

### 3. `inspect_mesh_topology`

*   **Description:** Reads a mesh file and determines if it is a volumetric mesh or a surface mesh.
*   **Parameters:**
    *   `mesh_path` (string, required): The file path to the mesh.
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"inspect_mesh_topology","arguments":{"mesh_path":"<mesh_path>"}}}'
    ```

### 4. `resolve_asset_path`

*   **Description:** Expands `~`, resolves a filesystem path to an absolute path, and checks whether it exists.
*   **Parameters:**
        *   `path` (string, required): Asset path (relative or absolute).
*   **Returns (shape):** `{ "input": string, "path": string, "exists": boolean, "is_file": boolean, "size_bytes"?: number, "error"?: string }`
*   **Usage:**
        ```bash
        curl -X POST http://127.0.0.1:8000/mcp \
            -H "Content-Type: application/json" \
            -H "Accept: application/json, text/event-stream" \
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
            -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"mesh_stats","arguments":{"mesh_path":"<mesh_path>"}}}'
        ```

### 6. `run_math_script`

*   **Description:** Executes a given Python script in a sandboxed environment and returns the output.
*   **Parameters:**
    *   `script` (string, required): A string containing the Python code to execute.
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"run_math_script","arguments":{"script":"<script>"}}}'
    ```

### 7. `query_sofa_component`

*   **Description:** Queries the SOFA framework's component registry for details about a specific component. **Now with best-effort repair logic:** it automatically attempts to load missing plugins and satisfy context requirements (like a MechanicalObject) to allow metadata inspection.
*   **Parameters:**
    *   `component_name` (string, required): The class name of the SOFA component to query.
*   **Returns (shape):** Includes `data_fields`, `links` (dependency info), and `hints` if instantiation was difficult.
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"query_sofa_component","arguments":{"component_name":"<component_name>"}}}'
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
      -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"search_sofa_components","arguments":{"query":"<query>","limit":50}}}'
    ```

### 9. `validate_scene`
*   **Description:** Validates a proposed SOFA scene snippet by embedding it into a baseline scene wrapper, initializing the scene, and animating one simulation step (`dt=0.01`).
*   **Parameters:**
    *   `script_content` (string, required): Python source code (as a plain string) that **must** define a function `add_scene_content(parent_node)`.
*   **Returns (shape):**
    *   On success: `{ "success": true, "message": string, "stdout": string }`
    *   On failure: `{ "success": false, "message": string, "error": string, "stdout": string }` (or timeout with `error: "Timeout"`)
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"validate_scene","arguments":{"script_content":"<script_content>"}}}'
    ```

### 10. `summarize_scene`
*   **Description:** Builds the scene graph (without running a simulation step) and returns a structured summary of nodes/objects plus **health checks** (hierarchy validation, missing solvers, broken links).
*   **Parameters:**
    *   `script_content` (string, required): Python source code (as a plain string) that **must** define a function `add_scene_content(parent_node)`.
*   **Returns (shape):**
    *   On success: `{ "success": true, "node_count": number, "object_count": number, "health_warnings": string[], "nodes": array, ... }`
    *   On failure: `{ "success": false, "message": string, "error": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"summarize_scene","arguments":{"script_content":"<script_content>"}}}'
    ```

### 11. `write_scene`
*   **Description:** Writes the generated SOFA scene file to disk **without** running validation. Prefer calling `validate_scene` first.
*   **Parameters:**
    *   `script_content` (string, required): Python source code (as a plain string) that **must** define a function `add_scene_content(parent_node)`.
    *   `output_filename` (string, required): Filesystem path (relative or absolute) to write the SOFA scene Python file to (typically ends with `.py`). The parent directory will be created if needed, and the file is overwritten if it already exists.
*   **Returns (shape):**
    *   On success: `{ "success": true, "message": string, "path": string }`
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"write_scene","arguments":{"script_content":"<script_content>","output_filename":"<output_filename>"}}}'
    ```

### 12. `write_and_test_scene`
*   **Description:** Drafts a SOFA scene from a provided Python script, dry-runs it, and reports any errors or issues found during the process.
*   **Parameters:**
    *   `script_content` (string, required): Python source code (as a plain string) that **must** define a function `add_scene_content(parent_node)` which adds objects/nodes under the provided SOFA node. This content is embedded into a generated scene wrapper that provides `createScene(rootNode)` and baseline solver/animation-loop utilities; validation attempts to initialize the scene and animate one simulation step (`dt=0.01`).
    *   `output_filename` (string, required): Filesystem path (relative or absolute) to write the validated SOFA scene Python file to (typically ends with `.py`). The parent directory will be created if needed, and the file is overwritten if it already exists. The file is only written when validation succeeds.
*   **Returns (shape):**
    *   On success: `{ "success": true, "message": string, "path": string, "stdout": string }`
    *   On failure: `{ "success": false, "message": string, "error": string }` (or timeout with `error: "Timeout"`)
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":11,"method":"tools/call","params":{"name":"write_and_test_scene","arguments":{"script_content":"<script_content>","output_filename":"<output_filename>"}}}'
    ```

### 13. `load_scene`

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
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":12,"method":"tools/call","params":{"name":"load_scene","arguments":{"scene_path":"<scene_path>"}}}'
    ```

### 14. `patch_scene`

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
      -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":13,"method":"tools/call","params":{"name":"patch_scene","arguments":{"scene_path":"<scene_path>","patch":{"op":"insert_after","anchor":"def createScene(rootNode):","text":"\n    # patched\n"}}}}'
          ```
      
### 15. `run_and_extract`

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
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":15,"method":"tools/call","params":{"name":"run_and_extract","arguments":{"scene_path":"cantilever_beam.py","steps":5,"dt":0.01,"node_path":"/solver_node/mo","field":"position"}}}'
    ```

### 16. `process_simulation_data`

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
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":16,"method":"tools/call","params":{"name":"process_simulation_data","arguments":{"file_path":".sofa_mcp_results/sim_data_20260225_120000.json","indices":[0, 42],"calculate_metrics":true}}}'
    ```

### 17. `update_data_field`

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
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":16,"method":"tools/call","params":{"name":"update_data_field","arguments":{"scene_path":"scene.py","object_name":"mo","field_name":"totalMass","new_value":5.0}}}'
    ```

### 18. `find_indices_by_region`

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
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":18,"method":"tools/call","params":{"name":"find_indices_by_region","arguments":{"file_path":"prostate.stl","axis":"z","mode":"max"}}}'
    ```
