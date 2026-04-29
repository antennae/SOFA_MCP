# Agent C — Direct C++ source verification of QP/inverse smell tests

**Date:** 2026-04-25
**Scope:** SoftRobots.Inverse C++ source verified directly from `/home/sizhe/workspace/sofa/plugins/SoftRobots.Inverse/`
**Method:** Read actual source files. No WebFetch. Agent 9's claims verified independently.

## Claim-by-claim verdicts

### 1. `printLog=True` emits `W`, `Q`, `A`, `Aeq`, `c`, `bu`, `bl`, `beq`, `l`, `u`, `dfree`, `delta`, `lambda`

**VERIFIED — with one structural clarification.**

- `QPInverseProblemSolver.cpp` lines 537–552: when `f_printLog.getValue()` is true, calls `displayQNormVariation()`, then `displayQPSystem()`, then `displayResult()`.
- `QPInverseProblem.cpp` `displayQPSystem()` (lines 275–431): emits a single `msg_info("QPInverseProblem")` stream containing labeled blocks — exact strings:
  - `" W      = ["`, `" Q      = ["`, `" A      = ["`, `" Aeq      = ["`, `" c      = ["`, `" bu      = ["`, `" bl      = ["`, `" beq      = ["`, `" l      = ["`, `" u      = ["`, `" dfree  = ["`
- `QPInverseProblem.cpp` `displayResult()` (lines 242–272): emits `msg_info("QPInverseProblem")` stream containing `" delta = ["` and `" lambda = ["`.

All fields are in one multi-line `msg_info` call per method — regex must match within a multi-line block.

One unconditional emit: `msg_info() << "computeCompliance in " << m_constraintsCorrections.size() << " constraintCorrections"` at line 412 fires on **every step regardless of `f_printLog`** — no guard around it.

### 2. `d_graph` is `Data<map<string, vector<SReal>>>` with keys `iterations` and `objective`

**WRONG on the key names.**

Type confirmed: `QPInverseProblemSolver.h` line 154: `sofa::Data<map<string, vector<SReal>>> d_graph;`

**Actual keys** populated each step (`QPInverseProblemSolver.cpp` lines 511–535):
- `"#Effectors:"` — effector row count
- `"#Actuators:"` — actuator row count
- `"#Equality:"` — equality row count
- `"#Contacts:"` — contact row count
- `"Last Objective:"` — current step objective (1-element vector, overwritten each step)
- `"Last Iterations:"` — current step iteration count (1-element vector, overwritten each step)

**Agent 9 said keys are `"iterations"` and `"objective"`. Both are WRONG.** Correct keys are `"Last Iterations:"` and `"Last Objective:"` (capital L, trailing colon). This is a breaking error if implemented literally.

Note: `d_graph` is cleared and repopulated each step — it is NOT a growing time-series array. Each key holds a 1-element vector with the current step's value.

### 3. `d_objective` is `Data<SReal>` (per-step scalar)

**VERIFIED.**

`QPInverseProblemSolver.h` line 157: `sofa::Data<SReal> d_objective;`
Written every step in `solveSystem()` line 531: `d_objective.setValue(objective);`
This is the cleaner programmatic source for `inverse_objective_not_decreasing` — read it after each `animate()` call.

### 4. `actuatorsOnly` Data field name

**VERIFIED. C++ member is `d_actuatorsOnly`; Python/Data name is `"actuatorsOnly"`.**

`QPInverseProblemSolver.h` line 153: `sofa::Data<bool> d_actuatorsOnly;`
Constructor line 141: `initData(&d_actuatorsOnly, false, "actuatorsOnly", ...)`. No `f_` prefix.

### 5. `d_displayTime=True` adds per-step build/solve/total-time numbers

**VERIFIED.**

Exact emit strings:
- `buildSystem()`: `msg_info() << "build system in " << N << " ms"`
- `solveSystem()`: `msg_info() << " TOTAL solve QP " << N << " ms"`
- `applyCorrection()`: `msg_info() << "TotalTime " << N << " ms"`

Data field Python name: `"displayTime"`.

### 6. Backend strings `"Using proxQP solver"` / `"Using qpOASES solver"` independent of `printLog`

**WRONG — they ARE gated by `msg_info()`.**

`QPInverseProblemSolver.cpp` lines 192 and 200:
```cpp
msg_info() << "Using proxQP solver";
msg_info() << "Using qpOASES solver";
```

`msg_info()` (no named component string) on a `BaseObject` subclass is suppressed when `f_printLog=false`. These are emitted only during `createProblems()`, called from `init()`. **If `printLog` is set post-construction (after init), these messages will have already been suppressed.** Agent 9 was wrong that they are independent of `printLog`.

**Implication:** To see the backend string, `printLog=True` must be set **before** `Sofa.Simulation.init()`. If set after init, backend detection via log scraping will fail. An alternative is to read `d_qpSolver.getValue().getSelectedId()` programmatically.

### 7. `"Relative variation of infinity norm through one step:"` is a real emit string

