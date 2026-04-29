# Rule 1 — Plugins: deep review

**Date:** 2026-04-26
**Reviewer:** single-rule deep-review agent
**Rule under review:** "Every component class needs a corresponding `RequiredPlugin` (use `get_plugins_for_components` to resolve)."
**Verdict:** Rule confirmed valid. Significant silent-failure nuances documented below.

---

## 1. Mechanistic explanation

When `addObject("Foo")` is called on a SOFA Python binding and `Foo`'s plugin is not loaded, the C++ `ObjectFactory::createObject()` returns `nullptr` and records the error strings `"Object type Foo<> was not created"` and `"The component 'Foo' cannot be found in the factory."` in the `BaseObjectDescription` error list. The SofaPython3 binding (`Binding_Node.cpp:256-261`) then **raises a Python `ValueError`** from those strings — there is no silent continue at the Python API level. Scene construction aborts. This is the primary failure mode.

The secondary mode is the v20.12+ PLUGINIZE migration scenario (Agent 4 #10, Agent 9 F6): a scene runs inside `runSofa` or any host that pre-loads a broad set of plugins automatically (e.g., the Sofa.Component umbrella). In that context `addObject` succeeds because the plugin happened to be loaded already, but when moved to a clean environment (e.g., the `~/venv/bin/python` subprocess used by `scene_writer.py`) the same class is not found and the ValueError fires. This is the **silent-failure window**: the scene "works" for the author but breaks in isolated validation.

A third, subordinate mode: the `SceneCheckMissingRequiredPlugin` visitor (in the optional `SceneChecking` plugin, `SceneCheckMissingRequiredPlugin.cpp:52-103`) fires a `[WARNING]` message **post-init** listing plugins used but not declared. This fires only if the `SceneChecking` plugin was loaded before `init()`; it does not fire in the bare `~/venv/bin/python` subprocess unless explicitly loaded.

---

## 2. Core-builtin exemptions

Classes that do NOT require a `RequiredPlugin` because they are registered from `Sofa.Simulation.Core`, `Sofa.Simulation.Graph`, or `Sofa.Simulation.Common` — libraries that are always linked into any SOFA Python process:

| Class | Library | Cache status |
|---|---|---|
| `DefaultAnimationLoop` | `Sofa.Simulation.Core` | NOT IN CACHE |
| `RequiredPlugin` | `Sofa.Simulation.Core` | NOT IN CACHE |
| `Node` / node manipulation | `Sofa.Simulation.Graph` | NOT IN CACHE |
| `GenericConstraintSolver` | `Sofa.Component.Constraint.Lagrangian.Solver` (init.cpp intentionally omits its `registerObjects` call) | NOT IN CACHE |
| `DefaultContactManager` | Unknown (not found in component module .so scans) | NOT IN CACHE |
| `InfoComponent` | Core fallback placeholder | NOT IN CACHE |

**How to identify core-builtins operationally:** any class name absent from the plugin cache (`.sofa-component-plugin-map.json`) but successfully instantiable in a bare SOFA Python subprocess. The cache is built by scanning `.so` files in `$SOFA_ROOT/lib`; `Sofa.Simulation.*` `.so` files exist (`libSofa.Simulation.Core.so`) but their components are pre-linked into the Python interpreter and therefore their `registerObjects` calls run at process startup before any plugin diff is taken. The cache thus has a **systematic blind spot for simulation-core components**.

**Important exception:** `GenericConstraintSolver` is in `Sofa.Component.Constraint.Lagrangian.Solver` (confirmed by source path) but is **intentionally excluded from that module's `registerObjects()` call** (`init.cpp:57-64` lists only NNCGConstraintSolver, BlockGaussSeidel, UnbuiltGaussSeidel, LCP, ImprovedJacobi). It registers via some other mechanism or is effectively deprecated. Either way, it cannot be resolved by the plugin cache and should not be recommended. The v2.1 spec already drops it from the validated-class list.

---

## 3. `get_plugins_for_components` contract

**Implementation path:** `get_plugins_for_components` (component_query.py:290-298) calls `get_plugin_for_component` (line 254-287) for each deduplicated name. That function:

1. Ensures the cache JSON exists (generates on first call).
2. Looks up the name in the cache dict.
3. If found: calls `SofaRuntime.importPlugin(plugin_name)` (best-effort pre-load, ignores failure), returns the plugin name string.
4. If **not found**: returns the string `"Component not found in cache"`.

**Return value for unknown class names:** the string `"Component not found in cache"` — not `None`, not an exception, not an empty string. The caller must explicitly check for this sentinel.

**Return value for ambiguous names (class in multiple plugins):** not possible by construction. The cache generator uses `if component not in plugin_map: plugin_map[component] = plugin_name` (plugin_cache.py:144-146) — first-writer wins, no overwrite. A class that appears in two plugins is mapped only to the first one encountered in the scan order (SoftRobots < longer Sofa.Component.* names < shorter names). Ambiguity is silently resolved to one answer; no warning is emitted.

**Core-builtin names return `"Component not found in cache"`** — same sentinel as a genuinely unknown class. `summarize_scene`'s plugin checker must treat this return value as "exempt / no RequiredPlugin needed" rather than "error", for names that are known core-builtins.

---

## 4. Sample scenes

**Should-trigger (missing RequiredPlugin):**
No upstream scene in this repo deliberately omits a `RequiredPlugin`. However, the PLUGINIZE migration pattern (Agent 4 #10) means any pre-v20.12 scene file will trigger it. A minimal synthetic trigger:

```python
# BAD: uses CableActuator (SoftRobots.Inverse) without RequiredPlugin
def createScene(rootNode):
    rootNode.addObject("FreeMotionAnimationLoop")
    rootNode.addObject("NNCGConstraintSolver")          # needs Sofa.Component.Constraint.Lagrangian.Solver
    rootNode.addObject("CableActuator", name="cable")  # needs SoftRobots.Inverse — will ValueError
```

**Shouldn't-trigger (compliant scenes with RequiredPlugin):**

- `/home/sizhe/workspace/SOFA_MCP/archiv/cantilever_beam.py` — 11 `RequiredPlugin` declarations covering all used components (lines 9-19).
- `/home/sizhe/workspace/SOFA_MCP/archiv/tri_leg_cables.py` — 21 `RequiredPlugin` declarations (lines 7-27) including `SoftRobots` and `SoftRobots.Inverse`.

---

## 5. Silent-failure modes in detail

**Mode A — Pre-loaded-host masking (primary):** Scene works in `runSofa` (which auto-loads the Sofa.Component umbrella) but fails with ValueError in the `~/venv/bin/python` subprocess. This is the dominant real-world pattern (Agent 4 #10, Agent 9 F6, SoftRobots issues #150, #42, #229).

**Mode B — Cache miss for core-builtins:** `get_plugins_for_components` returns `"Component not found in cache"` for `DefaultAnimationLoop`, `RequiredPlugin`, `GenericConstraintSolver`. If the checker treats this as "missing plugin", it will false-positive on perfectly legal scenes. **The checker must allowlist this sentinel for classes that are known simulation-core.**

**Mode C — SceneChecking warning gated on plugin load:** The `[WARNING] This scene is using component defined in plugins but is not importing...` message only fires if the `SceneChecking` plugin was loaded. The v2.1 spec's `plugin_not_imported_warning` regex rule is correct to gate this: "only fires if `SceneChecking` plugin is loaded — subprocess wrapper should load it." Without explicit loading this warning never appears.

**Mode D — Cache ambiguity silence:** If a class is registered in two plugins (e.g., a SoftRobots component that was later upstreamed to Sofa.Component), the cache silently returns only one. The `RequiredPlugin` generated will still work, but may not be the minimal/canonical one.

---

## 6. Severity and message shape recommendation

**Severity:** `error` — not `warning`. Rationale: in the isolated `~/venv/bin/python` subprocess a missing RequiredPlugin raises a Python `ValueError` and the scene will not load at all. There is no "scene runs but behaves oddly" gray zone for this rule. The failure is hard and immediate.

Exception: if `get_plugins_for_components` returns `"Component not found in cache"` for a class that also does not appear in the SOFA source as a known core-builtin, severity should be `warning` with a note that the class may be unknown or from an unscanned plugin.

**Recommended `checks` entry shape:**

```python
{
    "rule": "rule_1_plugins",
    "severity": "error",
    "subject": "/",                  # or the node path where the component is declared
    "message": (
        "Component 'CableActuator' has no RequiredPlugin. "
        "Required plugin: 'SoftRobots.Inverse'. "
        "Without it the scene will raise ValueError in isolated execution."
    )
}
```

For unresolvable names (cache miss, not known core-builtin):

```python
{
    "rule": "rule_1_plugins",
    "severity": "warning",
    "subject": "/",
    "message": (
        "Component 'FooBar' not found in the plugin cache. "
        "It may be a typo, an unscanned plugin, or a custom component. "
        "Add a RequiredPlugin if 'FooBar' comes from an external library."
    )
}
```

---

## 7. Final rule wording (recommended)

> **Rule 1 — Plugins.**
> *Recommend:* one `RequiredPlugin` per distinct plugin needed by the scene's components. Use `get_plugins_for_components` to resolve. Omit `RequiredPlugin` for core-builtin classes (`DefaultAnimationLoop`, `RequiredPlugin` itself, `GenericConstraintSolver`, `DefaultContactManager`) which are always available in any SOFA Python process.
> *Validate:* every component class in the scene whose plugin cache lookup returns a non-empty string other than `"Component not found in cache"` must have a corresponding `RequiredPlugin` with that plugin name (or any name that loads the same `.so`).
> *Discovery escape:* if `get_plugins_for_components` returns `"Component not found in cache"`, emit `warning` rather than `error`; the component may be a custom class or from an unscanned plugin directory.

---

## 8. Confidence verdict

**High confidence** on the mechanistic explanation — directly verified in `Binding_Node.cpp:256-261` (ValueError throw) and `ObjectFactory.cpp:229-343` (nullptr + logError chain). **High confidence** on the core-builtin exemption list — confirmed `DefaultAnimationLoop` absent from cache and registered in `Sofa.Simulation.Core`; `GenericConstraintSolver` confirmed absent from module's `registerObjects()`. **Medium confidence** on `DefaultContactManager` exemption — absent from cache but source registration site not located in this review. **High confidence** on `get_plugins_for_components` contract — code read directly.
