import os
import unittest
from unittest.mock import MagicMock, patch
import sys

# Add the sofa_mcp path to the test
# This allows running the test script from the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sofa_mcp.architect.component_query import query_sofa_component




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
        mock_node.addObject.return_value = None

        result = query_sofa_component("NonExistentComponent")
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Could not create an instance of NonExistentComponent.")

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

        mock_node = MagicMock()
        mock_sofa_core.Node.return_value = mock_node
        mock_node.addObject.return_value = mock_component

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

if __name__ == '__main__':
    unittest.main()
