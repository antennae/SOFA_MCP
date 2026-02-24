import os
import sys
import importlib.util
import copy
import Sofa.Core
import Sofa.Simulation

def run_and_extract(scene_path: str, steps: int, dt: float, node_path: str, field: str) -> dict:
    """
    Runs the simulation for a given number of steps and extracts data from a specific field.

    Args:
        scene_path: Path to the python scene file.
        steps: Number of simulation steps to run.
        dt: Time step.
        node_path: Path to the node or object in the scene graph (e.g., 'mechanics/mo').
        field: Name of the data field to extract (e.g., 'position').

    Returns:
        A dictionary containing:
            - success: Boolean indicating success.
            - data: List of values extracted at each step (if successful).
            - error: Error message (if failed).
    """
    if not os.path.exists(scene_path):
        return {"success": False, "error": f"Scene file not found: {scene_path}"}

    # Load the scene module
    try:
        # Use a unique module name to avoid conflicts
        module_name = f"scene_module_{os.path.basename(scene_path).replace('.', '_')}"
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

    return {"success": True, "data": results}