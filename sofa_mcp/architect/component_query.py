from __future__ import annotations

from typing import Any, Dict, List

import os
import re
import types

import Sofa.Core


_AUTO_IMPORTED_PLUGINS = False
_MIN_COMPONENT_REGISTRY_SIZE = 50


def _get_object_factory_instance(factory: Any) -> Any:
    """Return an ObjectFactory instance-like object.

    Some SOFA Python builds expose ObjectFactory as a singleton with getInstance();
    others expose a static/pybind type directly. This helper avoids peppering the
    codebase with fragile hasattr(..., "getInstance") checks.
    """

    try:
        get_instance = getattr(factory, "getInstance", None)
        if callable(get_instance):
            return get_instance()
    except Exception:
        pass
    return factory


def _extract_class_names_from_entries(entries: Any) -> List[str]:
    """Extract SOFA class names from ObjectFactory entries.

    In some SOFA Python builds, the object factory exposes a list of ClassEntry
    objects via `ObjectFactory.components` or `getComponentsFromTarget()`.
    """

    if entries is None:
        return []

    # Keep this conservative to avoid iterating over MagicMock-like objects in tests.
    if not isinstance(entries, (list, tuple, set)):
        return []

    names: List[str] = []
    for entry in entries:
        if isinstance(entry, str):
            names.append(entry)
            continue

        class_name = getattr(entry, "className", None)
        if class_name:
            names.append(str(class_name))
            continue

        # Fallbacks for other potential shapes.
        for attr in ("name", "shortName"):
            value = getattr(entry, attr, None)
            if value:
                names.append(str(value))
                break

    return names


def _maybe_auto_import_component_plugins(core: Any) -> None:
    """Best-effort: import a minimal set of component libraries to populate the registry.

    This is only attempted in real SOFA environments (not mocked tests) and is
    idempotent.
    """

    global _AUTO_IMPORTED_PLUGINS
    if _AUTO_IMPORTED_PLUGINS:
        return

    # Avoid side effects when Sofa.Core is mocked (e.g., unittest MagicMock).
    if not isinstance(core, types.ModuleType):
        _AUTO_IMPORTED_PLUGINS = True
        return

    try:
        import SofaRuntime  # type: ignore
    except Exception:
        _AUTO_IMPORTED_PLUGINS = True
        return

    def discover_plugins_from_sofa_root() -> List[str]:
        sofa_root = os.environ.get("SOFA_ROOT")
        if not sofa_root:
            return []

        lib_dirs = [os.path.join(sofa_root, "lib"), os.path.join(sofa_root, "build", "lib")]
        plugins: set[str] = set()
        for lib_dir in lib_dirs:
            if not os.path.isdir(lib_dir):
                continue
            try:
                for filename in os.listdir(lib_dir):
                    # Prefer unversioned .so files; those map cleanly to importPlugin names.
                    if not (filename.startswith("lib") and filename.endswith(".so")):
                        continue
                    plugins.add(filename[len("lib") : -len(".so")])
            except Exception:
                continue

        return sorted(plugins)

    discovered = discover_plugins_from_sofa_root()

    # Import all available Sofa.Component.* modules (and the umbrella module, if present)
    # so component search can cover the full build rather than a tiny default registry.
    plugin_names: List[str] = []
    if "Sofa.Component" in discovered:
        plugin_names.append("Sofa.Component")

    plugin_names.extend([p for p in discovered if p.startswith("Sofa.Component.")])

    # Also import popular external plugins if they are built.
    plugin_names.extend([p for p in discovered if p.startswith("SoftRobots")])

    # Allow user to force-add plugins via env var (comma-separated names).
    extra = os.environ.get("SOFA_MCP_AUTOIMPORT_PLUGINS", "").strip()
    if extra:
        plugin_names.extend([p.strip() for p in extra.split(",") if p.strip()])

    # De-dupe while preserving order.
    seen: set[str] = set()
    ordered_plugins: List[str] = []
    for p in plugin_names:
        if p in seen:
            continue
        seen.add(p)
        ordered_plugins.append(p)

    for plugin_name in ordered_plugins:
        try:
            SofaRuntime.importPlugin(plugin_name)
        except Exception:
            pass

    _AUTO_IMPORTED_PLUGINS = True


