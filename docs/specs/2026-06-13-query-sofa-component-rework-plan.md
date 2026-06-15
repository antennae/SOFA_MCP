# `query_sofa_component` rework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `query_sofa_component` honor `template` correctly, expose the registered template list + factory metadata, strip universal `BaseObject` fields by default, and return useful metadata (instead of a misleading "could not create" error) when a registered class can't be instantiated.

**Architecture:** Keep instantiate-to-introspect as the source of `data_fields`/`links` (no reflection path exists for Data schema), but (a) build the dummy scaffold's `MechanicalObject` to match the requested template so per-template Data shapes are correct, and (b) layer instantiation-independent `Sofa.Core.ObjectFactory` `ClassEntry` metadata on top — which also turns a failed instantiation into a useful partial answer.

**Tech Stack:** Python, SofaPython3 (`Sofa.Core`, `SofaRuntime`), FastMCP, `pytest`/`unittest`. Run all commands with `~/venv/bin/python` (bare `python` is not on PATH).

**Spec:** `docs/specs/2026-06-13-query-sofa-component-rework.md`

---

## Verified facts (from 2026-06-13 probing — do not re-derive)

- `Sofa.Core.ObjectFactory.getComponent(name)` returns a `ClassEntry` with attributes `templates` (a `set`), `defaultTemplate` (`str`, may be `''`), `targets` (`set` of plugin names), `description` (`str`), `locations` (`set` of header paths). **No Data-field schema.**
- `ClassEntry.templates` is **empty until the registering plugin is loaded.** The plugin name comes from `plugin_cache.load_plugin_map()`.
- A template-matched scaffold makes shapes correct: `PartialFixedProjectiveConstraint` with a `Rigid3d` mstate → `fixedDirections` type `fixed_array<bool,6>`; with `Vec3d` → `fixed_array<bool,3>`. A **mismatched** scaffold silently degrades (SOFA logs *"Requested template 'Rigid3d' is not compatible... Falling back to ... Vec3d"*) and returns the wrong shape — this is the 5-20 bug.
- Putting both a tet and a tri topology container in one node emits a benign *"Only one Topology is permitted in a Node"* warning. **Irrelevant here** — we read Data schema via `getDataFields()` and never call `init()`/simulate. This matches the pre-existing scaffold behavior.
- A live component's actual template is read via `component.getTemplateName()` (returns e.g. `'Rigid3d'`). `getData("templateName")` returns `None` — do **not** use it.
- Baseline: `~/venv/bin/python -m pytest test/test_architect/test_component_query.py -q` → 12 passed.

## File structure

- **Modify** `sofa_mcp/architect/component_query.py` — add `_UNIVERSAL_DATA_FIELDS`, `_SCAFFOLD_POSITIONS`, `_scaffold_template_for`, `_build_scaffold`, `_get_class_entry_metadata`; rewrite `query_sofa_component`.
- **Modify** `sofa_mcp/server.py:222-225` — add `include_universal` param to the tool wrapper + docstring.
- **Modify** `test/test_architect/test_component_query.py` — keep mocked tests green; add pure-helper unit tests.
- **Create** `test/test_architect/test_component_query_integration.py` — real-SOFA behavior tests.
- **Modify** `skills/sofa-mcp/sofa-mcp/SKILL.md`, `README.md` — doc the template round-trip + `introspection` field.

## Response shape (target)

Full success:
```json
{
  "name": "...", "class_name": "PartialFixedProjectiveConstraint", "template": "Rigid3d",
  "templates": ["Rigid2d","Rigid3d","Vec1d","Vec2d","Vec3d","Vec6d"],
  "default_template": null, "plugin": "Sofa.Component.Constraint.Projective",
  "description": "...", "source_header": "/.../PartialFixedProjectiveConstraint.h",
  "data_fields": {"fixedDirections": {"type":"fixed_array<bool,6>","value":"...","help":"..."}, ...},
  "links": [...], "introspection": "full", "success": true
}
```
Registered but not instantiable: `success: true`, `introspection: "metadata_only"`, `data_fields: null`, `links: null`, `note`, plus the metadata fields.
Unknown class: unchanged — `success: false`, `error: "Could not create an instance of <name> for inspection."`, `hints`, optional `suggested_replacements`.

