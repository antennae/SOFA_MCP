import subprocess
import tempfile
import os
import pathlib
from typing import Dict, Any, Optional



def write_and_test_scene(script_content: str, output_filename: str) -> Dict[str, Any]:
    """
    Writes a SOFA script, attempts to run a single step, and reports success or failure.
    
    Args:
        script_content: The Python source code for the SOFA scene. This script is expected
                        to define a function `add_scene_content(parent_node)`.
        output_filename: The final path where the script should be saved upon success.
        
    Returns:
        A dictionary containing success status, stdout, stderr, and the final file path.
    """

    utilities = """
def add_header(root_node):
    root_node.addObject("RequiredPlugin", pluginName="Sofa.Component.AnimationLoop")
    root_node.addObject("RequiredPlugin", pluginName="Sofa.Component.Constraint.Lagrangian.Solver")
    root_node.addObject("RequiredPlugin", pluginName="Sofa.Component.ODESolver.Backward")
    root_node.addObject("RequiredPlugin", pluginName="Sofa.Component.LinearSolver.Direct")
    root_node.addObject("RequiredPlugin", pluginName="Sofa.Component.Constraint.Lagrangian.Correction")
    root_node.addObject("RequiredPlugin", pluginName="Sofa.Component.Visual")
    root_node.addObject("VisualStyle", displayFlags="showBehavior showBehaviorModels")
    root_node.addObject(
        "FreeMotionAnimationLoop",
        name="AnimationLoop",
        parallelCollisionDetectionAndFreeMotion=False,
        parallelODESolving=False,
    )
    # if not inverse:
    root_node.addObject(
        "NNCGConstraintSolver",
        name="ConstraintSolver",
    )
    # else:
    #     root_node.addObject(
    #         "QPInverseProblemSolver",
    #         name="ConstraintSolver",
    #     )
def add_solver(
    root_node,
):
    solver_node = root_node.addChild("solver_node")

    solver_node.addObject(
        "EulerImplicitSolver",
        firstOrder=False,
    )
    solver_node.addObject(
        "SparseLDLSolver",
        name="Solver",
        template="CompressedRowSparseMatrixMat3x3d",
        parallelInverseProduct=True,
    )
    solver_node.addObject(
        "GenericConstraintCorrection",
        name="ConstraintCorrection",
    )
    return solver_node
    """
    python_path = os.path.expanduser("~/venv/bin/python")

    create_scene_function = f"""
{utilities}

# The user-provided script is expected to define a function called 'add_scene_content'
{script_content}

def createScene(rootNode):
    # 1. Call your utilities first
    add_header(rootNode)
    solver_node = add_solver(rootNode)

    # 2. Call the user-defined function
    if 'add_scene_content' in globals():
        add_scene_content(solver_node)
    else:
        raise NameError("The provided script_content must define a function called 'add_scene_content(parent_node)'.")
"""

    # Validation wrapper to run one step
    validation_wrapper = f"""
import Sofa
import Sofa.Core
import sys

{create_scene_function}

def _iter_nodes(node):
    yield node
    for child in getattr(node, 'children', []):
        yield from _iter_nodes(child)

def _node_has_class(node, class_name: str) -> bool:
    for obj in getattr(node, 'objects', []):
        try:
            if hasattr(obj, 'getClassName') and obj.getClassName() == class_name:
                return True
        except Exception:
            pass
    return False

def _tree_has_class(node, class_name: str) -> bool:
    return any(_node_has_class(n, class_name) for n in _iter_nodes(node))

def _assert_required_components(root):
    missing = []
    # These are added by add_header/add_solver. If they are missing, the scene
    # may "run" but behave incorrectly.
    if root.getObject('AnimationLoop') is None:
        missing.append("FreeMotionAnimationLoop (name='AnimationLoop')")
    if root.getObject('ConstraintSolver') is None:
        missing.append("NNCGConstraintSolver (name='ConstraintSolver')")

    solver_node = root.getChild('solver_node')
    if solver_node is None:
        missing.append("Child node 'solver_node'")
    else:
        if not _node_has_class(solver_node, 'EulerImplicitSolver'):
            missing.append("EulerImplicitSolver (in solver_node)")
        if solver_node.getObject('Solver') is None:
            missing.append("SparseLDLSolver (name='Solver')")
        if solver_node.getObject('ConstraintCorrection') is None:
            missing.append("GenericConstraintCorrection (name='ConstraintCorrection')")

    if missing:
        raise RuntimeError("Missing required baseline components: " + "; ".join(missing))

    # Soft check: warn if scene has no DOFs.
    if not _tree_has_class(root, 'MechanicalObject'):
        print("WARNING: No MechanicalObject found in the scene graph.")

def validate():
    root = Sofa.Core.Node("root")
    try:
        if 'createScene' not in globals():
            print("ERROR: createScene function missing", file=sys.stderr)
            sys.exit(1)
            
        createScene(root)
        _assert_required_components(root)
        Sofa.Simulation.init(root)
        # Try one simulation step
        Sofa.Simulation.animate(root, 0.01)
        print("SUCCESS: Scene initialized and animated 1 step.")
    except Exception as e:
        print(f"ERROR: {{str(e)}}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    validate()
"""

    with tempfile.NamedTemporaryFile(suffix=".py", mode='w', delete=False) as tmp:
        tmp.write(validation_wrapper)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [python_path, tmp_path],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            # Save the original script content (without validation wrapper) to the target location
            output_path = pathlib.Path(output_filename).absolute()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            # We save the full create_scene_function which includes utilities and the user script
            with open(output_path, 'w') as f:
                f.write(create_scene_function)
            
            return {
                "success": True,
                "message": "Scene validated and saved.",
                "path": str(output_path),
                "stdout": result.stdout
            }
        else:
            return {
                "success": False,
                "error": result.stderr or result.stdout,
                "message": "Validation failed. Please correct the script based on the error."
            }
            
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Timeout",
            "message": "The scene took too long to initialize (possible infinite loop or massive mesh)."
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "An unexpected error occurred during execution."
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
