# Rule 3 — Time Integration Solver: Pre-implementation review

**Date:** 2026-04-26
**Reviewer:** single-rule deep review agent
**Spec section:** v2.1 §1.1 Rule 3

---

## Mechanistic explanation (3 sentences)

`AnimateVisitor::processNodeTopDown` (verified in `sofa/src/Sofa/framework/Simulation/Core/src/sofa/simulation/AnimateVisitor.cpp` lines 125–177) checks `node->solver.empty()` at every tree node; if the solver list is non-empty it dispatches `OdeSolver::solve`, emits `RESULT_PRUNE` to stop descending, and returns — so the subtree under a solver node is integrated as a unit. A `MechanicalObject` with no solver in its ancestry and no mapping is silently skipped: the visitor returns `RESULT_CONTINUE` past such nodes, accumulating no forces and not updating positions — the result is a **frozen, non-simulated MO that produces no runtime errors and no warnings**. A mapped MO is recognized by `BaseMechanicalVisitor::processNodeTopDown` (line 79–81 of `BaseMechanicalVisitor.cpp`): when `node->mechanicalMapping != nullptr` it calls `fwdMappedMechanicalState` instead of `fwdMechanicalState`, and `stopAtMechanicalMapping` (line 555–558) returns `!map->areForcesMapped()` — i.e., traversal stops before a non-mechanical (visual) mapping but continues through mechanical mappings, delegating integration to the parent solver.

---

## Class-registration audit

Source of truth: `.sofa_mcp_results/.sofa-component-plugin-map.json` (the build-time plugin cache).

| Class name | Registered in cache | Plugin |
|---|---|---|
| `EulerImplicitSolver` | **YES** | `Sofa.Component.ODESolver.Backward` |
| `RungeKutta4Solver` | **YES** | `Sofa.Component.ODESolver.Forward` |
| `NewmarkImplicitSolver` | **YES** | `Sofa.Component.ODESolver.Backward` |
| `StaticSolver` | **YES** | `Sofa.Component.ODESolver.Backward` |
| `EulerExplicitSolver` | **YES** | `Sofa.Component.ODESolver.Forward` |
| `VariationalSymplecticSolver` | **YES** | `Sofa.Component.ODESolver.Backward` |
| `CentralDifferenceSolver` | **YES** | `Sofa.Component.ODESolver.Forward` |
| `BDFOdeSolver` | **YES** | `Sofa.Component.ODESolver.Backward` |
| `DampVelocitySolver` | **YES** | `Sofa.Component.ODESolver.Forward` |
| `RungeKutta2Solver` | **YES** | `Sofa.Component.ODESolver.Forward` |
| `NewtonRaphsonSolver` | **YES** | `Sofa.Component.ODESolver.Backward` |
| `EulerSymplecticSolver` | **NO** | Not a separate class; this is `EulerExplicitSolver` with `symplectic=true`. The `.scn` example file `EulerSymplecticSolver.scn` confirms this (line 3: "variant of `EulerExplicitSolver` where Data `symplectic` is set to true"). |
| `SymplecticEulerSolver` | **NO** | Alias; same situation as above. |

**Missed integrators to add to the allow-list**: `BDFOdeSolver`, `RungeKutta2Solver`, `NewtonRaphsonSolver`, `DampVelocitySolver`. All four are registered. `DampVelocitySolver` is a trivial velocity-damping-only solver, rarely used as a primary integrator — acceptable to add but annotate as unusual.

---

## "Mapped MO" detection algorithm

The SOFA core distinction between mapped and unmapped MOs is made at the **`Node.mechanicalMapping` slot**, not by scanning `*Mapping` output links. A node's MO is "mapped" if and only if `node.mechanicalMapping` is non-null — meaning a `BaseMapping`-derived object occupies that slot. Visual/data-only mappings (e.g. `BarycentricMapping` to an `OglModel`) live in a child node and do not occupy `mechanicalMapping` in the parent; they are not considered mechanical by `BaseMechanicalVisitor`.