---

### Task 1: Pure helpers — template-family resolution + module constants

**Files:**
- Modify: `sofa_mcp/architect/component_query.py` (add constants + `_scaffold_template_for` near the top-level helpers, after `_REPLACEMENT_BULLET_RE`)
- Test: `test/test_architect/test_component_query.py`

- [ ] **Step 1: Write the failing test**

Add to `test/test_architect/test_component_query.py` — extend the import on line 10-16 to include `_scaffold_template_for`, then add this test method to `TestComponentQuery`:

```python
    def test_scaffold_template_for(self):
        from sofa_mcp.architect.component_query import _scaffold_template_for
        self.assertEqual(_scaffold_template_for("Rigid3d"), "Rigid3d")
        self.assertEqual(_scaffold_template_for("Rigid3"), "Rigid3d")   # missing 'd' suffix
        self.assertEqual(_scaffold_template_for("Rigid2d"), "Rigid2d")
        self.assertEqual(_scaffold_template_for("Vec3d"), "Vec3d")
        self.assertEqual(_scaffold_template_for("Vec1d"), "Vec1d")
        self.assertEqual(_scaffold_template_for("Vec6"), "Vec6d")
        self.assertEqual(_scaffold_template_for(None), "Vec3d")          # default
        self.assertEqual(_scaffold_template_for("UnknownTemplate"), "Vec3d")
        self.assertEqual(_scaffold_template_for("Rigid"), "Rigid3d")     # bare rigid → 3d
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/venv/bin/python -m pytest test/test_architect/test_component_query.py::TestComponentQuery::test_scaffold_template_for -v`
Expected: FAIL — `ImportError: cannot import name '_scaffold_template_for'`.

- [ ] **Step 3: Write minimal implementation**

In `sofa_mcp/architect/component_query.py`, after the `_REPLACEMENT_BULLET_RE`/`_parse_replacements_from_error` block (around line 70), add:

```python
# BaseObject Data fields present on every component — constant noise. Stripped
# from `data_fields` by default; `include_universal=True` keeps them.
_UNIVERSAL_DATA_FIELDS = frozenset(
    {"name", "printLog", "tags", "bbox", "componentState", "listening"}
)

# Template family → (mstate template, 4-point position array). 4 points keep the
# tet/tri topology indices [0..3] valid. We never call init(), so the topology is
# only there so topology-dependent components can construct.
_SCAFFOLD_POSITIONS = {
    "Vec1d": [[0.0], [1.0], [2.0], [3.0]],
    "Vec2d": [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
    "Vec3d": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    "Vec6d": [[0.0, 0, 0, 0, 0, 0], [1.0, 0, 0, 0, 0, 0],
              [0, 1.0, 0, 0, 0, 0], [0, 0, 1.0, 0, 0, 0]],
    "Rigid3d": [[0, 0, 0, 0, 0, 0, 1.0], [1.0, 0, 0, 0, 0, 0, 1.0],
                [0, 1.0, 0, 0, 0, 0, 1.0], [0, 0, 1.0, 0, 0, 0, 1.0]],
    "Rigid2d": [[0.0, 0, 0], [1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]],
}


def _scaffold_template_for(template: Optional[str]) -> str:
    """Map a requested SOFA template to the scaffold mstate template key.

    Handles exact keys (`Vec3d`), the missing-`d` form (`Vec3`, `Rigid3`), and
    falls back to `Vec3d` for anything unrecognized (bare `Rigid` → `Rigid3d`)."""
    if not template:
        return "Vec3d"
    t = str(template)
    for key in _SCAFFOLD_POSITIONS:
        if t == key or t == key[:-1]:  # "Rigid3" matches "Rigid3d"
            return key
    if t.startswith("Rigid2"):
        return "Rigid2d"
    if t.startswith("Rigid"):
        return "Rigid3d"
    return "Vec3d"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/venv/bin/python -m pytest test/test_architect/test_component_query.py::TestComponentQuery::test_scaffold_template_for -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sofa_mcp/architect/component_query.py test/test_architect/test_component_query.py
git commit -m "feat(query): add template-family resolver and scaffold constants"
```

