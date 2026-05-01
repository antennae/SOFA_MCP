
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from typing import Any
from fastmcp import FastMCP
import sofa_mcp.architect.mesh_inspector as mesh_inspector
import sofa_mcp.architect.mesh_generator as mesh_generator
import sofa_mcp.architect.component_query as component_query
import sofa_mcp.architect.scene_writer as scene_writer
import sofa_mcp.observer.stepping as stepping
import sofa_mcp.observer.renderer as renderer
import sofa_mcp.observer.diagnostics as diagnostics
from sofa_mcp.observer import probes
import sofa_mcp.optimizer.patcher as patcher

# Create the MCP server instance
mcp = FastMCP("SOFA MCP")

@mcp.tool()
def health_check() -> dict:
    """Returns the server status and initialization state."""
    return {"status": "ready", "version": "1.0.0"}


@mcp.tool()
def update_data_field(scene_path: str, object_name: str, field_name: str, new_value) -> dict:
    """Updates a specific field of a SOFA object in a Python scene file."""
    return patcher.update_data_field(scene_path, object_name, field_name, new_value)


@mcp.tool()
def run_and_extract(scene_path: str, steps: int, dt: float, node_path: str, field: str) -> dict:
    """Runs a SOFA simulation and extracts data from a specified field at each step. Results are saved to a file."""
    return stepping.run_and_extract(scene_path, steps, dt, node_path, field)


@mcp.tool()
def render_scene_snapshot(
    scene_path: str,
    steps: int = 50,
    dt: float = 0.01,
    output_path: str = None,
    image_size: tuple = (1024, 768),
    background: str = "white",
    show_edges: bool = False,
) -> dict:
    """Runs a SOFA scene for N steps and renders the final state to a PNG via offscreen PyVista. Auto-discovers MechanicalObjects and uses sibling OglModel colors when available."""
    return renderer.render_scene_snapshot(
        scene_path=scene_path,
        steps=steps,
        dt=dt,
        output_path=output_path,
        image_size=image_size,
        background=background,
        show_edges=show_edges,
    )


@mcp.tool()
def process_simulation_data(
    file_path: str, 
    start_step: int = 0, 
    end_step: int = -1, 
    indices: list[int] = None, 
    calculate_metrics: bool = False,
    include_data: bool = False
) -> dict:
    """Processes a simulation data file to extract a subset of results or calculate metrics (displacement, stability)."""
    return stepping.process_simulation_data(file_path, start_step, end_step, indices, calculate_metrics, include_data)



@mcp.tool()
def find_indices_by_region(
    file_path: str,
    axis: str,
    mode: str,
    value: Any = None,
    tolerance: float = 1e-5
) -> dict:
    """Finds vertex indices based on spatial criteria (min, max, range) along an axis."""
    return mesh_inspector.find_indices_by_region(file_path, axis, mode, value, tolerance)


@mcp.tool()
def validate_scene(script_content: str, verbose: bool = False) -> dict:
    """Validates a SOFA scene snippet by initializing and animating one step (dt=0.01).

    `verbose=False` (default) compacts captured SOFA stdout to plugin loads,
    convergence, errors, and tracebacks. Set `verbose=True` for the full log.
    """
    return scene_writer.validate_scene(script_content, verbose=verbose)


@mcp.tool()
def summarize_scene(script_content: str, verbose: bool = False) -> dict:
    """Summarizes the scene graph (nodes/objects) and runs basic checks.

    `verbose=False` (default) compacts captured SOFA stderr/stdout on the
    failure path. Success path is unchanged (only the parsed summary is returned).
    """
    return scene_writer.summarize_scene(script_content, verbose=verbose)


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
def generate_volume_mesh(
    stl_path: str,
    output_path: str = None,
    mesh_size_factor: float = 1.0,
    remove_duplicates: bool = True,
) -> dict:
    """Converts a surface STL file into a volumetric VTK mesh using GMSH. Output is loadable by SOFA's MeshVTKLoader."""
    return mesh_generator.generate_volume_mesh(stl_path, output_path, mesh_size_factor, remove_duplicates)


