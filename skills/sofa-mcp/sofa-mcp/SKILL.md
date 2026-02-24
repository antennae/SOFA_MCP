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
2. **Clarify only what’s necessary:** if the request is underspecified, ask for the minimum missing details (e.g., geometry source/mesh path, expected material behavior, boundary conditions, what needs to be visualized/controlled).
3. **Preflight assets/components (when relevant):**
    - If the scene references a mesh, call `resolve_asset_path` (if needed) and `mesh_stats` to get bounding box + topology + basic counts for scaling/collision choices.
    - If you are unsure about a SOFA class name, call `search_sofa_components` to find candidates, then `query_sofa_component` to confirm parameters before writing code.
4. **Generate `script_content`:** produce Python code that defines `add_scene_content(parent_node)` only (no `createScene`), and add SOFA objects under `parent_node`.
5. **Validate (fast loop):** call `validate_scene(script_content)`.
6. **Auto-repair on failure:** if validation fails, use the returned error message to patch `script_content` and retry (bounded attempts, e.g. up to 3). Prefer minimal, targeted edits.
7. **Summarize + verify structure (recommended):** call `summarize_scene(script_content)` and ensure basic checks pass (e.g., a `MechanicalObject` exists, user objects were added).
8. **Write final file:** once validation succeeds, call `write_scene(script_content, output_filename)`.
9. **Stop condition:** on success, report the returned output `path` and any warnings.

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

*   **Description:** Queries the SOFA framework's component registry for details about a specific component.
*   **Parameters:**
    *   `component_name` (string, required): The class name of the SOFA component to query.
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
*   **Description:** Builds the scene graph (without running a simulation step) and returns a structured summary of nodes/objects plus basic verification checks.
*   **Parameters:**
    *   `script_content` (string, required): Python source code (as a plain string) that **must** define a function `add_scene_content(parent_node)`.
*   **Returns (shape):**
    *   On success: `{ "success": true, "node_count": number, "object_count": number, "class_counts": object, "checks": array, "nodes": array, ... }`
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