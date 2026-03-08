import subprocess
import tempfile
import os
import pathlib
from typing import Dict, Any


def _build_scene_source(script_content: str) -> str:
    """The user-provided script is now expected to be the full content,
    including the createScene(rootNode) function.
    """
    return script_content


def _build_wrapper_preamble(script_content: str, *, extra_imports: str = "") -> str:
    lines = [
        "import Sofa",
        "import Sofa.Core",
        "import Sofa.Simulation",
        "import sys",
    ]
    if extra_imports.strip():
        lines.append(extra_imports.strip())

    lines.append("")
    lines.append(script_content)
    lines.append("")
    return "\n".join(lines)


def _build_validation_wrapper(create_scene_function: str) -> str:
    preamble = _build_wrapper_preamble(create_scene_function)
    return (
        preamble
        + """
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
    # Flexible validation: we check if the scene tree contains the necessary physics building blocks.
    checks = {
        "AnimationLoop": _tree_has_class(root, "FreeMotionAnimationLoop") or _tree_has_class(root, "DefaultAnimationLoop"),
        "ConstraintSolver": _tree_has_class(root, "NNCGConstraintSolver") or _tree_has_class(root, "QPInverseProblemSolver"),
        "TimeIntegration": _tree_has_class(root, "EulerImplicitSolver") or _tree_has_class(root, "RungeKutta4Solver"),
        "LinearSolver": _tree_has_class(root, "SparseLDLSolver") or _tree_has_class(root, "CGLinearSolver") or _tree_has_class(root, "SparseDirectSolver"),
    }
    
    missing = [k for k, v in checks.items() if not v]
    if missing:
        # We don't raise here yet to allow the agent to see the warnings first, 
        # but the tool output will reflect this.
        print(f"WARNING: Missing key components: {', '.join(missing)}")

def validate():
    root = Sofa.Core.Node("root")
    try:
        if "createScene" not in globals():
            print("ERROR: createScene function missing", file=sys.stderr)
            sys.exit(1)

        createScene(root)
        _assert_required_components(root)
        Sofa.Simulation.init(root)
        Sofa.Simulation.animate(root, 0.01)
        print("SUCCESS: Scene initialized and animated 1 step.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    validate()
"""
    )


def _build_summary_wrapper(create_scene_function: str) -> str:
    preamble = _build_wrapper_preamble(create_scene_function, extra_imports="import json")
    return (
        preamble
        + """
# These are baseline solver objects added by add_solver(rootNode) under /root/solver_node.
# We use this set only to estimate whether the user added any *additional* objects
# under solver_node.
SOLVER_BASELINE_CLASSES = {
    'EulerImplicitSolver',
    'SparseLDLSolver',
    'GenericConstraintCorrection',
}

def _iter_nodes(node, path="/"):
    yield node, path
    for child in getattr(node, 'children', []):
        try:
            child_name = child.getName() if hasattr(child, 'getName') else getattr(child, 'name', 'child')
        except Exception:
            child_name = 'child'
        child_path = path.rstrip('/') + '/' + str(child_name)
        yield from _iter_nodes(child, child_path)

def _safe_obj_name(obj):
    try:
        if hasattr(obj, 'getName'):
            return obj.getName()
    except Exception:
        pass
    return None

def _safe_class_name(obj):
    try:
        if hasattr(obj, 'getClassName'):
            return obj.getClassName()
    except Exception:
        pass
    return obj.__class__.__name__

def _get_template(obj):
    try:
        # Many SOFA objects have a 'template' data field
        return str(obj.getData('template').getValue())
    except:
        return None

def summarize():
    root = Sofa.Core.Node("root")
    try:
        if 'createScene' not in globals():
            print("ERROR: createScene function missing", file=sys.stderr)
            sys.exit(1)

        createScene(root)

        nodes = []
        class_counts = {}
        object_count = 0
        mechanical_object_count = 0

        # These are classes that indicate the scene's health.
        has_animation_loop = _tree_has_class(root, 'FreeMotionAnimationLoop') or _tree_has_class(root, 'DefaultAnimationLoop')
        has_constraint_solver = _tree_has_class(root, 'NNCGConstraintSolver') or _tree_has_class(root, 'QPInverseProblemSolver')
        has_time_integration = _tree_has_class(root, 'EulerImplicitSolver') or _tree_has_class(root, 'RungeKutta4Solver')

        for node, path in _iter_nodes(root, "/root"):
            try:
                node_name = node.getName() if hasattr(node, 'getName') else getattr(node, 'name', None)
            except Exception:
                node_name = None

            objects = []
            for obj in getattr(node, 'objects', []):
                class_name = _safe_class_name(obj)
                obj_name = _safe_obj_name(obj)
                template = _get_template(obj)
                objects.append({"class": class_name, "name": obj_name, "template": template})

                object_count += 1
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
                if class_name == 'MechanicalObject':
                    mechanical_object_count += 1

            nodes.append({"path": path, "name": node_name, "objectCount": len(objects), "objects": objects})

        checks = []
        checks.append({"name": "has_animation_loop", "passed": has_animation_loop})
        checks.append({"name": "has_constraint_solver", "passed": has_constraint_solver})
        checks.append({"name": "has_time_integration", "passed": has_time_integration})

        summary = {
            "success": True,
            "node_count": len(nodes),
            "object_count": object_count,
            "class_counts": class_counts,
            "mechanical_object_count": mechanical_object_count,
            "checks": checks,
            "nodes": nodes,
        }

        # Prefix to allow robust parsing even if user code prints.
        print("SCENE_SUMMARY_JSON:" + json.dumps(summary, separators=(",", ":")))
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    summarize()
"""
    )


