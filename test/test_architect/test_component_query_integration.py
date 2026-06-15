"""Real-SOFA integration tests for query_sofa_component. Require SofaPython3."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sofa_mcp.architect.component_query import (
    _get_class_entry_metadata,
    query_sofa_component,
)


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


class TestQueryBehavior(unittest.TestCase):
    def test_template_is_honored_rigid3d(self):
        r = query_sofa_component("PartialFixedProjectiveConstraint", template="Rigid3d")
        self.assertTrue(r["success"])
        self.assertEqual(r["introspection"], "full")
        self.assertEqual(r["template"], "Rigid3d")
        self.assertIn("6", r["data_fields"]["fixedDirections"]["type"])  # fixed_array<bool,6>

    def test_template_is_honored_vec3d(self):
        r = query_sofa_component("PartialFixedProjectiveConstraint", template="Vec3d")
        self.assertTrue(r["success"])
        self.assertIn("3", r["data_fields"]["fixedDirections"]["type"])  # fixed_array<bool,3>

    def test_templates_list_present(self):
        r = query_sofa_component("PartialFixedProjectiveConstraint", template="Vec3d")
        self.assertIn("Rigid3d", r["templates"])
        self.assertIn("Vec3d", r["templates"])
        self.assertTrue(r["plugin"])

    def test_universal_fields_stripped_by_default(self):
        r = query_sofa_component("MechanicalObject")
        self.assertTrue(r["success"])
        for f in ("printLog", "listening", "componentState", "tags", "bbox", "name"):
            self.assertNotIn(f, r["data_fields"])

    def test_universal_fields_included_on_request(self):
        r = query_sofa_component("MechanicalObject", include_universal=True)
        self.assertIn("printLog", r["data_fields"])

    def test_registered_but_not_instantiable_fallback(self):
        # BarycentricMapping requires a parent + child mechanical state pair the
        # scaffold does not provide, so it cannot be instantiated during introspection.
        r = query_sofa_component("BarycentricMapping")
        self.assertTrue(r["success"])            # NOT a false negative
        self.assertEqual(r["introspection"], "metadata_only")
        self.assertIsNone(r["data_fields"])
        self.assertIsNone(r["template"])  # schema uniform with the full path
        self.assertEqual(r["plugin"], "Sofa.Component.Mapping.Linear")
        self.assertNotIn("misspelled", str(r).lower())

    def test_unknown_class_is_failure(self):
        r = query_sofa_component("TotallyMadeUpComponentXYZ")
        self.assertFalse(r["success"])
        self.assertEqual(
            r["error"],
            "Could not create an instance of TotallyMadeUpComponentXYZ for inspection.",
        )


if __name__ == '__main__':
    unittest.main()