@mcp.tool()
def resolve_asset_path(path: str) -> dict:
    """Resolves an asset path (~ expansion + absolute path) and checks existence."""
    return mesh_inspector.resolve_asset_path(path)


@mcp.tool()
def mesh_stats(mesh_path: str) -> dict:
    """Returns mesh statistics (bbox, topology, counts) useful for scene generation."""
    return mesh_inspector.mesh_stats(mesh_path)


@mcp.tool()
def query_sofa_component(component_name: str, template: str = None, context_components: list[dict] = None) -> dict:
    """Queries the SOFA component registry for a component."""
    return component_query.query_sofa_component(component_name, template=template, context_components=context_components)


@mcp.tool()
def search_sofa_components(query: str, limit: int = 50) -> dict:
    """Searches SOFA's registered components by a fuzzy query (substring/prefix)."""
    return component_query.search_sofa_components(query, limit=limit)


@mcp.tool()
def get_plugins_for_components(component_names: list[str], context_components: list[dict] = None) -> dict[str, str]:
    """
    For a list of SOFA component names, returns a mapping to their required plugins.
    """
    return component_query.get_plugins_for_components(component_names, context_components=context_components)


@mcp.tool()
def diagnose_scene(
    scene_path: str,
    complaint: str = None,
    steps: int = 50,
    dt: float = 0.01,
    verbose: bool = False,
) -> dict:
    """Runs a sanity report for a SOFA scene: structural anomalies (Health Rules) plus per-step metrics (max displacement, max force, NaN-first-step) on every unmapped MechanicalObject. `complaint` is accepted for forward-compat and currently unused.

    `verbose=False` (default) compacts `solver_logs` to plugin loads, convergence summaries, errors, warnings, and tracebacks. The response carries `log_lines_dropped: int` when filtering happened. Set `verbose=True` for the full captured log (still subject to head/tail char-budget truncation).
    """
    return diagnostics.diagnose_scene(scene_path, complaint=complaint, steps=steps, dt=dt, verbose=verbose)


@mcp.tool()
def enable_logs_and_run(
    scene_path: str,
    log_targets: list,
    steps: int = 5,
    dt: float = 0.01,
    verbose: bool = False,
) -> dict:
    """Toggle printLog=True on objects matching `log_targets` (class names or node-path fragments), animate for `steps` iterations, return the captured logs.

    Use this after `diagnose_scene` flags an anomaly to inspect what a specific solver, mapping, or constraint is doing at runtime. Logs are compacted by default; pass `verbose=True` for the full stream.
    """
    return probes.enable_logs_and_run(
        scene_path=scene_path,
        log_targets=log_targets,
        steps=steps,
        dt=dt,
        verbose=verbose,
    )


@mcp.tool()
def perturb_and_run(
    scene_path: str,
    parameter_changes: dict,
    steps: int = 50,
    dt: float = 0.01,
    verbose: bool = False,
) -> dict:
    """Apply Data-field overrides (e.g. `{"/root/leg/ff": {"youngModulus": 1000}}`) before init, animate, return per-MO metrics. Use to test a hypothesis: "is the deformation small because the material is too stiff?" → halve youngModulus, re-run, see if displacement scales as expected.

    Path can be an object path like `/root/beam/FEM` (single object) or a node path like `/root/beam` (fans out to every object on the node that exposes the field — prefer object paths when ambiguous).

    Logs are compacted by default; pass `verbose=True` for the full stream.
    """
    return probes.perturb_and_run(
        scene_path=scene_path,
        parameter_changes=parameter_changes,
        steps=steps,
        dt=dt,
        verbose=verbose,
    )


if __name__ == "__main__":
    from sofa_mcp.architect.plugin_cache import generate_and_save_plugin_map
    generate_and_save_plugin_map()
    port = int(os.environ.get("SOFA_MCP_PORT", "8000"))
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=port,
        path="/mcp",
        stateless_http=True,
        json_response=True,
    )
