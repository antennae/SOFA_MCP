import ast
import os
from typing import Any, Dict

def update_data_field(scene_path: str, object_name: str, field_name: str, new_value: Any) -> Dict[str, Any]:
    """
    Updates a specific field of a SOFA object in a Python scene file.
    
    This function parses the Python script, locates the addObject call for the 
    specified object_name, and updates (or adds) the keyword argument for field_name.
    It attempts to preserve original formatting by only patching the specific range.

    Args:
        scene_path: Path to the python scene file.
        object_name: The 'name' of the object to update (e.g., 'mo').
        field_name: The argument name to update or add (e.g., 'position').
        new_value: The new value for the field.
        
    Returns:
        Dict with success status and message.
    """
    if not os.path.exists(scene_path):
        return {"success": False, "error": f"File not found: {scene_path}"}

    with open(scene_path, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"success": False, "error": f"Syntax error in scene file: {e}"}

    target_call = None
    target_keyword = None
    
    # Find the addObject call
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check if it is an addObject call
            is_add_object = False
            if isinstance(node.func, ast.Attribute) and node.func.attr == "addObject":
                is_add_object = True
            elif isinstance(node.func, ast.Name) and node.func.id == "addObject":
                is_add_object = True
            
            if is_add_object:
                # Check for name="object_name" in keywords
                for kw in node.keywords:
                    # Handle ast.Constant (Python 3.8+) and legacy types
                    val = None
                    if isinstance(kw.value, ast.Constant):
                        val = kw.value.value
                    elif isinstance(kw.value, ast.Str): # Python < 3.8
                        val = kw.value.s
                    
                    if kw.arg == "name" and val == object_name:
                        target_call = node
                        break
                
                if target_call:
                    # Check if field is already present
                    for kw in node.keywords:
                        if kw.arg == field_name:
                            target_keyword = kw
                            break
                    break
    
    if not target_call:
        return {"success": False, "error": f"Object '{object_name}' not found in {scene_path}"}

    # Prepare the new value string
    new_value_str = repr(new_value)
    
    lines = source.splitlines(keepends=True)
    def get_offset(lineno, col_offset):
        off = 0
        for i in range(lineno - 1):
            off += len(lines[i])
        off += col_offset
        return off

    # Perform replacement
    if target_keyword:
        # Replace existing value
        val_node = target_keyword.value
        
        start_offset = get_offset(val_node.lineno, val_node.col_offset)
        end_offset = get_offset(val_node.end_lineno, val_node.end_col_offset)
        
        new_source = source[:start_offset] + new_value_str + source[end_offset:]
        
    else:
        # Insert new keyword argument
        last_arg = None
        if target_call.keywords:
            last_arg = target_call.keywords[-1]
        elif target_call.args:
            last_arg = target_call.args[-1]
            
        if last_arg:
            end_offset = get_offset(last_arg.end_lineno, last_arg.end_col_offset)
            
            # Scan forward to see if there is a comma
            cursor = end_offset
            has_comma = False
            while cursor < len(source):
                char = source[cursor]
                if char.isspace():
                    cursor += 1
                    continue
                if char == ',':
                    has_comma = True
                    cursor += 1
                    break 
                if char == ')' or char == '#':
                    break 
                cursor += 1
            
            if has_comma:
                insert_pos = cursor
                prefix = " "
            else:
                insert_pos = end_offset
                prefix = ", "
            
            new_source = source[:insert_pos] + prefix + f"{field_name}={new_value_str}" + source[insert_pos:]
        else:
             # Fallback if no arguments found (unlikely for addObject)
             return {"success": False, "error": "Could not determine insertion point (no arguments found)."}

    # Write back
    with open(scene_path, "w", encoding="utf-8") as f:
        f.write(new_source)

    return {"success": True, "message": f"Updated {field_name} for object {object_name}"}