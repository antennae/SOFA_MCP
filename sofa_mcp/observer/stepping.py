import os
import sys
import importlib.util
import copy
import json
import tempfile
from datetime import datetime
import Sofa.Core
import Sofa.Simulation

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
            - sample_data: The field value at the final step (for quick verification).
            - error: Error message (if failed).
    """
    if not os.path.exists(scene_path):
        return {"success": False, "error": f"Scene file not found: {scene_path}"}

    # Load the scene module
    try:
        # Use a unique module name to avoid conflicts
        module_name = f"scene_module_{os.path.basename(scene_path).replace('.', '_')}_{id(scene_path)}"
        spec = importlib.util.spec_from_file_location(module_name, scene_path)
        if spec is None or spec.loader is None:
             return {"success": False, "error": f"Could not load scene from {scene_path}"}
        
        scene_module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = scene_module
        spec.loader.exec_module(scene_module)

        if not hasattr(scene_module, "createScene"):
             return {"success": False, "error": "Scene file must contain a 'createScene' function."}

    except Exception as e:
        return {"success": False, "error": f"Failed to load scene: {str(e)}"}

    # Initialize SOFA simulation
    try:
        root = Sofa.Core.Node("root")
        scene_module.createScene(root)
        Sofa.Simulation.init(root)
    except Exception as e:
        return {"success": False, "error": f"Failed to initialize simulation: {str(e)}"}

    # Resolve Node/Object
    try:
        target = root
        parts = [p for p in node_path.strip('/').split('/') if p]
        
        for i, part in enumerate(parts):
            # 1. Try child node
            child = target.getChild(part)
            if child:
                target = child
                continue
            
            # 2. Try object (only if last part)
            if i == len(parts) - 1:
                obj = target.getObject(part)
                if obj:
                    target = obj
                    break
            
            return {"success": False, "error": f"Node not found: {part}"}
        
        # Resolve Field
        data_object = target.findData(field)
        if not data_object:
             return {"success": False, "error": f"Data field '{field}' not found"}

    except Exception as e:
        return {"success": False, "error": f"Error resolving path: {str(e)}"}

    # Run loop
    results = []
    try:
        for _ in range(steps):
            Sofa.Simulation.animate(root, dt)
            
            val = data_object.value
            # Convert to python types for JSON serialization
            if hasattr(val, "tolist"):
                val = val.tolist()
            elif isinstance(val, list):
                val = copy.deepcopy(val)
            
            results.append(val)
            
    except Exception as e:
        return {"success": False, "error": f"Simulation runtime error: {str(e)}"}

    # Save to file
    try:
        results_dir = os.path.abspath(".sofa_mcp_results")
        os.makedirs(results_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sim_data_{timestamp}.json"
        output_path = os.path.join(results_dir, filename)
        
        meta = {
            "scene_path": scene_path,
            "node_path": node_path,
            "field": field,
            "steps": steps,
            "dt": dt,
            "timestamp": timestamp
        }
        
        with open(output_path, "w") as f:
            json.dump({"metadata": meta, "data": results}, f)

        # Optimization: Only return shape and a tiny preview to the LLM
        last_step_data = results[-1] if results else None
        data_shape = []
        data_preview = None
        
        if last_step_data is not None:
            import numpy as np
            try:
                data_shape = list(np.array(last_step_data).shape)
                if len(last_step_data) > 5:
                    data_preview = last_step_data[:5] # Just a peek
                else:
                    data_preview = last_step_data
            except:
                data_preview = str(last_step_data)[:100]

        return {
            "success": True, 
            "output_file": output_path,
            "steps": steps,
            "data_shape": data_shape,
            "data_preview": data_preview,
            "message": "Full simulation data saved to file. Use 'process_simulation_data' to analyze."
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to save results: {str(e)}"}

def process_simulation_data(
    file_path: str, 
    start_step: int = 0, 
    end_step: int = -1, 
    indices: list[int] = None,
    calculate_metrics: bool = False,
    include_data: bool = False
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

        # 1. Step Slicing
        if end_step == -1 or end_step > len(raw_data):
            end_step = len(raw_data)
        step_subset = raw_data[start_step:end_step]
        
        # 2. Index Selection (Spatial selection)
        # If indices are provided, we filter each step's array.
        final_data = []
        if indices is not None:
            for step_val in step_subset:
                if isinstance(step_val, list):
                    try:
                        filtered = [step_val[i] for i in indices]
                        final_data.append(filtered)
                    except IndexError:
                        return {"success": False, "error": f"Index out of range for data at step."}
                else:
                    # If step_val is a scalar, indices are ignored
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
            "data_shape": list(data_np.shape)
        }
        
        if include_data:
            result["data"] = final_data
        
        if calculate_metrics and step_subset:
            try:
                arr = data_np
                
                # We expect arr to be (Steps, ...)
                if arr.ndim >= 2:
                    # Case: Vector data (e.g., [Steps, N, 3] or [Steps, N])
                    # Net Displacement is the vector difference per element
                    displacement_vec = (arr[-1] - arr[0]).tolist()
                    
                    # If it's Vec3 (rank 3: Steps, N, 3), calculate magnitude of displacement
                    if arr.ndim == 3 and arr.shape[-1] == 3:
                        dist = np.linalg.norm(arr[-1] - arr[0], axis=-1)
                        net_disp_mag = float(np.max(dist))
                        
                        # Stability based on max vertex movement magnitude
                        if len(arr) > 1:
                            stability = float(np.max(np.linalg.norm(arr[-1] - arr[-2], axis=-1)))
                        else:
                            stability = 0.0
                        
                        peak_mag = float(np.max(np.linalg.norm(arr, axis=-1)))
                    else:
                        # General rank-2 data (e.g. list of scalars)
                        net_disp_mag = float(np.max(np.abs(arr[-1] - arr[0])))
                        stability = float(np.max(np.abs(arr[-1] - arr[-2]))) if len(arr) > 1 else 0.0
                        peak_mag = float(np.max(np.abs(arr)))
                else:
                    # Case: Scalar data (Steps,)
                    displacement_vec = float(arr[-1] - arr[0])
                    net_disp_mag = abs(displacement_vec)
                    stability = abs(float(arr[-1] - arr[-2])) if len(arr) > 1 else 0.0
                    peak_mag = float(np.max(np.abs(arr)))

                result["metrics"] = {
                    "net_displacement_vector": displacement_vec,
                    "max_displacement_magnitude": net_disp_mag,
                    "stability_measure": stability,
                    "is_converged": stability < 1e-3, # tighted convergence threshold
                    "peak_magnitude": peak_mag,
                    "final_values": arr[-1].tolist() # helpful summary
                }
            except Exception as e:
                result["metrics_error"] = f"Could not calculate metrics: {str(e)}"
                
        return result

    except Exception as e:
        return {"success": False, "error": f"Failed to process data: {str(e)}"}
