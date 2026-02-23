
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastmcp import FastMCP
import sofa_mcp.architect.mesh_inspector as mesh_inspector
import sofa_mcp.architect.math_sandbox as math_sandbox
import sofa_mcp.architect.component_query as component_query
import sofa_mcp.architect.scene_writer as scene_writer

# Create the MCP server instance
mcp = FastMCP("SOFA Sim2Real MCP")


@mcp.tool()
def write_and_test_scene(script_content: str, output_filename: str) -> dict:
    """
    Drafts, dry-runs, and auto-corrects a SOFA scene.
    It returns success if the scene initializes and animates one step (dt=0.01).
    """
    return scene_writer.write_and_test_scene(script_content, output_filename)


@mcp.tool()
def get_mesh_bounding_box(mesh_path: str) -> dict:
    """Reads a mesh file and returns its bounding box."""
    return mesh_inspector.get_mesh_bounding_box(mesh_path)


@mcp.tool()
def inspect_mesh_topology(mesh_path: str) -> str:
    """Reads a mesh file and determines if it is a volumetric or surface mesh."""
    return mesh_inspector.inspect_mesh_topology(mesh_path)


@mcp.tool()
def run_math_script(script: str) -> str:
    """Runs a Python script in a sandboxed environment."""
    return math_sandbox.run_math_script(script)


@mcp.tool()
def query_sofa_component(component_name: str) -> dict:
    """Queries the SOFA component registry for a component."""
    return component_query.query_sofa_component(component_name)


if __name__ == "__main__":
    print("Starting SOFA Sim2Real MCP server...")
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8000,
        path="/mcp",
        stateless_http=True,
        json_response=True,
    )