---

### Task 2: ClassEntry metadata helper + template-matched scaffold builder

**Files:**
- Modify: `sofa_mcp/architect/component_query.py` (add `_build_scaffold`, `_get_class_entry_metadata` after the helpers from Task 1)
- Test: `test/test_architect/test_component_query_integration.py` (new)

- [ ] **Step 1: Write the failing test**

Create `test/test_architect/test_component_query_integration.py`. These run against real SOFA (the dev env has it; consistent with `test_summarize_rules.py`).

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/venv/bin/python -m pytest test/test_architect/test_component_query_integration.py -v`
Expected: FAIL — `ImportError: cannot import name '_get_class_entry_metadata'`.

- [ ] **Step 3: Write minimal implementation**

In `sofa_mcp/architect/component_query.py`, add after the Task 1 helpers:

```python
def _build_scaffold(root: Any, template: Optional[str]) -> None:
    """Add a template-matched MechanicalObject + tet/tri topology to `root`.

    The mstate template is chosen so per-template Data shapes come out correct
    (a Vec3d mstate silently degrades a Rigid3d request). The dual topology
    triggers a benign 'one Topology per Node' warning — harmless because we
    never call init()."""
    key = _scaffold_template_for(template)
    root.addObject("MechanicalObject", template=key, name="dummy_mstate",
                   position=_SCAFFOLD_POSITIONS[key])
    root.addObject("TetrahedronSetTopologyContainer", name="dummy_tet_topology",
                   tetrahedra=[[0, 1, 2, 3]])
    root.addObject("TriangleSetTopologyContainer", name="dummy_tri_topology",
                   triangles=[[0, 1, 2], [0, 2, 3], [0, 3, 1], [1, 3, 2]])


def _get_class_entry_metadata(component_name: str) -> Optional[Dict[str, Any]]:
    """Read instantiation-independent metadata from the ObjectFactory ClassEntry.

    Loads the registering plugin first (ClassEntry.templates only populates after
    load). Returns None when unavailable (e.g. Sofa.Core mocked in unit tests, or
    the factory raised)."""
    try:
        from . import plugin_cache
        plugin = None
        try:
            plugin = plugin_cache.load_plugin_map().get(component_name)
        except Exception:
            plugin = None
        if plugin:
            try:
                import SofaRuntime
                SofaRuntime.importPlugin(plugin)
            except Exception:
                pass
        ce = Sofa.Core.ObjectFactory.getComponent(component_name)
        templates = sorted(str(t) for t in ce.templates)  # raises if ce is a mock
        default_template = str(ce.defaultTemplate) or None
        locations = [str(p) for p in ce.locations]
        description = str(ce.description).strip() or None
        return {
            "templates": templates,
            "default_template": default_template,
            "plugin": plugin,
            "description": description,
            "source_header": locations[0] if locations else None,
        }
    except Exception:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `~/venv/bin/python -m pytest test/test_architect/test_component_query_integration.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add sofa_mcp/architect/component_query.py test/test_architect/test_component_query_integration.py
git commit -m "feat(query): add ClassEntry metadata helper and scaffold builder"
```

---

### Task 3: Rewrite `query_sofa_component` to use the helpers

**Files:**
- Modify: `sofa_mcp/architect/component_query.py:184-377` (the `query_sofa_component` body)
- Test: `test/test_architect/test_component_query_integration.py`

- [ ] **Step 1: Write the failing tests**