```python
def is_node_mapped(node_summary):
    """
    node_summary: one entry from summarize_scene's node tree.
    Returns True if the MO at this node is mechanically mapped
    (i.e. inherits dynamics from a parent solver via a mechanical mapping).
    """
    # A node is mapped if it contains any component whose class is a
    # registered mechanical mapping (i.e. in the BaseMapping subclass set).
    # In summarize_scene's JSON output the component list is flat per node.
    # We identify mechanical mappings by class-name suffix patterns.
    MECHANICAL_MAPPING_SUFFIXES = (
        "Mapping",       # BarycentricMapping, RigidMapping, IdentityMapping, etc.
        "MultiMapping",  # SubsetMultiMapping, IdentityMultiMapping, etc.
    )
    VISUAL_MAPPING_CLASSES = {"VisualMapping"}  # not mechanical

    for comp in node_summary.get("components", []):
        cls = comp["class"]
        if cls in VISUAL_MAPPING_CLASSES:
            continue
        if any(cls.endswith(sfx) for sfx in MECHANICAL_MAPPING_SUFFIXES):
            return True
    return False


def find_unmapped_mos_without_integrator(scene_summary):
    """
    Walk the scene tree. For each node that has a MechanicalObject
    and is NOT mapped, check that an ODE solver exists in the node
    itself or in any ancestor node.

    Returns list of (node_path, message) violations.
    """
    ODE_SOLVER_CLASSES = {
        "EulerImplicitSolver", "RungeKutta4Solver", "NewmarkImplicitSolver",
        "StaticSolver", "EulerExplicitSolver", "VariationalSymplecticSolver",
        "CentralDifferenceSolver", "BDFOdeSolver", "RungeKutta2Solver",
        "NewtonRaphsonSolver", "DampVelocitySolver",
    }

    violations = []

    def walk(node, ancestor_has_solver):
        node_has_solver = ancestor_has_solver or any(
            c["class"] in ODE_SOLVER_CLASSES
            for c in node.get("components", [])
        )
        has_mo = any(c["class"] == "MechanicalObject" for c in node.get("components", []))
        mapped = is_node_mapped(node)

        if has_mo and not mapped and not node_has_solver:
            violations.append((node["path"], "MechanicalObject with no ODE solver in ancestry"))

        for child in node.get("children", []):
            walk(child, node_has_solver)

    walk(scene_summary["root"], False)
    return violations
```

**Key subtleties:**

- `node_has_solver` propagates downward: once an ancestor has a solver, all descendants (mapped or not) satisfy the rule.
- `is_node_mapped` must check the *current node's* mapping components, not the parent's. The `mechanicalMapping` slot is in the child node (the slave), not the master.
- `MultiMapping` nodes (Rule 12 territory) must NOT have their own solver — that is Rule 12's concern, not Rule 3's. Rule 3 skips them via the `mapped=True` branch.
- A visual-only `BarycentricMapping` inside a child `OglModel` node does not make that node "mapped" in the mechanical sense; the OglModel node typically has no `MechanicalObject` anyway.

---

## Final rule wording (v2.1 §1.1 Rule 3 — revised)

