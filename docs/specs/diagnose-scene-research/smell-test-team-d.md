# Agent D — §6.B smell test verification

**Date:** 2026-04-25. Source-grep only, no scene execution. Directories searched: `/home/sizhe/workspace/sofa/src/`, `/home/sizhe/workspace/sofa/plugins/SoftRobots/`, `/home/sizhe/workspace/sofa/plugins/SoftRobots.Inverse/`

## D1 — `factory_or_intersector_warning`

**Status: VERIFIED — all three sub-patterns found, mixed levels**

**Sub-pattern 1** `Element Intersector .* NOT FOUND`
- `src/Sofa/framework/Core/src/sofa/core/collision/Intersection.cpp:96`
- Level: `msg_warning("IntersectorMap")`
- Exact: `"Element Intersector " << gettypename(t1) << "-" << gettypename(t2) << " NOT FOUND within :" << tmp.str()`

**Sub-pattern 2** `Object type .* was not created`
- `src/Sofa/framework/Core/src/sofa/core/ObjectFactory.cpp:232`
- `arg->logError("Object type " + classname + "<" + templatename + "> was not created")`
- `logError()` buffers into `BaseObjectDescription::errors`; flushed as `msg_error()` in `ObjectElement.cpp:85` and `SimpleApi.cpp:108`. **Emitted level: `[ERROR]`**

**Sub-pattern 3** `cannot be found in the factory`
- `src/Sofa/framework/Core/src/sofa/core/ObjectFactory.cpp:240`
- `arg->logError("The component '" + classname + "' cannot be found in the factory.")`
- Same `logError()` → `msg_error()` path. **Emitted level: `[ERROR]`**

**Recommended regex:** `Element Intersector .* NOT FOUND|Object type .* was not created|cannot be found in the factory`

**Severity: `error`**

## D2 — `qp_infeasible_in_log`

**Status: VERIFIED at both `msg_warning` and `msg_error`**

Four emit sites:

`plugins/SoftRobots.Inverse/src/.../QPInverseProblemQPOases.cpp:96`
```cpp
msg_warning("QPInverseProblemImpl") << "QP infeasible at time = " << m_time << " with " << ... << " contacts, check constraint on actuators.";
```
Line 106: `msg_warning` — `"QP infeasible at time = ... , try with option HST_INDEF."`

Line 116: `msg_error` — `"QP infeasible at time = ..., iteration = ..., and final nWSR = ..."`

`plugins/SoftRobots.Inverse/src/.../LCPQPSolverQPOases.cpp:109`
```cpp
msg_warning("LCPQPSolver") << "QP infeasible.";
```

**Recommended regex:** `QP infeasible`

**Severity: `error`** (escalates to `msg_error` on final failure)

## D3 — `broken_link_string`

**Status: WRONG — `'0000000000000000'` pattern does not appear in any upstream SOFA `msg_*` call**

The actual link-failure messages in SOFA are:

`src/Sofa/framework/Core/src/sofa/core/objectmodel/Base.cpp:579`
```cpp
msg_warning() << "Link update failed for " << link->getName() << " = " << link->getValueString();
```

`src/Sofa/framework/Core/src/sofa/core/objectmodel/BaseLink.cpp:379/383`
```cpp
msg_error("BaseLink (" + getName() + ")") << "Could not read link from '" << pathname << "'";
```

The `'0000000000000000'` string from GitHub issue #5579 is a **Python-side repr artifact** — pybind11's default `__repr__` of a null/dangling C++ object pointer, printed when user Python code inspects the object. It is not emitted by SOFA's `msg_*` infrastructure.

**Recommended replacement regex:** `Link update failed for .+ = @|Could not read link from`

**Severity: `warning`**

## D4 — `pybind_numpy_warning`

**Status: VERIFIED WITH WORDING DRIFT RISK**

`src/Sofa/framework/Core/src/sofa/core/objectmodel/Base.cpp:475`
```cpp
if( !(dataVec[d]->read( value )) && !value.empty())
{
    msg_warning() << "Could not read value for data field " << attribute << ": " << value;
}
```
Level: `msg_warning`

When numpy passes `np.float64(1.0)` as a Python value, pybind11 serializes it as the string `"np.float64(1.0)"` which SOFA fails to parse and prints as the `value`. The `np.float64` substring therefore appears in the `value` portion.

**Drift risk:** NumPy 2.0 (June 2024) changed some repr formatting. The repr may become `numpy.float64` in some contexts. Also applies to `np.float32`, `np.int32`, etc.

**Recommended regex:** `Could not read value for data field .* np\.float\d+|Could not read value for data field .* numpy\.`

**Severity: `warning`**

## D5 — `plugin_not_imported_warning`

**Status: VERIFIED at `msg_warning` level — with subprocess caveat**

