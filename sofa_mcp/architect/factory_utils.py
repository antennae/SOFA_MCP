from __future__ import annotations

import Sofa.Core
from typing import Any, List

def get_object_factory_instance() -> Any:
    """Return an ObjectFactory instance-like object.

    Some SOFA Python builds expose ObjectFactory as a singleton with getInstance();
    others expose a static/pybind type directly.
    """
    factory = Sofa.Core.ObjectFactory
    try:
        get_instance = getattr(factory, "getInstance", None)
        if callable(get_instance):
            return get_instance()
    except Exception:
        pass
    return factory

def extract_class_names_from_entries(entries: Any) -> List[str]:
    """Extract SOFA class names from ObjectFactory entries."""
    if entries is None:
        return []

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

        for attr in ("name", "shortName"):
            value = getattr(entry, attr, None)
            if value:
                names.append(str(value))
                break

    return names

def collect_component_names_from_factory(instance: Any) -> List[str]:
    """Collect registered class names from the SOFA ObjectFactory binding."""
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

    names = extract_class_names_from_entries(getattr(instance, "components", None))

    targets = getattr(instance, "targets", None)
    if isinstance(targets, (list, tuple, set, frozenset)) and hasattr(instance, "getComponentsFromTarget"):
        combined: List[str] = []
        for target in targets:
            try:
                combined.extend(
                    extract_class_names_from_entries(instance.getComponentsFromTarget(target))
                )
            except Exception:
                continue
        if combined:
            names.extend(combined)

    return sorted({str(n) for n in names if n})
