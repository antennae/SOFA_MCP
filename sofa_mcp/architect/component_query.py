
from __future__ import annotations

from typing import Any, Dict, List

import re
import types

import Sofa.Core


_AUTO_IMPORTED_PLUGINS = False


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

    # Keep this list small; more can be loaded explicitly by the user scene.
    for plugin_name in (
        "Sofa.Component.Topology",
        "Sofa.Component.IO.Mesh",
        "Sofa.Component.LinearSolver",
        "Sofa.Component.ODESolver",
        "Sofa.Component.StateContainer",
        "Sofa.Component.Mapping",
        "Sofa.Component.Mass",
    ):
        try:
            SofaRuntime.importPlugin(plugin_name)
        except Exception:
            pass

    _AUTO_IMPORTED_PLUGINS = True


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
            instance = factory.getInstance() if hasattr(factory, "getInstance") else factory
            for method_name in (
                "getClassNames",
                "getAllObjectClassNames",
                "getRegisteredObjectNames",
                "getObjectClassNames",
            ):
                if hasattr(instance, method_name):
                    names = getattr(instance, method_name)()
                    if names:
                        return [str(n) for n in names]

            # Common in recent SOFA builds: a list of ClassEntry objects.
            names = _extract_class_names_from_entries(getattr(instance, "components", None))
            if names:
                # Some builds only have a tiny default registry until component
                # libraries are explicitly imported. If the list is suspiciously
                # small, try a best-effort auto-import and re-read.
                if len(names) >= 50:
                    return names

                _maybe_auto_import_component_plugins(core)
                refreshed = _extract_class_names_from_entries(getattr(instance, "components", None))
                if refreshed and len(refreshed) >= len(names):
                    names = refreshed

                if len(names) >= 50:
                    return names

            # Some builds expose components per-target.
            targets = getattr(instance, "targets", None)
            if isinstance(targets, (list, tuple, set)) and hasattr(instance, "getComponentsFromTarget"):
                combined: List[str] = []
                for target in targets:
                    try:
                        combined.extend(
                            _extract_class_names_from_entries(instance.getComponentsFromTarget(target))
                        )
                    except Exception:
                        continue
                if combined:
                    if len(combined) >= 50:
                        return combined

                    _maybe_auto_import_component_plugins(core)
                    refreshed_combined: List[str] = []
                    for target in targets:
                        try:
                            refreshed_combined.extend(
                                _extract_class_names_from_entries(instance.getComponentsFromTarget(target))
                            )
                        except Exception:
                            continue

                    if refreshed_combined and len(refreshed_combined) >= len(combined):
                        combined = refreshed_combined

                    if len(combined) >= 50:
                        return combined

                    # Even if still small, return what we have.
                    return combined
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

    # As a last resort, try importing a minimal set of component libraries and retry.
    _maybe_auto_import_component_plugins(core)

    try:
        factory = getattr(core, "ObjectFactory", None)
        if factory is None:
            return []
        instance = factory.getInstance() if hasattr(factory, "getInstance") else factory
        names = _extract_class_names_from_entries(getattr(instance, "components", None))
        if names:
            return names

        targets = getattr(instance, "targets", None)
        if isinstance(targets, (list, tuple, set)) and hasattr(instance, "getComponentsFromTarget"):
            combined: List[str] = []
            for target in targets:
                try:
                    combined.extend(_extract_class_names_from_entries(instance.getComponentsFromTarget(target)))
                except Exception:
                    continue
            if combined:
                return combined
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
