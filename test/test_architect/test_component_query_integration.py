"""Real-SOFA integration tests for query_sofa_component. Require SofaPython3."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sofa_mcp.architect.component_query import _get_class_entry_metadata


class TestClassEntryMetadata(unittest.TestCase):
    def test_metadata_for_multitemplate_class(self):
        md = _get_class_entry_metadata("PartialFixedProjectiveConstraint")
        self.assertIsNotNone(md)
        self.assertIn("Rigid3d", md["templates"])
        self.assertIn("Vec3d", md["templates"])
        self.assertTrue(md["plugin"])  # plugin name resolved from cache
        self.assertTrue(md["source_header"].endswith(".h"))

    def test_metadata_for_unknown_is_none_or_empty_templates(self):
        md = _get_class_entry_metadata("NotARealComponentXYZ")
        # Either None (factory raised) or a dict with no templates.
        self.assertTrue(md is None or not md.get("templates"))


if __name__ == '__main__':
    unittest.main()
