
import Sofa.Core


def query_sofa_component(component_name: str) -> dict:
    """
    Queries the SOFA component registry for a component and returns its
    data fields, default values, and Python bindings.
    """
    try:
        # In SOFA, components are often created within a node.
        # We may not be able to get all info without a running simulation,
        # but we can try to inspect the class.
        # The following is a conceptual implementation.
        # The actual SOFA API might differ.

        # This is a placeholder for where you'd use the SOFA API
        # to get component information.
        # For example, if Sofa.Core had a component registry:
        # if not Sofa.Core.has_component(component_name):
        #     return {"error": f"Component '{component_name}' not found."}
        
        # The ability to inspect data fields without a running scene depends on the
        # SOFA Python3 bindings. A common way is to create a temporary node and object.
        
        root = Sofa.Core.Node("rootNode")
        component = root.addObject(component_name)
        
        if not component:
            return {"error": f"Could not create an instance of {component_name}."}

        data_fields = {}
        for data in component.getDataFields():
            data_fields[data.getName()] = {
                "type": data.getValueTypeString(),
                "value": str(data.getValue()),
                "help": data.getHelp(),
            }

        return {
            "name": component.getName(),
            "class_name": component.getClassName(),
            "data_fields": data_fields,
        }

    except ImportError:
        return {"error": "Sofa.Core not found. Make sure your environment is sourced correctly."}
    except Exception as e:
        return {"error": f"An error occurred: {e}"}