**VERIFIED — exact string confirmed.**

`QPInverseProblem.cpp` `displayQNormVariation()` lines 590–591:
```
" Relative variation of infinity norm through one step: " << varNorm << " %\n"
" Largest relative variation of infinity norm through one step: " << m_largestQNormVariation << " %\n\n"
```
Also emitted (lines 580–582, always when `displayQNormVariation` is called):
```
" Q infinity norm : " << norm << "\n"
" Previous infinity norm : " << prevNorm << "\n"
```

The value `varNorm` is expressed as a **percentage**. The first step is skipped due to `d_countdownFilterStartPerturb` (default 1).

**`q_norm_blowup` implementation:** regex `"Relative variation of infinity norm through one step: ([\d.]+) %"` — threshold of >1000 (= 10× change expressed as percentage) is appropriate.

### 8. `cable_negative_lambda` — can lambda go negative when `minForce=0`?

**PARTIALLY VERIFIED — negative lambda is possible ONLY when `minForce` is not set (or is set negative).**

`CableActuator.inl` `initLimit()` lines 147–154:
```cpp
if(d_minForce.isSet()) {
    m_hasLambdaMin = true;
    m_lambdaMin[0] = minForce;
}
if(!m_hasLambdaMin || m_lambdaMin[0]<0)
    msg_info(this) << "By not setting minForce=0 you are considering the cable as a stiff rod able to push.";
```

`ConstraintHandler::getConstraintOnLambda()` (lines 550–577) maps to QP bounds:
- `hasLambdaMin` AND `hasLambdaMax`: `l[i] = lambdaMin`, `u[i] = lambdaMax`
- Only `hasLambdaMin`: `l[i] = lambdaMin`, `u[i] = 1e99`
- Neither: `l[i] = -1e99`, `u[i] = 1e99`

**When `minForce` is not set: `m_hasLambdaMin=false`, QP bound is `l=-1e99` — negative lambda is fully allowed by the QP.** The cable can push.

**When `minForce=0`: `l[i]=0` — QP enforces lambda >= 0, negative lambda is mathematically impossible.**

The code itself explicitly warns about this at init time (the `msg_info` above). The smell test is valid and catches real misconfiguration. Fix in anomaly message: "Set `minForce=0` on `CableActuator` to enforce cable-only (tension) constraint."

## Per-smell-test verdicts

| Smell test | Verdict | Implementation notes |
|---|---|---|
| `actuator_lambda_zero` | **STRONG** | Parse `" lambda = ["` block from `displayResult()`. All zeros every step = actuator never engaged. Requires `printLog=True` before init. |
| `cable_negative_lambda` | **STRONG** (with scope annotation) | Fires only when `minForce` absent/negative. Still catches a critical real misconfiguration. Parse lambda block; filter to actuator rows. Message should prescribe `minForce=0`. |
| `q_norm_blowup` | **STRONG** | Exact string confirmed. Value is a percentage; threshold >1000% (= 10× variation per step). Skip step 0 (countdown suppresses first step). Requires `printLog=True`. |
| `inverse_objective_not_decreasing` | **CONDITIONAL** | Read `d_objective` (scalar) programmatically each step — no log scraping. Non-decreasing over multiple consecutive steps = infeasible target. Key name correction critical if using `d_graph`. |

## Recommended programmatic Data field reads

| Data field (C++) | Python name | Type | Purpose |
|---|---|---|---|
| `d_objective` | `"objective"` | `SReal` | Read after each `animate()` step for `inverse_objective_not_decreasing` |
| `d_graph` | `"info"` | `map<string, vector<SReal>>` | Keys: `"Last Objective:"`, `"Last Iterations:"`, `"#Actuators:"`, `"#Effectors:"`, `"#Equality:"`, `"#Contacts:"` |
| `d_actuatorsOnly` | `"actuatorsOnly"` | `bool` | Read at init for `scene_summary` |
| `d_allowSliding` | `"allowSliding"` | `bool` | Read at init for `scene_summary` |
| `d_qpSolver` | `"qpSolver"` | `OptionsGroup` | Read at init for backend detection (alternative to log scraping) |

## What Agent 9 got wrong (summary)

1. **`d_graph` key names wrong.** Said `"iterations"` and `"objective"`. Actual: `"Last Iterations:"` and `"Last Objective:"`. Breaking error.
2. **Backend strings are NOT independent of `printLog`.** Both use `msg_info()` which is suppressed when `f_printLog=false`. They emit only at init — setting `printLog` post-construction misses them.
3. **`cable_negative_lambda` nuance.** Source is unambiguous: `minForce=0` sets `l[i]=0` in the QP — negative lambda is **mathematically impossible** when properly set. The smell test fires only when `minForce` is absent.
4. **`d_graph` is not a growing time-series.** Each key is cleared and overwritten with a 1-element vector each step. Not a trajectory array. Reading it at run-end gives only the last step's value per key.
5. **`computeCompliance` emit is unconditional** (line 412, no `f_printLog` guard) — appears every step regardless of log settings.