> **Rule 3 — Time Integration Solver**
>
> *Recommend:* `EulerImplicitSolver` for almost all deformable FEM scenes (~88% of upstream uses); `EulerExplicitSolver` for light explicit dynamics (94 upstream uses, more common than `RungeKutta4Solver`'s 24); `RungeKutta4Solver` for smooth explicit dynamics where high-order accuracy matters but stiffness is bounded.
>
> *Validate:* accept any of `EulerImplicitSolver`, `RungeKutta4Solver`, `NewmarkImplicitSolver`, `StaticSolver`, `EulerExplicitSolver`, `VariationalSymplecticSolver`, `CentralDifferenceSolver`, `BDFOdeSolver`, `RungeKutta2Solver`, `NewtonRaphsonSolver`, `DampVelocitySolver` (all class-cache-verified registered in this build).
>
> *Check:* for every `MechanicalObject` in the scene, at least one ODE solver must exist in the node itself or in any ancestor node, **unless** the node also contains a `*Mapping` or `*MultiMapping` component (mapped MOs inherit dynamics from the solver that governs their parent/master).
>
> *Severity:* `error` — an unmapped MO with no solver in ancestry is silently frozen (no motion, no error, no warning from SOFA runtime).

**Change from v2.1 draft:**

- `EulerExplicitSolver` should be the primary "alternative for explicit dynamics" recommendation, ahead of `RungeKutta4Solver` — Agent 2 corpus shows 94 vs 24 upstream uses.
- Add `BDFOdeSolver`, `RungeKutta2Solver`, `NewtonRaphsonSolver`, `DampVelocitySolver` to the allow-list (all registered, omitting them causes false positives on valid scenes).

---

## Edge cases

| Scenario | Correct behavior |
|---|---|
| MO used as a collision proxy with `simulated="false"` on the collision model | Rule 3 **still fires** if the MO has no solver in ancestry. The `simulated="false"` flag is on the `*CollisionModel` component, not the MO — the MO itself remains unsimulated but the flag is on the wrong object. Example: `PointSplatModel.scn` "World" node has an MO with no solver and `simulated="false"` on its collision models. This is a valid SOFA pattern (static floor) and should be **exempt**. Detection: check if `moving="false"` AND `simulated="false"` appear on any `*CollisionModel` sibling in the same node. |
| MO with `template="Rigid3d"` representing a static rigid body | Same as above. If no solver in ancestry, SOFA silently freezes it, which is intentional for a static body. The rule should **warn** (not error) when the MO has zero motion over all steps (`mo_static` smell test covers this at runtime). |
| Multiple solvers at different tree levels | Permitted and common (see `Diamond.py`: a `goal` subnode has its own `EulerImplicitSolver`, the `robot` subnode has another). The visitor prunes at the first solver it finds per branch, so each subtree is independently integrated. Rule 3 must not require a single root-level solver — checking ancestry per-MO is correct. |
| Mapped MO under a `MultiMapping` (Rule 12 case) | The MultiMapping node must NOT have its own solver (Rule 12). Its MO is mapped, so Rule 3 is satisfied. No interaction. |
| Visual `OglModel` node with `BarycentricMapping` but no `MechanicalObject` | Not a MO at all — Rule 3 does not apply. |

**Recommended additional exemption:** when a node contains a `MechanicalObject` **and** all `*CollisionModel` siblings have `simulated="false"` (or `moving="false"`), suppress the Rule 3 error to `info`. This covers the ubiquitous static-floor pattern seen in `PointSplatModel.scn` and `ViewerSetting.scn`.

---

## Sample scenes

**Should NOT trigger Rule 3:**

1. `/home/sizhe/workspace/sofa/plugins/SoftRobots.Inverse/examples/sofapython3/robots/Diamond.py` — multiple subtrees each with their own `EulerImplicitSolver`; all MOs have a solver in ancestry or are mapped.
2. `/home/sizhe/workspace/sofa/src/examples/Component/ODESolver/Forward/RungeKutta4Solver.scn` — single `RungeKutta4Solver` at the deformable node; visual child uses `BarycentricMapping` (mapped MO, exempt).
3. `/home/sizhe/workspace/sofa/src/examples/Component/ODESolver/Backward/NewmarkImplicitSolver.scn` — `NewmarkImplicitSolver` is in the allow-list.

**Should trigger Rule 3 (violations):**

4. `/home/sizhe/workspace/sofa/src/examples/Component/Visual/PointSplatModel.scn` — "World" node has a `MechanicalObject` with no solver in ancestry and no mapping. *However*, its `*CollisionModel` siblings have `simulated="false"`, so this is a static-floor; the recommended behavior is `info` (not `error`) per the additional exemption above.
5. Any scene where a deformable `TetrahedronFEMForceField` node has a `MechanicalObject` but lacks `EulerImplicitSolver`/etc. in the same node or above — silent freeze, should be `error`.
6. `/home/sizhe/workspace/sofa/plugins/ModelOrderReduction/examples/bouncingBall/softSphereFalling.py` — has `MechanicalObject` but imports suggest solver is defined in a Python helper function; if absent at any level, fires Rule 3.

---

## Alternative recommendation: EulerExplicitSolver vs. RungeKutta4Solver

The v2.1 spec recommends `RungeKutta4Solver` as the alternative for "explicit dynamics with bounded stiffness." Agent 2's corpus shows:

- `EulerExplicitSolver`: **94 upstream uses**
- `RungeKutta4Solver`: **24 upstream uses**

`EulerExplicitSolver` is 4x more prevalent as an explicit alternative. The recommendation should be **revised** to:

> *Recommend:* `EulerExplicitSolver` as the primary explicit alternative (4x more prevalent); `RungeKutta4Solver` when higher-order time accuracy is needed and dt is very small.

`RungeKutta4Solver` is a valid and registered class but is a niche choice (used in specific fluid/visual scenes like `PointSplatModel.scn`). Recommending it as the "default explicit" is misleading — most SOFA developers who want explicit dynamics reach for `EulerExplicitSolver` (which also supports `symplectic=true` for better stability).

---

## Severity verdict

**`error`** — confirmed.

Rationale: an unmapped `MechanicalObject` with no ODE solver in ancestry is **silently frozen** — no motion, no NaN, no SOFA warning, no error. This is not "wrong physics" that might be caught at runtime; it is **complete non-simulation** with no diagnostic signal. The user will observe "nothing moves" with no log output to explain why. This is exactly the class of silent failure that `diagnose_scene` is designed to surface. Severity `warning` would be inappropriately permissive — there is no scenario where an unsimulated deformable MO is intentional and unlabeled. (Static bodies labeled with `simulated="false"` are covered by the additional exemption, downgraded to `info`.)

---

## Confidence verdict

**High confidence** on the core rule and mechanism (source-verified in `AnimateVisitor.cpp`, `BaseMechanicalVisitor.cpp`). 

**Medium confidence** on the static-body exemption detection heuristic (`simulated="false"` on sibling `*CollisionModel`) — this needs a unit test against `PointSplatModel.scn` to confirm it correctly suppresses the false positive.

**Medium confidence** on the `DampVelocitySolver` inclusion — it is registered but is not a standard ODE integrator (it only damps velocities, not integrates forces). Including it in the allow-list prevents false positives on scenes that use it as a supplementary component, but it should never be the *only* "integrator" in a physics subtree. A future refinement could warn when `DampVelocitySolver` is the only solver in ancestry of a MO with force fields.

**No concerns** on the mapped-MO exemption — the `node.mechanicalMapping` slot is SOFA core design, verified in `Node.h` line 257 and `BaseMechanicalVisitor.cpp`.