Append to `test/test_architect/test_component_query_integration.py`:

```python
from sofa_mcp.architect.component_query import query_sofa_component


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
        # SurfacePressureConstraint needs wired topology/links the scaffold lacks.
        r = query_sofa_component("SurfacePressureConstraint")
        self.assertTrue(r["success"])            # NOT a false negative
        self.assertEqual(r["introspection"], "metadata_only")
        self.assertIsNone(r["data_fields"])
        self.assertEqual(r["plugin"], "SoftRobots")
        self.assertNotIn("misspelled", str(r).lower())

    def test_unknown_class_is_failure(self):
        r = query_sofa_component("TotallyMadeUpComponentXYZ")
        self.assertFalse(r["success"])
        self.assertEqual(
            r["error"],
            "Could not create an instance of TotallyMadeUpComponentXYZ for inspection.",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/venv/bin/python -m pytest test/test_architect/test_component_query_integration.py::TestQueryBehavior -v`
Expected: FAIL — `KeyError: 'introspection'` and the Rigid3d test getting `bool,3` (the current scaffold degrades Rigid3d to Vec3d), and `query_sofa_component` has no `include_universal` kwarg (`TypeError`).

- [ ] **Step 3: Write the implementation**

Replace the entire `query_sofa_component` function (`sofa_mcp/architect/component_query.py:184-377`) with:

