import os
import unittest
from unittest.mock import MagicMock, patch
import sys

# Add the sofa_mcp path to the test
# This allows running the test script from the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sofa_mcp.architect.component_query import (
    query_sofa_component,
    search_sofa_components,
    get_plugin_for_component,
    _parse_replacements_from_error,
    _load_renames,
)




class TestComponentQuery(unittest.TestCase):

    @patch.dict('sys.modules', {'Sofa.Core': None})
    def test_sofa_core_not_found(self):
        """
        Test that an error is returned if Sofa.Core is not available.
        """
        result = query_sofa_component("SomeComponent")
        print(result)
        self.assertIn("error", result)


    @patch('sofa_mcp.architect.component_query.Sofa.Core')
    def test_component_not_found(self, mock_sofa_core):
        """
        Test that an error is returned if the component cannot be created.
        """
        mock_node = MagicMock()
        mock_sofa_core.Node.return_value = mock_node
        # Mock child node's addObject to return Exception
        mock_child = mock_node.addChild.return_value
        mock_child.addObject.side_effect = Exception("Component not found")

        result = query_sofa_component("NonExistentComponent")
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Could not create an instance of NonExistentComponent for inspection.")

    @patch('sofa_mcp.architect.component_query.Sofa.Core')
    def test_query_sofa_component_success(self, mock_sofa_core):
        """
        Test querying a component successfully.
        """
        # Mocking the SOFA component and its data fields
        mock_component = MagicMock()
        mock_component.getName.return_value = "MyComponent"
        mock_component.getClassName.return_value = "MyComponentClass"

        mock_data_field = MagicMock()
        mock_data_field.getName.return_value = "my_data"
        mock_data_field.getValueTypeString.return_value = "string"
        mock_data_field.getValue.return_value = "default_value"
        mock_data_field.getHelp.return_value = "A test data field."

        mock_component.getDataFields.return_value = [mock_data_field]
        mock_component.getLinks.return_value = []

        mock_node = MagicMock()
        mock_sofa_core.Node.return_value = mock_node
        # Mock child node's addObject to return the component
        mock_child = mock_node.addChild.return_value
        mock_child.addObject.return_value = mock_component

        # Call the function
        result = query_sofa_component("MyComponent")

        # Asserts
        self.assertNotIn("error", result)
        self.assertEqual(result["name"], "MyComponent")
        self.assertEqual(result["class_name"], "MyComponentClass")
        self.assertIn("my_data", result["data_fields"])
        self.assertEqual(result["data_fields"]["my_data"]["type"], "string")
        self.assertEqual(str(result["data_fields"]["my_data"]["value"]), "default_value")
        self.assertEqual(result["data_fields"]["my_data"]["help"], "A test data field.")

    @patch('sofa_mcp.architect.component_query.Sofa.Core')
    def test_generic_exception(self, mock_sofa_core):
        """
        Test the generic exception handler.
        """
        mock_sofa_core.Node.side_effect = Exception("A generic error.")

        result = query_sofa_component("SomeComponent")
        self.assertIn("error", result)
        self.assertEqual(result["error"], "An error occurred: A generic error.")


    @patch('sofa_mcp.architect.component_query.Sofa.Core')
    def test_search_sofa_components_success(self, mock_sofa_core):
        mock_factory_inst = MagicMock()
        mock_factory_inst.getClassNames.return_value = [
            "MechanicalObject",
            "EulerImplicitSolver",
            "TetrahedronSetTopologyContainer",
            "SparseLDLSolver",
        ]
        mock_sofa_core.ObjectFactory.getInstance.return_value = mock_factory_inst

        result = search_sofa_components("mech")
        self.assertNotIn("error", result)
        self.assertIn("MechanicalObject", result.get("matches", []))

        # Prefix mode
        result2 = search_sofa_components("Tetra*")
        self.assertIn("TetrahedronSetTopologyContainer", result2.get("matches", []))


    @patch('sofa_mcp.architect.component_query._try_get_registered_component_names')
    @patch('sofa_mcp.architect.plugin_cache.load_plugin_map')
    def test_search_sofa_components_unavailable(self, mock_load, mock_live):
        # Both the cache and the live-factory fallback return nothing →
        # search_sofa_components must surface an error rather than a
        # misleading empty match list.
        mock_load.return_value = {}
        mock_live.return_value = []
        result = search_sofa_components("anything")
        self.assertIn("error", result)

    @patch('sofa_mcp.architect.component_query.Sofa.Core')
    def test_query_with_context_and_template(self, mock_sofa_core):
        """
        Test that context_components and template are correctly used.
        """
        mock_node = MagicMock()
        mock_sofa_core.Node.return_value = mock_node
        mock_child = mock_node.addChild.return_value
        
        mock_component = MagicMock()
        mock_component.getName.return_value = "TestComp"
        mock_component.getClassName.return_value = "TestComp"
        mock_component.getDataFields.return_value = []
        mock_component.getLinks.return_value = []
        mock_child.addObject.return_value = mock_component

        context = [{"type": "HexahedronSetTopologyContainer", "name": "topo"}]
        result = query_sofa_component("TestComp", template="Vec3d", context_components=context)
        
        # Verify context components were added to root node
        mock_node.addObject.assert_any_call("HexahedronSetTopologyContainer", name="topo")
        
        # Verify target component was added to child node with template
        mock_child.addObject.assert_called_with("TestComp", template="Vec3d")
        
        self.assertTrue(result["success"])

    def test_parse_replacements_from_error(self):
        # Matches the shape of SOFA's actual retired-component error message.
        err = (
            "GenericConstraintSolver has been replaced since v25.12 by a set of new components, "
            "whose names relate to the method used:\n"
            "  - BlockGaussSeidelConstraintSolver (if you were using this component without setting 'resolutionMethod')\n"
            "  - UnbuiltGaussSeidelConstraintSolver (...)\n"
            "  - NNCGConstraintSolver (...)\n"
        )
        replacements = _parse_replacements_from_error(err)
        self.assertIn("BlockGaussSeidelConstraintSolver", replacements)
        self.assertIn("NNCGConstraintSolver", replacements)
        self.assertIn("UnbuiltGaussSeidelConstraintSolver", replacements)

    def test_parse_replacements_returns_empty_when_no_marker(self):
        # An ordinary error (no "replaced since") must not produce false positives.
        self.assertEqual(_parse_replacements_from_error("some other error"), [])

    def test_renames_json_loads(self):
        renames = _load_renames()
        self.assertIn("GenericConstraintSolver", renames)
        self.assertIn("BlockGaussSeidelConstraintSolver", renames["GenericConstraintSolver"])
        # The _comment key must be stripped.
        self.assertNotIn("_comment", renames)

    @patch('sofa_mcp.architect.component_query.Sofa.Core')
    @patch('sofa_mcp.architect.plugin_cache.load_plugin_map')
    @patch('sofa_mcp.architect.plugin_cache.get_cache_path')
    def test_get_plugin_for_component_returns_rename_hint(self, mock_cache_path, mock_load, mock_sofa_core):
        # Cache lookup misses, but our renames.json has GenericConstraintSolver.
        # Must return the structured dict shape, not the plain "not found" string.
        mock_cache_path.return_value = "/nonexistent/path.json"
        mock_load.return_value = {}
        # Factory probe will raise — no rename message in error, so _parse
        # returns []. Falls through to renames.json.
        mock_node = MagicMock()
        mock_node.addObject.side_effect = Exception("unrelated factory error")
        mock_sofa_core.Node.return_value = mock_node

        # Ensure get_cache_path() points at an existing dir so plugin_cache
        # doesn't try to regenerate. Use os.path.exists override via the
        # existing logic: if path doesn't exist, generate is called — mock it.
        with patch('sofa_mcp.architect.plugin_cache.generate_and_save_plugin_map'):
            with patch('os.path.exists', return_value=True):
                result = get_plugin_for_component("GenericConstraintSolver")

        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("renamed"))
        self.assertIn("BlockGaussSeidelConstraintSolver", result.get("suggested_replacements", []))

    @patch('sofa_mcp.architect.plugin_cache.load_plugin_map')
    def test_search_sofa_components_prepends_renamed_replacements(self, mock_load):
        # When the substring match would miss the modern replacements (e.g. a
        # `Generic` query), the renames map must add them via a separate field.
        mock_load.return_value = {
            "GenericConstraintCorrection": "Sofa.Component.Constraint.Lagrangian.Correction",
            "SerialPortBridgeGeneric": "SoftRobots",
        }
        result = search_sofa_components("Generic")
        self.assertIn("renamed_replacements", result)
        names = {r["name"] for r in result["renamed_replacements"]}
        self.assertIn("BlockGaussSeidelConstraintSolver", names)


if __name__ == '__main__':
    unittest.main()
