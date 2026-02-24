
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
def validate_scene(script_content: str) -> dict:
    """Validates a SOFA scene snippet by initializing and animating one step (dt=0.01)."""
    return scene_writer.validate_scene(script_content)


@mcp.tool()
def summarize_scene(script_content: str) -> dict:
    """Summarizes the scene graph (nodes/objects) and runs basic checks."""
    return scene_writer.summarize_scene(script_content)


@mcp.tool()
def write_scene(script_content: str, output_filename: str) -> dict:
    """Writes a generated SOFA scene file to disk without running validation."""
    return scene_writer.write_scene(script_content, output_filename)


@mcp.tool()
def write_and_test_scene(script_content: str, output_filename: str) -> dict:
    """
    Drafts, dry-runs, and auto-corrects a SOFA scene.
    It returns success if the scene initializes and animates one step (dt=0.01).
    """
    return scene_writer.write_and_test_scene(script_content, output_filename)


@mcp.tool()
def load_scene(scene_path: str) -> dict:
    """Loads an existing scene file from disk and returns its contents."""
    return scene_writer.load_scene(scene_path)


@mcp.tool()
def patch_scene(scene_path: str, patch: dict) -> dict:
    """Applies a structured text patch to an existing scene file."""
    return scene_writer.patch_scene(scene_path, patch)


@mcp.tool()
def get_mesh_bounding_box(mesh_path: str) -> dict:
    """Reads a mesh file and returns its bounding box."""
    return mesh_inspector.get_mesh_bounding_box(mesh_path)


@mcp.tool()
def inspect_mesh_topology(mesh_path: str) -> str:
    """Reads a mesh file and determines if it is a volumetric or surface mesh."""
    return mesh_inspector.inspect_mesh_topology(mesh_path)


@mcp.tool()
def resolve_asset_path(path: str) -> dict:
    """Resolves an asset path (~ expansion + absolute path) and checks existence."""
    return mesh_inspector.resolve_asset_path(path)


@mcp.tool()
def mesh_stats(mesh_path: str) -> dict:
    """Returns mesh statistics (bbox, topology, counts) useful for scene generation."""
    return mesh_inspector.mesh_stats(mesh_path)


@mcp.tool()
def run_math_script(script: str) -> str:
    """Runs a Python script in a sandboxed environment."""
    return math_sandbox.run_math_script(script)


@mcp.tool()
def query_sofa_component(component_name: str) -> dict:
    """Queries the SOFA component registry for a component."""
    return component_query.query_sofa_component(component_name)


@mcp.tool()
def search_sofa_components(query: str, limit: int = 50) -> dict:
    """Searches SOFA's registered components by a fuzzy query (substring/prefix)."""
    return component_query.search_sofa_components(query, limit=limit)


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