```python
def query_sofa_component(
    component_name: str,
    template: str = None,
    context_components: list[dict] = None,
    include_universal: bool = False,
) -> dict:
    """
    Queries the SOFA component registry for a component and returns its data
    fields, default values, Python bindings, and factory metadata (templates,
    plugin, source header).

    Args:
        component_name: Name of the SOFA component class.
        template: Optional template (e.g. 'Vec3d', 'Rigid3d'). The introspection
            scaffold is built to match, so per-template Data shapes are correct.
        context_components: Optional list of components to add to the context node
            before creating the target. Each dict has a 'type' key + data fields.
        include_universal: Include the 6 universal BaseObject Data fields
            (name, printLog, tags, bbox, componentState, listening). Default False.
    """
    try:
        import SofaRuntime

        base_plugins = [
            "Sofa.Component.StateContainer",
            "Sofa.Component.Topology.Container.Constant",
            "Sofa.Component.Topology.Container.Dynamic",
            "Sofa.Component.Visual",
            "Sofa.GL.Component.Rendering3D",
        ]
        for p in base_plugins:
            try:
                SofaRuntime.importPlugin(p)
            except Exception:
                pass

        # Factory metadata also loads the registering plugin, which helps the
        # instantiation below succeed and populates ClassEntry.templates.
        metadata = _get_class_entry_metadata(component_name)

        root = Sofa.Core.Node("registryQueryNode")

        if context_components:
            for comp in context_components:
                c_type = comp.get("type")
                if not c_type:
                    continue
                kwargs = {k: v for k, v in comp.items() if k != "type"}
                try:
                    root.addObject(c_type, **kwargs)
                except Exception as e:
                    p_match = re.search(r"<RequiredPlugin name=[\"']([^\"']+)[\"']/>", str(e))
                    if p_match:
                        try:
                            SofaRuntime.importPlugin(p_match.group(1))
                            root.addObject(c_type, **kwargs)
                        except Exception:
                            pass
        else:
            effective = template or (metadata.get("default_template") if metadata else None)
            _build_scaffold(root, effective)

        child = root.addChild("targetNode")

        def try_create(node, name, tmpl=None):
            try:
                if tmpl:
                    return node.addObject(name, template=tmpl)
                return node.addObject(name)
            except Exception as e:
                return e

        res = try_create(child, component_name, tmpl=template)

        # Diagnose failure and attempt specific repairs.
        if res is None or isinstance(res, Exception):
            err_msg = str(res) if res is not None else f"addObject('{component_name}') returned None"
            plugin_match = re.search(r"<RequiredPlugin name='([^']+)'/>", err_msg)
            if plugin_match:
                try:
                    SofaRuntime.importPlugin(plugin_match.group(1))
                    res = try_create(child, component_name, tmpl=template)
                except Exception:
                    pass
            if res is None or isinstance(res, Exception):
                err_text = str(res) if res is not None else ""
                if ("template" in err_text.lower() or "mstate" in err_text.lower()
                        or "topology" in err_text.lower() or res is None):
                    if not template:
                        res = try_create(child, component_name, tmpl="Vec3d")

        # Still failing: registered → metadata-only success; else → unknown error.
        if res is None or isinstance(res, Exception):
            error_text = str(res) if res is not None else "Unknown error (addObject returned None)"
            is_registered, plugin = _is_registered_component(component_name)

            if is_registered:
                resp: Dict[str, Any] = {
                    "class_name": component_name,
                    "data_fields": None,
                    "links": None,
                    "introspection": "metadata_only",
                    "note": (
                        f"{component_name} is registered but could not be instantiated in the "
                        "introspection scaffold, so its Data fields are unknown. The class exists "
                        "and the listed templates are valid. For field-level schema, write a "
                        "candidate scene and run write_and_test_scene."
                    ),
                    "success": True,
                }
                if metadata:
                    for k in ("templates", "default_template", "plugin", "description", "source_header"):
                        resp[k] = metadata[k]
                else:
                    resp["plugin"] = plugin
                return resp

            # Truly unknown — keep the existing error contract.
            replacements = _parse_replacements_from_error(error_text)
            renames_map = _load_renames()
            if not replacements and component_name in renames_map:
                replacements = list(renames_map[component_name])

            hints: List[str] = []
            if "mstate" in error_text.lower():
                hints.append("This component requires a MechanicalObject (mstate) in its context.")
            if "topology" in error_text.lower():
                hints.append("This component requires a TopologyContainer (e.g. TetrahedronSetTopologyContainer).")
            if "factory" in error_text.lower() and "plugin" not in error_text.lower():
                hints.append("The component name might be misspelled or the plugin is not loaded.")
            if replacements:
                hints.append(f"SOFA suggests replacements for `{component_name}`: {', '.join(replacements)}.")

            response: Dict[str, Any] = {
                "error": f"Could not create an instance of {component_name} for inspection.",
                "details": error_text,
                "hints": hints,
                "success": False,
            }
            if replacements:
                response["suggested_replacements"] = replacements
            return response

        # Success.
        component = res
        data_fields = {}
        for data in component.getDataFields():
            fname = data.getName()
            if not include_universal and fname in _UNIVERSAL_DATA_FIELDS:
                continue
            data_fields[fname] = {
                "type": data.getValueTypeString(),
                "value": str(data.getValue()),
                "help": str(data.getHelp()),
            }

        links = []
        for link in component.getLinks():
            is_multi = False
            if hasattr(link, "isMultiLink"):
                prop = getattr(link, "isMultiLink")
                is_multi = prop() if callable(prop) else bool(prop)
            links.append({"name": link.getName(), "help": str(link.getHelp()), "is_multi": is_multi})

        actual_template = None
        try:
            tn = component.getTemplateName()
            actual_template = tn if isinstance(tn, str) else None
        except Exception:
            actual_template = None

        response = {
            "name": component.getName(),
            "class_name": component.getClassName(),
            "template": actual_template or (str(template) if template else None),
            "data_fields": data_fields,
            "links": links,
            "introspection": "full",
            "success": True,
        }
        if metadata:
            for k in ("templates", "default_template", "plugin", "description", "source_header"):
                response[k] = metadata[k]
        return response

    except ImportError:
        return {"error": "Sofa.Core not found. Make sure your environment is sourced correctly."}
    except Exception as e:
        return {"error": f"An error occurred: {e}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/venv/bin/python -m pytest test/test_architect/test_component_query_integration.py -v`
