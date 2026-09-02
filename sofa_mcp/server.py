
import asyncio
import contextlib
import itertools
import os
import sys
import time
import traceback
import datetime as _dt
import pathlib as _pathlib

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from typing import Any
from fastmcp import FastMCP
from fastmcp.server.dependencies import Progress
from fastmcp.utilities.tasks import TaskConfig
from fastmcp_tasks import TasksExtension
import sofa_mcp.architect.mesh_inspector as mesh_inspector
import sofa_mcp.architect.mesh_generator as mesh_generator
import sofa_mcp.architect.component_query as component_query
import sofa_mcp.architect.scene_writer as scene_writer
import sofa_mcp.observer.stepping as stepping
import sofa_mcp.observer.renderer as renderer
import sofa_mcp.observer.diagnostics as diagnostics
from sofa_mcp.observer import probes
import sofa_mcp.optimizer.patcher as patcher

# Crash-log path. The pneunet session (2026-05-14 feedback #6) hit a silent
# stdio-transport drop with no diagnostic record — at minimum we want a place
# on disk that captures the traceback if it happens again.
_SERVER_LOG_PATH = os.path.expanduser("~/.sofa_mcp_results/server.log")
_SERVER_START_TIME = time.time()


def _log_server_event(level: str, message: str) -> None:
    """Append a timestamped line to the server log; swallow any I/O error.

    We never want logging itself to take down the server, so disk failures
    here are silent on purpose."""
    try:
        _pathlib.Path(_SERVER_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(_SERVER_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} [{level}] {message}\n")
    except Exception:
        pass


# Create the MCP server instance
mcp = FastMCP("SOFA MCP")

# MCP Tasks (spec 2026-07-28, extension io.modelcontextprotocol/tasks). The
# three scene-running tools are declared task-capable in "optional" mode: a
# client that opts in gets a task handle back immediately and polls for the
# result; a legacy client gets the old blocking call. Backend is the default
# in-process memory:// docket, which is all a single local server needs.
mcp.add_extension(TasksExtension())
_RUN_AS_TASK = TaskConfig(mode="optional")


_RUNS_IN_FLIGHT: dict[str, dict] = {}
_RUN_SEQ = itertools.count(1)


@contextlib.contextmanager
def _track_run(tool: str, **info):
    """Register a scene run in the in-flight table for the duration of the
    call, so `server_status` can answer "is that long run still going?".
    Tracked here rather than via the docket backend: pydocket 0.24.1's
    memory:// snapshot() raises KeyError('message_id') while a task is
    pending, and this table also covers the legacy blocking path."""
    run_id = f"{tool}-{next(_RUN_SEQ)}"
    _RUNS_IN_FLIGHT[run_id] = {
        "tool": tool,
        "started": _dt.datetime.now().isoformat(timespec="seconds"),
        **info,
    }
    try:
        yield run_id
    finally:
        _RUNS_IN_FLIGHT.pop(run_id, None)


def _runs_in_flight() -> dict:
    return {
        "count": len(_RUNS_IN_FLIGHT),
        "running": [{"id": k, **v} for k, v in _RUNS_IN_FLIGHT.items()],
    }


@mcp.tool()
async def server_status(log_tail: int = 20) -> dict:
    """Returns server uptime, plugin-cache freshness, recent log lines, and the in-flight scene-run table (`runs_in_flight`) for diagnose/probe calls still executing, whether submitted as MCP tasks or blocking calls.

    Use when a previous call returned a transport error and you want to
    confirm the server is responsive again — eliminates the "is it alive?"
    guessing the agent otherwise has to do — or to see whether a long run
    submitted as a task is still in flight.
    """
    from sofa_mcp.architect import plugin_cache
    cache_path = plugin_cache.get_cache_path()
    cache_info: dict[str, Any]
    if os.path.exists(cache_path):
        st = os.stat(cache_path)
        cache_info = {
            "path": cache_path,
            "exists": True,
            "size_bytes": st.st_size,
            "mtime": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        }
    else:
        cache_info = {"path": cache_path, "exists": False}

    log_lines: list[str] = []
    if os.path.exists(_SERVER_LOG_PATH):
        try:
            with open(_SERVER_LOG_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            log_lines = [ln.rstrip("\n") for ln in lines[-max(1, int(log_tail)):]]
        except Exception:
            pass

    return {
        "status": "ok",
        "version": "1.0.0",
        "uptime_seconds": int(time.time() - _SERVER_START_TIME),
        "log_path": _SERVER_LOG_PATH,
        "log_tail": log_lines,
        "plugin_cache": cache_info,
        "runs_in_flight": _runs_in_flight(),
    }


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
def write_and_test_scene(script_content: str, output_filename: str) -> dict:
    """
    Drafts, dry-runs, and auto-corrects a SOFA scene.
    It returns success if the scene initializes and animates one step (dt=0.01).
    """
    return scene_writer.write_and_test_scene(script_content, output_filename)


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
def mesh_stats(mesh_path: str) -> dict:
    """Returns mesh statistics (bbox, topology, counts) useful for scene generation."""
    return mesh_inspector.mesh_stats(mesh_path)


@mcp.tool()
def query_sofa_component(
    component_name: str,
    template: str = None,
    context_components: list[dict] = None,
    include_universal: bool = False,
) -> dict:
    """Queries the SOFA component registry for a component.

    Honors `template` (the introspection scaffold is built to match, so a
    `Rigid3d` request returns Rigid3d-shaped Data fields, not a silent Vec3d
    fallback). Returns `templates`, `plugin`, `description`, `source_header`, and
    an `introspection` field (`"full"` or `"metadata_only"`). When a registered
    class can't be instantiated in the scaffold, returns `success: true` with
    `introspection: "metadata_only"` and `data_fields: null` — not a misleading
    "not found" error. Set `include_universal=True` to keep the 6 universal
    BaseObject Data fields (name, printLog, tags, bbox, componentState, listening).
    """
    return component_query.query_sofa_component(
        component_name,
        template=template,
        context_components=context_components,
        include_universal=include_universal,
    )


@mcp.tool()
def search_sofa_components(query: str, limit: int = 50) -> dict:
    """Searches SOFA's registered components by a fuzzy query (substring/prefix)."""
    return component_query.search_sofa_components(query, limit=limit)


@mcp.tool()
def get_plugins_for_components(component_names: list[str], context_components: list[dict] = None) -> dict:
    """
    For a list of SOFA component names, returns a mapping to their required plugins.

    Each value is either:
      - a plugin-name string (component found in cache), or
      - a dict `{plugin: null, renamed: True, hint, suggested_replacements}`
        when the name is a retired class SOFA has since renamed
        (e.g. `GenericConstraintSolver` → `BlockGaussSeidel...`), or
      - the literal string `"Component not found in cache"` when truly unknown.
    """
    return component_query.get_plugins_for_components(component_names, context_components=context_components)


@mcp.tool(task=_RUN_AS_TASK)
async def diagnose_scene(
    scene_path: str,
    complaint: str = None,
    steps: int = 50,
    dt: float = 0.01,
    verbose: bool = False,
    env: dict = None,
    timeout_s: int = 90,
    progress: Progress = Progress(),
) -> dict:
    """Runs a sanity report for a SOFA scene: structural anomalies (Health Rules) plus per-step metrics (max displacement, max force, NaN-first-step) on every unmapped MechanicalObject. `complaint` is accepted for forward-compat and currently unused.

    `env` (optional) is a dict of environment-variable overrides merged over the server's environment for the scene subprocesses — use it to diagnose a scene variant chosen by an env var (e.g. `{"TRUNK_HYPER_MATERIAL": "MooneyRivlin"}`) without editing the scene file.

    `verbose=False` (default) compacts `solver_logs` to plugin loads, convergence summaries, errors, warnings, and tracebacks. The response carries `log_lines_dropped: int` when filtering happened. Set `verbose=True` for the full captured log (still subject to head/tail char-budget truncation).

    `dt` is passed straight to `Sofa.Simulation.animate` and overrides any `root.dt` the scene sets in `createScene`. `timeout_s` (default 90) is the wall-clock budget for the runner subprocess; raise it for long runs (e.g. 400 hyperelastic steps) instead of splitting the run.

    Task-capable: on a client that supports MCP tasks this returns a task handle immediately and the result arrives when the run finishes; `server_status` lists runs in flight. Legacy clients get the blocking call.
    """
    await progress.set_message(f"diagnose_scene: {int(steps)} steps, dt={dt}, budget {timeout_s}s")
    with _track_run("diagnose_scene", scene_path=scene_path, steps=int(steps), timeout_s=timeout_s):
        result = await asyncio.to_thread(
            diagnostics.diagnose_scene, scene_path,
            complaint=complaint, steps=steps, dt=dt, verbose=verbose, env=env, timeout_s=timeout_s,
        )
    await progress.set_message("diagnose_scene: done")
    return result


@mcp.tool(task=_RUN_AS_TASK)
async def enable_logs_and_run(
    scene_path: str,
    log_targets: list,
    steps: int = 5,
    dt: float = 0.01,
    verbose: bool = False,
    timeout_s: int = 90,
    progress: Progress = Progress(),
) -> dict:
    """Toggle printLog=True on objects matching `log_targets` (class names or node-path fragments), animate for `steps` iterations, return the captured logs.

    Use this after `diagnose_scene` flags an anomaly to inspect what a specific solver, mapping, or constraint is doing at runtime. Logs are compacted by default; pass `verbose=True` for the full stream. `dt` overrides the scene's `root.dt` for the stepping loop; `timeout_s` (default 90) is the subprocess wall-clock budget.
    """
    await progress.set_message(f"enable_logs_and_run: {int(steps)} steps, budget {timeout_s}s")
    with _track_run("enable_logs_and_run", scene_path=scene_path, steps=int(steps), timeout_s=timeout_s):
        result = await asyncio.to_thread(
            probes.enable_logs_and_run,
            scene_path=scene_path,
            log_targets=log_targets,
            steps=steps,
            dt=dt,
            verbose=verbose,
            timeout_s=timeout_s,
        )
    await progress.set_message("enable_logs_and_run: done")
    return result


@mcp.tool(task=_RUN_AS_TASK)
async def perturb_and_run(
    scene_path: str,
    parameter_changes: dict,
    steps: int = 50,
    dt: float = 0.01,
    verbose: bool = False,
    timeout_s: int = 90,
    progress: Progress = Progress(),
) -> dict:
    """Apply Data-field overrides (e.g. `{"/root/leg/ff": {"youngModulus": 1000}}`) before init, animate, return per-MO metrics. Use to test a hypothesis: "is the deformation small because the material is too stiff?" → halve youngModulus, re-run, see if displacement scales as expected.

    Path can be an object path like `/root/beam/FEM` (single object) or a node path like `/root/beam` (fans out to every object on the node that exposes the field — prefer object paths when ambiguous).

    Logs are compacted by default; pass `verbose=True` for the full stream. `dt` overrides the scene's `root.dt` for the stepping loop; `timeout_s` (default 90) is the subprocess wall-clock budget.
    """
    await progress.set_message(f"perturb_and_run: {int(steps)} steps, budget {timeout_s}s")
    with _track_run("perturb_and_run", scene_path=scene_path, steps=int(steps), timeout_s=timeout_s):
        result = await asyncio.to_thread(
            probes.perturb_and_run,
            scene_path=scene_path,
            parameter_changes=parameter_changes,
            steps=steps,
            dt=dt,
            verbose=verbose,
            timeout_s=timeout_s,
        )
    await progress.set_message("perturb_and_run: done")
    return result


def main() -> None:
    from sofa_mcp.architect.plugin_cache import generate_and_save_plugin_map
    _log_server_event("info", "Plugin cache generation starting...")
    try:
        generate_and_save_plugin_map()
        _log_server_event("info", "Plugin cache generation complete.")
    except Exception as e:
        _log_server_event("error", f"Plugin cache generation failed: {e}\n{traceback.format_exc()}")
        raise

    port = int(os.environ.get("SOFA_MCP_PORT", "8000"))
    _log_server_event("info", f"Starting FastMCP on 127.0.0.1:{port}/mcp")
    try:
        mcp.run(
            transport="streamable-http",
            host="127.0.0.1",
            port=port,
            path="/mcp",
            stateless_http=True,
            json_response=True,
        )
    except BaseException as e:
        # BaseException catches KeyboardInterrupt and SystemExit too — we want
        # *any* termination recorded, since the original crash report (issue 6)
        # described the process going silent without a Python-level exception.
        _log_server_event("error", f"mcp.run terminated: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise
    finally:
        _log_server_event("info", "mcp.run exited.")


if __name__ == "__main__":
    main()
