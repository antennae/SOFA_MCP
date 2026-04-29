# Rule 12 Review: MultiMapping Output Node Has No Solver

## 1. Mechanistic explanation

`MechanicalIntegrationVisitor::fwdOdeSolver` (`/home/sizhe/workspace/sofa/src/Sofa/framework/Simulation/Core/src/sofa/simulation/mechanicalvisitor/MechanicalIntegrationVisitor.cpp:71`) returns `RESULT_PRUNE` after calling `obj->solve(...)`. In `BaseMechanicalVisitor::processNodeTopDown` (`BaseMechanicalVisitor.cpp:58-64`), `node->solver` — typed `NodeSequence<OdeSolver>` (`Node.h:234`) — is iterated **first**, before any mapping. So when the visitor enters a MultiMapping output node that contains an ODE solver, the solver fires immediately, runs a complete independent integration step on only the DoFs visible in that subtree, then prunes. The MultiMapping's `apply`/`applyJ`/`applyJT` are never called by that traversal pass. The output DoFs detach from all parent MOs and evolve independently.

Correct topology: ODE solver lives in a common **ancestor** node of all input MOs and the output MO. The `Rigidify()` template in STLIB (`rigidification.py:119-126`) explicitly removes `solver`, `integration`, and `correction` from the output node before attaching `SubsetMultiMapping` — canonical confirmation.

## 2. Full registered `*MultiMapping` list (this build)

From `.sofa_mcp_results/.sofa-component-plugin-map.json`:

| Registered name | Plugin | True `core::MultiMapping`? |
|---|---|---|
| `IdentityMultiMapping` | `Sofa.Component.Mapping.Linear` | Yes |
| `SubsetMultiMapping` | `Sofa.Component.Mapping.Linear` | Yes (via `LinearMultiMapping`) |
| `CenterOfMassMultiMapping` | `Sofa.Component.Mapping.Linear` | Yes (via `LinearMultiMapping`) |
| `DistanceMultiMapping` | `Sofa.Component.Mapping.NonLinear` | Yes |
| `DifferenceMultiMapping` | `Cosserat` | **No** — inherits `core::Multi2Mapping`, not `core::MultiMapping` (same structural risk, different base class) |

**`BeamMultiMapping` and `RigidMultiMapping` do not exist** — no source files, no registration in cache. These two names in the current rule spec are wrong. `CenterOfMassMultiMapping` is real and missing from the spec.

## 3. Edge cases

**ODE solver vs linear solver vs constraint solver:** The rule must restrict to `core::behavior::OdeSolver` subclasses only. `node->solver` (`NodeSequence<OdeSolver>`) is what the visitor iterates; linear solvers (`SparseLDLSolver`, `CGLinearSolver` — `core::behavior::LinearSolver` subclasses) and constraint solvers (`GenericConstraintSolver` — `core::behavior::ConstraintSolver`) are stored in separate node fields. A linear solver without an ODE solver on the output node is inert but not broken. A constraint solver there would not trigger `RESULT_PRUNE` and is architecturally odd but not the primary failure.

**Mass on the output node:** Allowed and canonical — `UniformMass` appears in both `IdentityMultiMapping.scn` and `SubsetMultiMapping.scn`. Mass contributions propagate via `areMassesMapped()`.

**ForceFields on the output node:** Allowed and the primary use case — forces propagate to parent MOs via `applyJT`. Do not flag.

**ConstraintCorrections on the output node:** None of 7 examined canonical scenes put a `*ConstraintCorrection` on the MultiMapping output node; they all belong on the parent MO nodes. Do not flag as a separate rule violation; do not allow as an exception.

**Nested MultiMappings:** No additional issue. The same rule applies node-by-node.

## 4. Sample scenes

**Should NOT trigger:**
- `/home/sizhe/workspace/sofa/src/examples/Component/Mapping/Linear/IdentityMultiMapping.scn` — solver at root; `concatenation` node has `IdentityMultiMapping` + `UniformMass` + `ConstantForceField`, no solver.
- `/home/sizhe/workspace/sofa/src/examples/Component/Mapping/Linear/SubsetMultiMapping.scn` — same pattern.
- `/home/sizhe/workspace/sofa/src/examples/Component/Mapping/NonLinear/DistanceMultiMapping.scn` — `connection` node: `DistanceMultiMapping` + `RestShapeSpringsForceField`, no solver.
- `/home/sizhe/workspace/sofa/src/examples/Component/Engine/Select/NearestPointROI.scn` — `merge1`/`merge2` output nodes: `SubsetMultiMapping` + `MeshSpringForceField`, no solver. Parent nodes M1/M2/M3 carry `UncoupledConstraintCorrection`.
- `/home/sizhe/workspace/sofa/plugins/SoftRobots/examples/tutorials/Tripod/details/tripod.py` — `RigidParts` node has `SubsetMultiMapping`; solvers are in arm/body ancestor nodes.
- `/home/sizhe/workspace/sofa/src/applications/plugins/STLIB/python3/src/stlib3/physics/mixedmaterial/rigidification.py` — `Rigidify()` explicitly removes solver before attaching `SubsetMultiMapping`.

**Should trigger:** No upstream scene exists with this pattern (0/24 corpus). Synthetic broken scene: any node carrying `IdentityMultiMapping` (or other `*MultiMapping`) co-located with `EulerImplicitSolver`.

## 5. Severity

**Error is justified.** The failure is deterministic and complete: the output DoFs always integrate independently when this pattern is present, with no configuration that produces correct multi-body physics. No "maybe intentional" interpretation applies.

## 6. Final recommended rule wording

**Trigger class list:** `{IdentityMultiMapping, SubsetMultiMapping, CenterOfMassMultiMapping, DistanceMultiMapping}` (Cosserat optional: `DifferenceMultiMapping` with conditional note).

**Remove `BeamMultiMapping` and `RigidMultiMapping` — these names do not exist.**

**Forbidden on output node:** Any `OdeSolver` subclass (`EulerImplicitSolver`, `RungeKutta4Solver`, `StaticSolver`, `NewmarkImplicitSolver`, `EulerExplicitSolver`, `VariationalSymplecticSolver`, `CentralDifferenceSolver`, `BDFOdeSolver`). Explicitly NOT linear solvers or constraint solvers.

**Allowed on output node:** `Mass` components, any `ForceField`, topology containers, visual models, constraints (`BilateralLagrangianConstraint`, etc.), collision models, non-mechanical visual/collision mappings.

**Severity:** `error`.

## 7. Confidence verdict

**Ship with refinements.** Mechanistic correctness is fully confirmed in SOFA source. Required changes:
1. Remove `BeamMultiMapping` and `RigidMultiMapping` from the trigger list (don't exist).
2. Add `CenterOfMassMultiMapping`.
3. Explicitly scope "forbidden" to `OdeSolver` subclasses only, not all solvers.
4. Optional: add `DifferenceMultiMapping` (Cosserat) with a conditional note that it inherits `Multi2Mapping` but has the same structural risk.