Expected: PASS (all of `TestQueryBehavior` + `TestClassEntryMetadata`).

- [ ] **Step 5: Commit**

```bash
git add sofa_mcp/architect/component_query.py test/test_architect/test_component_query_integration.py
git commit -m "feat(query): honor template, expose templates/metadata, metadata fallback"
```

---

> ## 🚩 MILESTONE GATE 1 — stop and verify with the user
>
> Core behavior is shipped and the integration suite is green. **Stop here and check in before docs/cleanup.**
>
> - **Regression net (automated):** `~/venv/bin/python -m pytest test/test_architect/test_component_query_integration.py -v` is green.
> - **Manual rubric (user eyeballs real output):** paste the actual response of
>   `query_sofa_component("PartialFixedProjectiveConstraint", template="Rigid3d")` and
>   `query_sofa_component("SurfacePressureConstraint")` so the user can confirm the shape/wording reads well to a consuming agent.
>
> Do not proceed to Task 4 until the user confirms.

---

### Task 4: Keep mocked unit tests green

**Files:**
- Modify: `test/test_architect/test_component_query.py`

- [ ] **Step 1: Run the existing mocked suite against the new code**

Run: `~/venv/bin/python -m pytest test/test_architect/test_component_query.py -v`
Expected: most pass; investigate any failure. Likely-safe: the new fields are additive and `_get_class_entry_metadata` returns `None` under the mock (`sorted(ce.templates)` raises on a `MagicMock`). The success/not-found/context tests assert only on pre-existing keys.

- [ ] **Step 2: Add a mocked assertion that universal fields are stripped**

Add to `TestComponentQuery` in `test/test_architect/test_component_query.py`:

```python
    @patch('sofa_mcp.architect.component_query.Sofa.Core')
    def test_universal_fields_stripped_mocked(self, mock_sofa_core):
        def mk(name):
            d = MagicMock()
            d.getName.return_value = name
            d.getValueTypeString.return_value = "string"
            d.getValue.return_value = "v"
            d.getHelp.return_value = "h"
            return d
        comp = MagicMock()
        comp.getName.return_value = "C"
        comp.getClassName.return_value = "C"
        comp.getTemplateName.return_value = "Vec3d"
        comp.getDataFields.return_value = [mk("printLog"), mk("youngModulus")]
        comp.getLinks.return_value = []
        node = MagicMock()
        mock_sofa_core.Node.return_value = node
        node.addChild.return_value.addObject.return_value = comp

        r = query_sofa_component("C")
        self.assertNotIn("printLog", r["data_fields"])
        self.assertIn("youngModulus", r["data_fields"])
        self.assertEqual(r["introspection"], "full")

        r2 = query_sofa_component("C", include_universal=True)
        self.assertIn("printLog", r2["data_fields"])
```

- [ ] **Step 3: Run the full mocked suite**

Run: `~/venv/bin/python -m pytest test/test_architect/test_component_query.py -v`
Expected: PASS (13 original-style + new). If `test_component_not_found` or `test_query_with_context_and_template` fail, the cause is the new code path; fix by ensuring `_get_class_entry_metadata` swallows mock errors (it should — verify the `sorted(...)` call is inside the `try`).

- [ ] **Step 4: Commit**

```bash
git add test/test_architect/test_component_query.py
git commit -m "test(query): cover universal-field stripping; keep mocked suite green"
```

---

### Task 5: Update the server tool wrapper

**Files:**
- Modify: `sofa_mcp/server.py:222-225`

- [ ] **Step 1: Update the wrapper signature + docstring**

Replace `sofa_mcp/server.py:222-225` with:

```python
@mcp.tool()
def query_sofa_component(
    component_name: str,
    template: str = None,
    context_components: list[dict] = None,
    include_universal: bool = False,
) -> dict:
    """Queries the SOFA component registry for a component.

    Honors `template` (the introspection scaffold is built to match, so a
    `Rigid3d` request returns Rigid3d-shaped Data fields, not a silent Vec3d
    fallback). Returns `templates`, `plugin`, `description`, `source_header`, and
    an `introspection` field (`"full"` or `"metadata_only"`). When a registered
    class can't be instantiated in the scaffold, returns `success: true` with
    `introspection: "metadata_only"` and `data_fields: null` — not a misleading
    "not found" error. Set `include_universal=True` to keep the 6 universal
    BaseObject Data fields (name, printLog, tags, bbox, componentState, listening).
    """
    return component_query.query_sofa_component(
        component_name,
        template=template,
        context_components=context_components,
        include_universal=include_universal,
    )
```

- [ ] **Step 2: Verify the server module imports cleanly**

Run: `~/venv/bin/python -c "import sofa_mcp.server"`
Expected: no traceback (imports succeed).

- [ ] **Step 3: Commit**

```bash
git add sofa_mcp/server.py
git commit -m "feat(server): expose include_universal; document template-aware query"
```

---

### Task 6: Documentation

**Files:**
- Modify: `skills/sofa-mcp/sofa-mcp/SKILL.md`
- Modify: `README.md:56`

- [ ] **Step 1: SKILL.md — note the template round-trip**

In `skills/sofa-mcp/sofa-mcp/SKILL.md`, in the "Workflow: natural language → validated scene" step 3 (`query_sofa_component`), append one tight sentence:

```markdown
   For template-dependent classes, the response's `templates` list shows every registered template; re-query with `template="Rigid3d"` to get that template's exact Data shapes (e.g. `fixedDirections` is `bool,6` for `Rigid3d` vs `bool,3` for `Vec3d`). A registered class that can't be introspected returns `introspection: "metadata_only"` with `data_fields: null` — it still exists; write a candidate scene + `write_and_test_scene` for field schema.
```

- [ ] **Step 2: README.md — mention template-awareness in the tool table**

In `README.md`, change the Component lookup row (line 56) Purpose cell to:

```markdown
| Component lookup | `query_sofa_component`, `search_sofa_components`, `get_plugins_for_components` | Find components in the registry; resolve their plugins. `query_sofa_component` is template-aware and returns the registered template list + source header. |
```

- [ ] **Step 3: Verify docs render (no broken tables)**

Run: `~/venv/bin/python -c "import pathlib; t=pathlib.Path('README.md').read_text(); assert 'template-aware' in t"`
Expected: no error.

- [ ] **Step 4: Full regression run**

Run: `~/venv/bin/python -m pytest test/test_architect/ -q`
Expected: all pass (mocked + integration).

- [ ] **Step 5: Commit**

```bash
git add skills/sofa-mcp/sofa-mcp/SKILL.md README.md
git commit -m "docs(query): document template-awareness and metadata_only fallback"
```

---

## Self-review (completed)

- **Spec coverage:** #1 honor template → Task 3 (`_build_scaffold` matched mstate) + Task 1 resolver; #2 templates/metadata → Task 2 + Task 3 response merge; #3 strip universal → Task 3 + `include_universal` Task 5; #4 metadata fallback → Task 3 `is_registered` branch. Testing → Tasks 2-4. Docs → Tasks 5-6. All spec sections mapped.
- **Placeholder scan:** no TBD/TODO; every code step has full code; every test has assertions.
- **Type consistency:** helper names (`_scaffold_template_for`, `_build_scaffold`, `_get_class_entry_metadata`, `_UNIVERSAL_DATA_FIELDS`, `_SCAFFOLD_POSITIONS`) and response keys (`introspection`, `templates`, `default_template`, `source_header`) are identical across all tasks. `try_create`'s kwarg renamed `template`→`tmpl` to avoid shadowing the outer `template` param — used consistently in Task 3.
- **Contract preservation:** the unknown-class path keeps the exact error string `"Could not create an instance of <name> for inspection."` (asserted by the pre-existing `test_component_not_found` and the new `test_unknown_class_is_failure`).
