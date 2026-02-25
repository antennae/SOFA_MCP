from __future__ import annotations

from typing import Any, Dict, List

import os
import re
import types

import Sofa.Core
from . import factory_utils


_AUTO_IMPORTED_PLUGINS = False
_MIN_COMPONENT_REGISTRY_SIZE = 50


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

    # --- Start of new cache generation logic ---
    from . import plugin_cache
    if not os.path.exists(plugin_cache.get_cache_path()):
        try:
            plugin_cache.generate_and_save_plugin_map()
        except Exception:
            # If cache generation fails, we can continue without it.
            pass
    # --- End of new cache generation logic ---

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


def query_sofa_component(component_name: str, template: str = None, context_components: list[dict] = None) -> dict:
    """
    Queries the SOFA component registry for a component and returns its
    data fields, default values, and Python bindings.

    Args:
        component_name: Name of the SOFA component class.
        template: Optional template (e.g., 'Vec3d', 'Rigid3d') to use.
        context_components: Optional list of components to add to the context node
            before creating the target component. Each dict should have a 'type'
            key and optional data field keys.
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
        
        if context_components:
            for comp in context_components:
                c_type = comp.get("type")
                if not c_type:
                    continue
                kwargs = {k: v for k, v in comp.items() if k != "type"}
                try:
                    root.addObject(c_type, **kwargs)
                except Exception as e:
                    # First attempt failed, check for a missing plugin.
                    err_msg = str(e)
                    p_match = re.search(r"<RequiredPlugin name=[\"']([^\"']+)[\"']/>", err_msg)
                    if p_match:
                        try:
                            plugin_name = p_match.group(1)
                            SofaRuntime.importPlugin(plugin_name)
                            # Retry adding the component now that plugin is loaded.
                            root.addObject(c_type, **kwargs)
                        except:
                            # If it still fails, we pass and let the main component query fail,
                            # which will provide better diagnostics to the user.
                            pass
        else:
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

        res = try_create(child, component_name, template=template)
        
        # 2. Diagnose failure and attempt specific repairs
        if res is None or isinstance(res, Exception):
            err_msg = str(res) if res is not None else f"addObject('{component_name}') returned None"
            
            # Case A: Missing Plugin
            plugin_match = re.search(r"<RequiredPlugin name='([^']+)'/>", err_msg)
            if plugin_match:
                plugin_name = plugin_match.group(1)
                try:
                    SofaRuntime.importPlugin(plugin_name)
                    res = try_create(child, component_name, template=template) # Retry
                except:
                    pass

            # Case B: Still failing with template/context error
            if res is None or isinstance(res, Exception):
                err_text = str(res) if res is not None else ""
                if "template" in err_text.lower() or "mstate" in err_text.lower() or "topology" in err_text.lower() or res is None:
                    # Try forcing a common template if not already specified
                    if not template:
                        res = try_create(child, component_name, template="Vec3d")

        # If it still failed, return the error with hints
        if res is None or isinstance(res, Exception):
            error_text = str(res) if res is not None else "Unknown error (addObject returned None)"
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



def get_plugin_for_component(component_name: str, context_components: list[dict] = None) -> str:
    """
    Finds the required SOFA plugin for a single component name using the generated cache.
    It ensures the cache is generated on the first run.
    """
    try:
        from . import plugin_cache

        # 1. Ensure the cache is built.
        cache_path = plugin_cache.get_cache_path()
        if not os.path.exists(cache_path):
            plugin_cache.generate_and_save_plugin_map()

        # 2. Load the map and perform the lookup. This is the single source of truth.
        plugin_map = plugin_cache.load_plugin_map()

        if component_name in plugin_map:
            # Check if the plugin is already loaded in the current context.
            # This is a bit of a heuristic. We try to add a dummy component from the plugin.
            # If it succeeds without error, we can say "Already Loaded".
            try:
                import SofaRuntime
                plugin_name = plugin_map[component_name]
                SofaRuntime.importPlugin(plugin_name)
                return plugin_name
            except Exception:
                 # If import fails, we return the name from cache.
                 return plugin_map[component_name]
        
        # If not in the cache, it's not found.
        return "Component not found in cache"

    except Exception as e:
        return f"Error during plugin query: {e}"


def get_plugins_for_components(component_names: list[str], context_components: list[dict] = None) -> dict[str, str]:
    """
    For a list of SOFA component names, returns a mapping to their required plugins.
    """
    results = {}
    # De-duplicate to avoid redundant checks
    for name in sorted(list(set(component_names))):
        results[name] = get_plugin_for_component(name, context_components=context_components)
    
    return results


def _try_get_registered_component_names() -> List[str]:

    """Best-effort retrieval of registered SOFA component class names.

    SOFA Python bindings vary between builds; this probes a few common APIs.
    """

    core = getattr(Sofa, "Core", None)
    if core is None:
        return []

    # Attempt ObjectFactory-based discovery.
    factory_class = getattr(core, "ObjectFactory", None)
    if factory_class is not None:
        try:
            instance = factory_utils.get_object_factory_instance()
            names = factory_utils.collect_component_names_from_factory(instance)
            if len(names) >= _MIN_COMPONENT_REGISTRY_SIZE:
                return names

            # Some builds only have a tiny default registry until component
            # libraries are explicitly imported. Try a best-effort import and retry.
            _maybe_auto_import_component_plugins(core)
            refreshed = factory_utils.collect_component_names_from_factory(instance)
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
    """Searches SOFA's registered components by a fuzzy query using the generated cache."""

    try:
        from . import plugin_cache
        names = list(plugin_cache.load_plugin_map().keys())
        
        if not names:
            # Fallback to the old method if the cache is empty for some reason
            names = _try_get_registered_component_names()

        if not names:
            return {
                "error": "Component search is not available. The plugin cache might be empty and the live factory is not responsive.",
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