def _collect_component_names_from_factory(instance: Any) -> List[str]:
    """Collect registered class names from the SOFA ObjectFactory binding."""

    # Prefer explicit name enumeration if present.
    for method_name in (
        "getClassNames",
        "getAllObjectClassNames",
        "getRegisteredObjectNames",
        "getObjectClassNames",
    ):
        try:
            method = getattr(instance, method_name, None)
            if callable(method):
                names = method()
                if names:
                    return [str(n) for n in names]
        except Exception:
            continue

    # Common in recent SOFA builds: ObjectFactory.components -> List[ClassEntry].
    names = _extract_class_names_from_entries(getattr(instance, "components", None))

    # Some builds also expose components per target.
    targets = getattr(instance, "targets", None)
    if isinstance(targets, (list, tuple, set, frozenset)) and hasattr(instance, "getComponentsFromTarget"):
        combined: List[str] = []
        for target in targets:
            try:
                combined.extend(
                    _extract_class_names_from_entries(instance.getComponentsFromTarget(target))
                )
            except Exception:
                continue
        if combined:
            names.extend(combined)

    # De-dupe while preserving deterministic ordering.
    return sorted({str(n) for n in names if n})


def query_sofa_component(component_name: str) -> dict:
    """
    Queries the SOFA component registry for a component and returns its
    data fields, default values, and Python bindings.
    """
    try:
        import SofaRuntime
        
        # Ensure common base plugins are loaded so we can build a valid context
        base_plugins = [
            "Sofa.Component.StateContainer",
            "Sofa.Component.Topology.Container.Constant",
            "Sofa.Component.Topology.Container.Dynamic",
            "Sofa.Component.Visual",
            "Sofa.GL.Component.Rendering3D"
        ]
        for p in base_plugins:
            try:
                SofaRuntime.importPlugin(p)
            except:
                pass

        # 1. Prepare a dummy context with common dependencies
        root = Sofa.Core.Node("registryQueryNode")
        root.addObject("MechanicalObject", template="Vec3d", name="dummy_mstate")
        # Add a few common topology containers
        root.addObject("TetrahedronSetTopologyContainer", name="dummy_tet_topology")
        root.addObject("TriangleSetTopologyContainer", name="dummy_tri_topology")
        
        # We use a child node for the target component so it can definitely see 
        # siblings/parents for link resolution.
        child = root.addChild("targetNode")
        
        def try_create(node, name, template=None):
            try:
                if template:
                    return node.addObject(name, template=template)
                return node.addObject(name)
            except Exception as e:
                return e

        res = try_create(child, component_name)
        
        # 2. Diagnose failure and attempt specific repairs
        if isinstance(res, Exception):
            err_msg = str(res)
            
            # Case A: Missing Plugin
            plugin_match = re.search(r"<RequiredPlugin name='([^']+)'/>", err_msg)
            if plugin_match:
                plugin_name = plugin_match.group(1)
                try:
                    SofaRuntime.importPlugin(plugin_name)
                    res = try_create(child, component_name) # Retry
                except:
                    pass

            # Case B: Still failing with template/context error
            if isinstance(res, Exception) and ("template" in str(res).lower() or "mstate" in str(res).lower() or "topology" in str(res).lower()):
                # Try forcing a common template
                res = try_create(child, component_name, template="Vec3d")

        # If it still failed, return the error with hints
        if isinstance(res, Exception):
            error_text = str(res)
            hints = []
            if "mstate" in error_text.lower():
                hints.append("This component requires a MechanicalObject (mstate) in its context.")
            if "topology" in error_text.lower():
                hints.append("This component requires a TopologyContainer (e.g. TetrahedronSetTopologyContainer).")
            if "factory" in error_text.lower() and "plugin" not in error_text.lower():
                hints.append("The component name might be misspelled or the plugin is not loaded.")
            
            return {
                "error": f"Could not create an instance of {component_name} for inspection.",
                "details": error_text,
                "hints": hints,
                "success": False
            }

        component = res
        data_fields = {}
        for data in component.getDataFields():
            data_fields[data.getName()] = {
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
            
            links.append({
                "name": link.getName(),
                "help": str(link.getHelp()),
                "is_multi": is_multi
            })

        return {
            "name": component.getName(),
            "class_name": component.getClassName(),
            "data_fields": data_fields,
            "links": links,
            "success": True
        }

    except ImportError:
        return {"error": "Sofa.Core not found. Make sure your environment is sourced correctly."}
    except Exception as e:
        return {"error": f"An error occurred: {e}"}


def _try_get_registered_component_names() -> List[str]:
    """Best-effort retrieval of registered SOFA component class names.

    SOFA Python bindings vary between builds; this probes a few common APIs.
    """

    core = getattr(Sofa, "Core", None)
    if core is None:
        return []

    # Attempt ObjectFactory-based discovery.
    factory = getattr(core, "ObjectFactory", None)
    if factory is not None:
        try:
            instance = _get_object_factory_instance(factory)
            names = _collect_component_names_from_factory(instance)
            if len(names) >= _MIN_COMPONENT_REGISTRY_SIZE:
                return names

            # Some builds only have a tiny default registry until component
            # libraries are explicitly imported. Try a best-effort import and retry.
            _maybe_auto_import_component_plugins(core)
            refreshed = _collect_component_names_from_factory(instance)
            if len(refreshed) >= _MIN_COMPONENT_REGISTRY_SIZE:
                return refreshed
            if refreshed:
                return refreshed
        except Exception:
            pass

    # Attempt runtime-based discovery if present.
    runtime = getattr(Sofa, "Runtime", None)
    if runtime is not None:
        try:
            for method_name in ("getComponents", "getComponentList", "getAvailableComponents"):
                if hasattr(runtime, method_name):
                    names = getattr(runtime, method_name)()
                    if names:
                        return [str(n) for n in names]
        except Exception:
            pass

    return []


def search_sofa_components(query: str, limit: int = 50) -> Dict[str, Any]:
    """Searches SOFA's registered components by a fuzzy query.

    - If `query` ends with '*', performs a prefix match (case-insensitive).
    - Otherwise performs a substring match (case-insensitive).
    - For multi-token queries, all tokens must appear in the name.
    """

    try:
        names = _try_get_registered_component_names()
        if not names:
            return {
                "error": "Component search is not available in this SOFA Python build. Provide an exact class name and use query_sofa_component instead.",
            }

        raw_query = (query or "").strip()
        if not raw_query:
            return {
                "error": "query must be a non-empty string",
            }

        prefix_mode = raw_query.endswith("*")
        q = raw_query[:-1] if prefix_mode else raw_query
        q = q.strip().lower()

        # Tokenize on non-alphanumeric boundaries to support queries like
        # "tet topology" or "rigid3".
        tokens = [t for t in re.split(r"[^a-zA-Z0-9]+", q) if t]
        if not tokens:
            return {
                "error": "query must contain at least one alphanumeric character",
            }

        def match(name: str) -> bool:
            n = name.lower()
            if prefix_mode:
                return any(n.startswith(t) for t in tokens) if len(tokens) == 1 else all(t in n for t in tokens)
            return all(t in n for t in tokens)

        deduped = sorted({str(n) for n in names})
        matches = [n for n in deduped if match(n)]

        return {
            "query": raw_query,
            "limit": int(limit),
            "count": len(matches[: int(limit)]),
            "matches": matches[: int(limit)],
        }

    except ImportError:
        return {"error": "Sofa.Core not found. Make sure your environment is sourced correctly."}
    except Exception as e:
        return {"error": f"An error occurred: {e}"}
