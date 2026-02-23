---
name: sofa-mcp
description: Integrates the SOFA Sim2Real MCP server tools for mesh inspection, math script execution, and SOFA component querying. Use this skill when analyzing SOFA simulation elements, performing calculations, or inspecting mesh properties.
---

# SOFA Sim2Real MCP Server Skill

This skill starts and interacts with the SOFA Sim2Real MCP server.

**IMPORTANT:** You must start the server using `start_sofa_mcp_server` before using any other tools.

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

### 4. `run_math_script`

*   **Description:** Executes a given Python script in a sandboxed environment and returns the output.
*   **Parameters:**
    *   `script` (string, required): A string containing the Python code to execute.
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"run_math_script","arguments":{"script":"<script>"}}}'
    ```

### 5. `query_sofa_component`

*   **Description:** Queries the SOFA framework's component registry for details about a specific component.
*   **Parameters:**
    *   `component_name` (string, required): The class name of the SOFA component to query.
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"query_sofa_component","arguments":{"component_name":"<component_name>"}}}'
    ```
### 6. `write_and_test_scene`
*   **Description:** Drafts a SOFA scene from a provided Python script, dry-runs it, and reports any errors or issues found during the process.
*   **Parameters:**
    *   `script_content` (string, required): A string containing the Python code that defines the SOFA scene.
    *   `output_filename` (string, required): The desired filename for the output SOFA scene file.
*   **Usage:**
    ```bash
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"write_and_test_scene","arguments":{"script_content":"<script_content>","output_filename":"<output_filename>"}}}'
    ```