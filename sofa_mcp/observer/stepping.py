import os
import sys
import importlib.util
import copy
import json
from datetime import datetime
import Sofa.Core
import Sofa.Simulation


def _results_dir() -> str:
    """Returns the canonical .sofa_mcp_results directory, anchored to the project root."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(project_root, ".sofa_mcp_results")
    os.makedirs(path, exist_ok=True)
    return path


def _load_scene_module(scene_path: str):
    """Loads a SOFA scene module from a file path. Returns (module, module_name) or raises."""
    module_name = f"scene_module_{os.path.basename(scene_path).replace('.', '_')}_{id(scene_path)}"
    spec = importlib.util.spec_from_file_location(module_name, scene_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load scene from {scene_path}")
    scene_module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = scene_module
    spec.loader.exec_module(scene_module)
    return scene_module, module_name


def _resolve_target(root, node_path: str):
    """Walks the scene graph along node_path and returns the terminal node or object."""
    target = root
    parts = [p for p in node_path.strip("/").split("/") if p]
    for i, part in enumerate(parts):
        child = target.getChild(part)
        if child:
            target = child
            continue
        if i == len(parts) - 1:
            obj = target.getObject(part)
            if obj:
                return obj
        raise RuntimeError(f"Node/object not found: '{part}' in path '{node_path}'")
    return target


def _serialize_value(val):
    """Converts a SOFA data value to a JSON-serializable Python type."""
    if hasattr(val, "tolist"):
        return val.tolist()
    if isinstance(val, list):
        return copy.deepcopy(val)
    return val


def run_and_extract(scene_path: str, steps: int, dt: float, node_path: str, field: str) -> dict:
    """
    Runs the simulation for a given number of steps and extracts data from a specific field.
    The results are saved to a JSON file to avoid large MCP response payloads.

    Args:
        scene_path: Path to the python scene file.
        steps: Number of simulation steps to run.
        dt: Time step.
        node_path: Path to the node or object in the scene graph (e.g., 'mechanics/mo').
        field: Name of the data field to extract (e.g., 'position').

    Returns:
        A dictionary containing:
            - success: Boolean indicating success.
            - output_file: Path to the JSON file containing the full data.
            - steps: Number of steps completed.
            - data_preview: The field value at the final step (for quick verification).
            - error: Error message (if failed).
    """
    if not os.path.exists(scene_path):
        return {"success": False, "error": f"Scene file not found: {scene_path}"}

    module_name = None
    try:
        scene_module, module_name = _load_scene_module(scene_path)

        if not hasattr(scene_module, "createScene"):
            return {"success": False, "error": "Scene file must contain a 'createScene' function."}

        root = Sofa.Core.Node("root")
        scene_module.createScene(root)
        Sofa.Simulation.init(root)

        target = _resolve_target(root, node_path)
        data_object = target.findData(field)
        if not data_object:
            return {"success": False, "error": f"Data field '{field}' not found"}

        results = []
        for _ in range(steps):
            Sofa.Simulation.animate(root, dt)
            results.append(_serialize_value(data_object.value))

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if module_name:
            sys.modules.pop(module_name, None)

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(_results_dir(), f"sim_data_{timestamp}.json")

        meta = {
            "scene_path": scene_path,
            "node_path": node_path,
            "field": field,
            "steps": steps,
            "dt": dt,
            "timestamp": timestamp,
        }
        with open(output_path, "w") as f:
            json.dump({"metadata": meta, "data": results}, f)

        last = results[-1] if results else None
        data_shape = []
        data_preview = None
        if last is not None:
            import numpy as np
            try:
                data_shape = list(np.array(last).shape)
                data_preview = last[:5] if isinstance(last, list) and len(last) > 5 else last
            except Exception:
                data_preview = str(last)[:100]

        return {
            "success": True,
            "output_file": output_path,
            "steps": steps,
            "data_shape": data_shape,
            "data_preview": data_preview,
            "message": "Full simulation data saved to file. Use 'process_simulation_data' to analyze.",
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to save results: {str(e)}"}


def run_and_extract_multi(
    scene_path: str,
    steps: int,
    dt: float,
    fields: list[dict],
) -> dict:
    """
    Runs a SOFA simulation and extracts data from multiple fields/nodes in a single run.
    More efficient than calling run_and_extract repeatedly when you need several fields.

    Args:
        scene_path: Path to the python scene file.
        steps: Number of simulation steps to run.
        dt: Time step.
        fields: List of field descriptors. Each entry must have:
                  - node_path (str): Path to node/object in scene graph (e.g. 'mechanics/mo').
                  - field (str): Data field name to extract (e.g. 'position').
                  - key (str, optional): Alias for this field in the output JSON.
                    Defaults to '<node_path>/<field>' if omitted.

    Returns:
        A dictionary containing:
            - success: Boolean indicating success.
            - output_file: Path to the JSON file with full time-series data for all fields.
            - steps: Number of steps completed.
            - fields: Per-field summary dict mapping key -> {data_shape, data_preview}.
            - error: Error message (if failed).

    Output JSON format:
        {
          "metadata": {
            "scene_path": str, "steps": int, "dt": float, "timestamp": str,
            "fields": [{"node_path": str, "field": str, "key": str}, ...]
          },
          "fields": {
            "<key>": [[step_0_value], [step_1_value], ...]
          }
        }
    """
    if not fields:
        return {"success": False, "error": "'fields' must be a non-empty list."}

    if not os.path.exists(scene_path):
        return {"success": False, "error": f"Scene file not found: {scene_path}"}

    # Normalize keys and check for duplicates
    descriptors = []
    seen_keys = set()
    for entry in fields:
        node_path = entry.get("node_path", "").strip()
        field_name = entry.get("field", "").strip()
        if not node_path or not field_name:
            return {"success": False, "error": f"Each field descriptor must have 'node_path' and 'field'. Got: {entry}"}
        key = entry.get("key") or f"{node_path}/{field_name}"
        if key in seen_keys:
            return {"success": False, "error": f"Duplicate key '{key}' in fields list."}
        seen_keys.add(key)
        descriptors.append({"node_path": node_path, "field": field_name, "key": key})

    module_name = None
    try:
        scene_module, module_name = _load_scene_module(scene_path)

        if not hasattr(scene_module, "createScene"):
            return {"success": False, "error": "Scene file must contain a 'createScene' function."}

        root = Sofa.Core.Node("root")
        scene_module.createScene(root)
        Sofa.Simulation.init(root)

        # Resolve all targets upfront — fail fast before running any steps
        data_objects = {}
        for d in descriptors:
            try:
                target = _resolve_target(root, d["node_path"])
            except RuntimeError as e:
                return {"success": False, "error": str(e)}

            data_obj = target.findData(d["field"])
            if data_obj is None:
                return {"success": False, "error": f"Data field '{d['field']}' not found at '{d['node_path']}'"}
            data_objects[d["key"]] = data_obj

        # Single animate loop — collect all fields at each step
        results = {d["key"]: [] for d in descriptors}
        for _ in range(steps):
            Sofa.Simulation.animate(root, dt)
            for d in descriptors:
                results[d["key"]].append(_serialize_value(data_objects[d["key"]].value))

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if module_name:
            sys.modules.pop(module_name, None)

    try:
        import numpy as np

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(_results_dir(), f"sim_data_multi_{timestamp}.json")

        meta = {
            "scene_path": scene_path,
            "steps": steps,
            "dt": dt,
            "timestamp": timestamp,
            "fields": descriptors,
        }
        with open(output_path, "w") as f:
            json.dump({"metadata": meta, "fields": results}, f)

        # Build per-field summary for the response
        field_summaries = {}
        for d in descriptors:
            key = d["key"]
            last = results[key][-1] if results[key] else None
            shape = []
            preview = None
            if last is not None:
                try:
                    shape = list(np.array(last).shape)
                    preview = last[:5] if isinstance(last, list) and len(last) > 5 else last
                except Exception:
                    preview = str(last)[:100]
            field_summaries[key] = {"data_shape": shape, "data_preview": preview}

        return {
            "success": True,
            "output_file": output_path,
            "steps": steps,
            "fields": field_summaries,
            "message": "Full multi-field simulation data saved. Use 'process_simulation_data' on individual fields if needed.",
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to save results: {str(e)}"}


def process_simulation_data(
    file_path: str,
    start_step: int = 0,
    end_step: int = -1,
    indices: list[int] = None,
    calculate_metrics: bool = False,
    include_data: bool = False,
) -> dict:
    """
    Processes a simulation data file to extract a subset of results or calculate
    SOFA-specific metrics like net displacement and stability.

    Args:
        file_path: Path to the JSON file containing simulation data.
        start_step: The first step to include.
        end_step: The last step to include (exclusive). -1 means all steps.
        indices: Optional list of indices to extract from the data at each step
                 (e.g., specific vertex indices from a MechanicalObject).
        calculate_metrics: Whether to calculate displacement, peak, and stability.
        include_data: Whether to include the full (possibly filtered) data array in the response.

    Returns:
        A dictionary containing:
            - success: Boolean indicating success.
            - metadata: Metadata from the original simulation.
            - data: The requested subset of data (only if include_data=True).
            - data_shape: Shape of the processed data array.
            - metrics: Calculated SOFA metrics (if requested).
            - error: Error message (if failed).
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    try:
        with open(file_path, "r") as f:
            full_content = json.load(f)

        metadata = full_content.get("metadata", {})
        raw_data = full_content.get("data", [])

        if not raw_data:
            return {"success": True, "data": [], "total_steps": 0}

        # 1. Step slicing
        if end_step == -1 or end_step > len(raw_data):
            end_step = len(raw_data)
        step_subset = raw_data[start_step:end_step]

        # 2. Index selection (spatial filter)
        final_data = []
        if indices is not None:
            for step_val in step_subset:
                if isinstance(step_val, list):
                    try:
                        final_data.append([step_val[i] for i in indices])
                    except IndexError:
                        return {"success": False, "error": "Index out of range for data at step."}
                else:
                    final_data.append(step_val)
        else:
            final_data = step_subset

        import numpy as np
        data_np = np.array(final_data)

        result = {
            "success": True,
            "metadata": metadata,
            "total_steps": len(raw_data),
            "subset_range": [start_step, end_step],
            "selection_indices": indices,
            "data_shape": list(data_np.shape),
        }

        if include_data:
            result["data"] = final_data

        if calculate_metrics and step_subset:
            if len(data_np) == 0:
                result["metrics_error"] = "Empty step range — cannot compute metrics."
            else:
                try:
                    arr = data_np
                    if arr.ndim >= 2:
                        displacement_vec = (arr[-1] - arr[0]).tolist()
                        if arr.ndim == 3 and arr.shape[-1] == 3:
                            dist = np.linalg.norm(arr[-1] - arr[0], axis=-1)
                            net_disp_mag = float(np.max(dist))
                            stability = float(np.max(np.linalg.norm(arr[-1] - arr[-2], axis=-1))) if len(arr) > 1 else 0.0
                            peak_mag = float(np.max(np.linalg.norm(arr, axis=-1)))
                        else:
                            net_disp_mag = float(np.max(np.abs(arr[-1] - arr[0])))
                            stability = float(np.max(np.abs(arr[-1] - arr[-2]))) if len(arr) > 1 else 0.0
                            peak_mag = float(np.max(np.abs(arr)))
                    else:
                        displacement_vec = float(arr[-1] - arr[0])
                        net_disp_mag = abs(displacement_vec)
                        stability = abs(float(arr[-1] - arr[-2])) if len(arr) > 1 else 0.0
                        peak_mag = float(np.max(np.abs(arr)))

                    result["metrics"] = {
                        "net_displacement_vector": displacement_vec,
                        "max_displacement_magnitude": net_disp_mag,
                        "stability_measure": stability,
                        "is_converged": stability < 1e-3,
                        "peak_magnitude": peak_mag,
                        "final_values": arr[-1].tolist(),
                    }
                except Exception as e:
                    result["metrics_error"] = f"Could not calculate metrics: {str(e)}"

        return result

    except Exception as e:
        return {"success": False, "error": f"Failed to process data: {str(e)}"}