`src/applications/projects/SceneChecking/src/SceneChecking/SceneCheckMissingRequiredPlugin.cpp:99`
```cpp
msg_warning(this->getName())
    << "This scene is using component defined in plugins but is not importing the required plugins." << msgendl
```
Level: `msg_warning`

**Caveat:** This check runs inside `SceneCheckerListener::rightAfterLoadingScene()`, which fires only when the `SceneChecking` plugin is loaded. If the `diagnose_scene` subprocess does not load SceneChecking, this warning is never emitted. The subprocess wrapper must either load the plugin explicitly or this smell test should note it is conditional.

**Recommended regex:** `This scene is using component defined in plugins but is not importing`

**Severity: `warning`**

## D6 — `auto_lcp_constraint_solver_warning`

**Status: WRONG CLASS NAME — auto-created class is `BlockGaussSeidelConstraintSolver`, not `LCPConstraintSolver`**

`src/Sofa/Component/AnimationLoop/src/sofa/component/animationloop/FreeMotionAnimationLoop.cpp:107-117`
```cpp
if (const auto constraintSolver = sofa::core::objectmodel::New<
    constraint::lagrangian::solver::BlockGaussSeidelConstraintSolver>())
{
    ...
    msg_warning() << "A ConstraintSolver is required by " << this->getClassName()
        << " but has not been found: a default "
        << constraintSolver->getClassName()
        << " is automatically added in the scene for you. ..."
}
```
Level: `msg_warning`

Agent 7 #4 correctly identified the phenomenon, but the SOFA docs it read ("an `LCPConstraintSolver` is automatically created") are **stale** — the current code creates `BlockGaussSeidelConstraintSolver`. Any regex matching `LCPConstraintSolver` in this message will never fire on this build.

**Recommended regex:** `A ConstraintSolver is required by .* but has not been found`

**Severity: `warning`**

## WARN-level catch-all fallback (v2 review M6)

SOFA's message formatter is fully uniform and stable:

`src/Sofa/framework/Helper/src/sofa/helper/logging/MessageFormatter.cpp:39-42`
```cpp
case Message::Warning : return "[WARNING] ";
case Message::Error   : return "[ERROR]   ";
case Message::Fatal   : return "[FATAL]   ";
```

Format per `DefaultStyleMessageFormatter.h:41`:
`[ERROR] ClassName(instanceName): message text`

**Recommended catch-all pattern:**
```python
SOFA_WARN_OR_ABOVE = re.compile(r'^\[(WARNING|ERROR|FATAL)\]')
```

Use this as a final §6.B smell test: any line matching this pattern that was not already caught by D1–D6 should be surfaced as an `info`-level anomaly with the raw line text, allowing the LLM agent to inspect unfamiliar warnings without false positives blocking the report.

## Updated §6.B severity table

| Rule | Status | Source level | §6.B severity | Recommended regex |
|---|---|---|---|---|
| `factory_or_intersector_warning` | VERIFIED | `[WARNING]`/`[ERROR]` | `error` | `Element Intersector .* NOT FOUND\|Object type .* was not created\|cannot be found in the factory` |
| `qp_infeasible_in_log` | VERIFIED | `[WARNING]`→`[ERROR]` | `error` | `QP infeasible` |
| `broken_link_string` | WRONG | no such SOFA emit | `warning` | Replace: `Link update failed for .+ = @\|Could not read link from` |
| `pybind_numpy_warning` | VERIFIED (drift risk) | `[WARNING]` | `warning` | `Could not read value for data field .* np\.float\d+` |
| `plugin_not_imported_warning` | VERIFIED (SceneChecking must be loaded) | `[WARNING]` | `warning` | `This scene is using component defined in plugins but is not importing` |
| `auto_lcp_constraint_solver_warning` | WRONG CLASS NAME | `[WARNING]` | `warning` | `A ConstraintSolver is required by .* but has not been found` |

## Summary of required spec fixes

1. **D3:** Replace `'0+'` regex entirely. The `'0000000000000000'` string is a Python/pybind repr artifact, not a SOFA `msg_*` emit. Use `Link update failed for .+ = @|Could not read link from` instead.
2. **D6:** The SOFA docs cited by Agent 7 are stale. Current code auto-creates `BlockGaussSeidelConstraintSolver`, not `LCPConstraintSolver`. Update the smell test description and use the regex `A ConstraintSolver is required by .* but has not been found`.
3. **D5 subprocess caveat:** Add a note that `plugin_not_imported_warning` requires the `SceneChecking` plugin to be loaded in the diagnose subprocess.
4. **D4 drift:** Widen the numpy regex to cover `numpy.float64` (NumPy 2.x repr changes).
5. **Catch-all:** Add `^\[(WARNING|ERROR|FATAL)\]` as a universal fallback to surface any `msg_warning`/`msg_error`/`msg_fatal` not caught by D1–D6.