def validate_scene(script_content: str, *, timeout_s: int = 30) -> Dict[str, Any]:
    """Validates a user-provided scene snippet by initializing and animating one step.

    The user-provided `script_content` must define `add_scene_content(parent_node)`.
    Returns a dict with `success` plus stdout/stderr-derived error info.
    """

    python_path = os.path.expanduser("~/venv/bin/python")
    create_scene_function = _build_scene_source(script_content)
    validation_wrapper = _build_validation_wrapper(create_scene_function)

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write(validation_wrapper)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [python_path, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )

        if result.returncode == 0:
            return {
                "success": True,
                "message": "Scene validated.",
                "stdout": result.stdout,
            }

        return {
            "success": False,
            "message": "Validation failed. Please correct the script based on the error.",
            "error": result.stderr or result.stdout,
            "stdout": result.stdout,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Timeout",
            "message": "The scene took too long to initialize (possible infinite loop or massive mesh).",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "An unexpected error occurred during execution.",
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def summarize_scene(script_content: str, *, timeout_s: int = 30) -> Dict[str, Any]:
    """Builds the scene graph and returns a structured summary + basic rule checks.

    This does not call Sofa.Simulation.init/animate; it's intended for fast inspection
    and verification of scene structure.
    """

    python_path = os.path.expanduser("~/venv/bin/python")
    create_scene_function = _build_scene_source(script_content)
    summary_wrapper = _build_summary_wrapper(create_scene_function)

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write(summary_wrapper)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [python_path, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "message": "Scene summary failed.",
                "error": result.stderr or result.stdout,
            }

        summary_line = None
        for line in (result.stdout or "").splitlines()[::-1]:
            if line.startswith("SCENE_SUMMARY_JSON:"):
                summary_line = line
                break

        if not summary_line:
            return {
                "success": False,
                "message": "Scene summary did not produce JSON output.",
                "error": result.stdout,
            }

        import json

        payload = summary_line[len("SCENE_SUMMARY_JSON:") :]
        parsed = json.loads(payload)
        return parsed

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Timeout",
            "message": "The scene took too long to build (possible infinite loop or massive mesh).",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "An unexpected error occurred during summarization.",
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def write_scene(script_content: str, output_filename: str) -> Dict[str, Any]:
    """Writes the generated SOFA scene (utilities + user content + createScene) to disk.

    This does not run validation. Prefer calling `validate_scene` first.
    """

    create_scene_function = _build_scene_source(script_content)
    output_path = pathlib.Path(output_filename).absolute()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write(create_scene_function)

    return {
        "success": True,
        "message": "Scene saved.",
        "path": str(output_path),
    }


def write_and_test_scene(script_content: str, output_filename: str) -> Dict[str, Any]:
    """Validates a scene snippet and writes it to disk only on success."""

    validation = validate_scene(script_content)
    if not validation.get("success"):
        return {
            "success": False,
            "error": validation.get("error"),
            "message": validation.get("message", "Validation failed."),
            "stdout": validation.get("stdout", ""),
        }

    written = write_scene(script_content, output_filename)
    return {
        "success": True,
        "message": "Scene validated and saved.",
        "path": written.get("path"),
        "stdout": validation.get("stdout", ""),
    }


def load_scene(scene_path: str, *, max_bytes: int = 1_000_000) -> Dict[str, Any]:
    """Loads a scene file from disk and returns its contents.

    Intended for agentic workflows that need to *edit an existing* scene rather than
    generating from scratch.
    """

    path = pathlib.Path(scene_path).expanduser()
    try:
        path = path.resolve()
    except Exception:
        path = path.absolute()

    if not path.exists():
        return {
            "success": False,
            "message": "Scene file not found.",
            "error": f"Path does not exist: {path}",
            "path": str(path),
        }

    if not path.is_file():
        return {
            "success": False,
            "message": "Scene path is not a file.",
            "error": f"Not a file: {path}",
            "path": str(path),
        }

    size_bytes = path.stat().st_size
    if size_bytes > max_bytes:
        return {
            "success": False,
            "message": "Scene file is too large to load.",
            "error": f"File size {size_bytes} exceeds max_bytes={max_bytes}",
            "path": str(path),
            "size_bytes": size_bytes,
        }

    content = path.read_text(encoding="utf-8", errors="replace")
    return {
        "success": True,
        "message": "Scene loaded.",
        "path": str(path),
        "size_bytes": size_bytes,
        "content": content,
    }


def _find_nth(haystack: str, needle: str, n: int) -> int:
    if n < 1:
        raise ValueError("occurrence must be >= 1")
    start = 0
    for _ in range(n):
        idx = haystack.find(needle, start)
        if idx == -1:
            return -1
        start = idx + len(needle)
    return idx


def patch_scene(scene_path: str, patch: Any) -> Dict[str, Any]:
    """Applies a structured text patch to an existing scene file.

    Patch format (single op dict):
      - {"op": "replace", "old": str, "new": str, "count"?: int}
      - {"op": "insert_before"|"insert_after", "anchor": str, "text": str, "occurrence"?: int}
      - {"op": "append"|"prepend", "text": str}

    You can also pass a list of such operations to apply them sequentially.
    """

    loaded = load_scene(scene_path)
    if not loaded.get("success"):
        return loaded

    original = loaded.get("content", "")
    updated = original

    ops = patch if isinstance(patch, list) else [patch]
    if not isinstance(ops, list) or len(ops) == 0:
        return {
            "success": False,
            "message": "Invalid patch format.",
            "error": "patch must be a dict or a non-empty list of dicts",
            "path": loaded.get("path"),
        }

    applied_ops = 0
    for op in ops:
        if not isinstance(op, dict):
            return {
                "success": False,
                "message": "Invalid patch operation.",
                "error": "Each patch operation must be an object/dict",
                "path": loaded.get("path"),
            }

        op_name = op.get("op") or op.get("type")
        if not isinstance(op_name, str) or not op_name:
            return {
                "success": False,
                "message": "Invalid patch operation.",
                "error": "Missing patch field 'op'",
                "path": loaded.get("path"),
            }

        if op_name == "replace":
            old = op.get("old")
            new = op.get("new")
            if not isinstance(old, str) or not isinstance(new, str):
                return {
                    "success": False,
                    "message": "Invalid replace operation.",
                    "error": "replace op requires string fields 'old' and 'new'",
                    "path": loaded.get("path"),
                }

            count = op.get("count", 1)
            if not isinstance(count, int) or count < 1:
                return {
                    "success": False,
                    "message": "Invalid replace operation.",
                    "error": "replace op 'count' must be an int >= 1",
                    "path": loaded.get("path"),
                }

            if old not in updated:
                return {
                    "success": False,
                    "message": "Patch could not be applied.",
                    "error": "replace target not found",
                    "path": loaded.get("path"),
                }

            updated = updated.replace(old, new, count)
            applied_ops += 1

        elif op_name in ("insert_before", "insert_after"):
            anchor = op.get("anchor")
            text = op.get("text")
            if not isinstance(anchor, str) or not isinstance(text, str):
                return {
                    "success": False,
                    "message": "Invalid insert operation.",
                    "error": "insert op requires string fields 'anchor' and 'text'",
                    "path": loaded.get("path"),
                }

            occurrence = op.get("occurrence", 1)
            if not isinstance(occurrence, int) or occurrence < 1:
                return {
                    "success": False,
                    "message": "Invalid insert operation.",
                    "error": "insert op 'occurrence' must be an int >= 1",
                    "path": loaded.get("path"),
                }

            idx = _find_nth(updated, anchor, occurrence)
            if idx == -1:
                return {
                    "success": False,
                    "message": "Patch could not be applied.",
                    "error": "insert anchor not found",
                    "path": loaded.get("path"),
                }

            insert_at = idx if op_name == "insert_before" else (idx + len(anchor))
            updated = updated[:insert_at] + text + updated[insert_at:]
            applied_ops += 1

        elif op_name in ("append", "prepend"):
            text = op.get("text")
            if not isinstance(text, str):
                return {
                    "success": False,
                    "message": "Invalid append/prepend operation.",
                    "error": "append/prepend op requires string field 'text'",
                    "path": loaded.get("path"),
                }

            updated = (text + updated) if op_name == "prepend" else (updated + text)
            applied_ops += 1

        else:
            return {
                "success": False,
                "message": "Unsupported patch operation.",
                "error": f"Unsupported op: {op_name}",
                "path": loaded.get("path"),
            }

    if updated == original:
        return {
            "success": False,
            "message": "No changes applied.",
            "error": "Patch operations resulted in no modifications",
            "path": loaded.get("path"),
        }

    path = pathlib.Path(loaded["path"])
    path.write_text(updated, encoding="utf-8")
    return {
        "success": True,
        "message": "Scene patched.",
        "path": str(path),
        "applied_ops": applied_ops,
        "size_bytes": path.stat().st_size,
    }
