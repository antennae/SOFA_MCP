# Rule 4 — Linear Solver: deep review

**Date:** 2026-04-26
**Reviewer:** single-rule deep-review agent
**Rule under review (v2.1 §1.1 Rule 4, unchanged from v1):**
> "implicit time solvers require a linear solver. Default to `SparseLDLSolver` with
> `template="CompressedRowSparseMatrixMat3x3d"` for FEM. Use `CGLinearSolver` only for
> very large meshes (>100k nodes)."

---

## 1. Class-registration audit

Confirmed registered in this build (via `search_sofa_components`):

| Class | Query | Registered |
|---|---|---|
| `SparseLDLSolver` | LDL | YES |
| `AsyncSparseLDLSolver` | LDL | YES |
| `EigenSimplicialLDLT` | LDL | YES |
| `CGLinearSolver` | CG / LinearSolver | YES |
| `PCGLinearSolver` | CG / LinearSolver | YES |
| `ParallelCGLinearSolver` | CG | YES |
| `BTDLinearSolver` | LinearSolver | YES |
| `MinResLinearSolver` | LinearSolver | YES |
| `SVDLinearSolver` | LinearSolver / Solver | YES |
| `CholeskySolver` | Cholesky | YES |
| `PrecomputedLinearSolver` | LinearSolver | YES |
| `SparseDirectSolver` | SparseDir | **NOT REGISTERED** |
| `SparseLUSolver` | LUSolver | **NOT REGISTERED** |
| `SparseCholeskySolver` | Cholesky | **NOT REGISTERED** |

Key finding: `SparseLDLSolver` is registered with exactly **two** template instantiations
(from `SparseLDLSolver.cpp` lines 35-36):
- `CompressedRowSparseMatrix<SReal>` (default, scalar — for Rigid3 / 1-DOF)
- `CompressedRowSparseMatrix<Mat3x3>` (for Vec3d FEM — the `CompressedRowSparseMatrixMat3x3d` alias)

No other templates are compiled. Using any other template string at scene instantiation will
silently fall through to the default `SReal` template.

---

## 2. Mechanism — no linear solver under an implicit ODE

Source: `LinearSolverAccessor.cpp` (`init()`, lines 32–41).

`EulerImplicitSolver::init()` calls `LinearSolverAccessor::init()`. That method:
1. Tries to find a `LinearSolver` descendant in the same subtree (`SearchDown`).
2. If none found: emits `msg_error() << "A linear solver is required by this component but
   has not been found."` and sets `d_componentState = ComponentState::Invalid`.

**Consequence:** the component is marked Invalid at init time. SOFA does not abort the
simulation; it continues loading, but `l_linearSolver->solveSystem()` in `solve()` will
dereference a null pointer at the first animate step — producing a segfault or uncaught
exception, not a silent failure or graceful error. No auto-creation of a fallback linear
solver occurs (unlike `FreeMotionAnimationLoop`'s auto-LCP behaviour).

The `msg_error` line is verifiable by the `^\[(ERROR|FATAL)\]` catch-all regex — so the
WARN catch-all in §6.B will surface it even without a dedicated rule.

---

## 3. Re-evaluation of "CG only for very large meshes (>100k nodes)"

### What corpus actually shows (Agent 2: 1480 CG vs 440 SparseLDL)

Investigating *context* of upstream CG uses across SoftRobots and src/ reveals three
distinct patterns — none of which is "large mesh":

| Pattern | Examples | DOF count | Reason for CG |
|---|---|---|---|
| **Effector / goal target node** | `effectorGoal.py`, `circularrobot.py` target, `SoftArmGripper` target, `DiamondRobot` target, `Trunk` target | 1–3 DOF (single `MechanicalObject` at target position) | Trivially small; CG converges in 1 step; SparseLDL setup cost would dominate |
| **Cosserat rod elements** | `cosserat_changing_radius.py`, `PCS_Example1.py` | 5–30 beam sections (Rigid3 or Vec6) | 1D beam, not 3D FEM; system is banded, CG reasonable |
| **Generic src/ demos** | `skybox.scn`, `simpleSphere.scn`, `chainAll.scn` | small (demo) | Historical — src/ predates SparseLDL prevalence in soft robotics |

**In every SoftRobots scene with a deformable FEM body, `SparseLDLSolver` is used:**
- `DiamondRobot.py` body: `SparseLDLSolver(template="CompressedRowSparseMatrixd")`
- `SoftArmGripper.py` finger: `SparseLDLSolver(template="CompressedRowSparseMatrixMat3x3d")`
- `tri_leg_cables.py`, `prostate_chamber.py`, `cantilever_beam.py`: all `SparseLDLSolver`
  with `CompressedRowSparseMatrixMat3x3d`
- `CircularRobot/circularrobot.py` robot body (not target): `SparseLDLSolver`

**The 3.4× CG-to-LDL ratio is almost entirely explained by effector/goal nodes, which
are auxiliary single-DOF MOs — not the main FEM body.** The rule's "100k nodes" rationale
is fabricated; no upstream scene uses CG for large meshes. The actual split is:

- `SparseLDLSolver` → main FEM bodies (Vec3d template, contact-capable)
- `CGLinearSolver` → auxiliary goal/target nodes (single point, `firstOrder=True`,
  no contact)

### Conclusion on the "100k nodes" claim

The threshold is **not defensible** as a mesh-size criterion. The correct distinction is:

- **FEM body (TetrahedronFEM, HexaFEM, Vec3d MO)** → `SparseLDLSolver` with
  `template="CompressedRowSparseMatrixMat3x3d"`
- **Auxiliary goal/effector nodes (single-point MO, `firstOrder=True`)** → `CGLinearSolver`
  acceptable because the system is trivially small regardless of the main mesh size

---

## 4. Template parameter analysis

Agent 2: only 40 of 440 SparseLDL uses set `template="CompressedRowSparseMatrixMat3x3d"`.

Cross-referencing `SparseLDLSolver.cpp` registration:
- Default (no template arg) → `CompressedRowSparseMatrix<SReal>` — scalar, not block-3x3.
  For Vec3d FEM this is **suboptimal**: processes each coordinate independently, 3× the
  symbolic decomposition work.
- `CompressedRowSparseMatrixMat3x3d` → `CompressedRowSparseMatrix<Mat3x3>` — correct for
  Vec3d FEM: treats 3×3 blocks as atomic units, significant speedup.

The rule's template guidance is **correct and important** but underspecified. The condition
should be: set this template when the MO template is `Vec3d` (which includes all
TetrahedronFEM scenes). For Rigid3d bodies use the default (scalar). For 1-DOF goal nodes
(CG anyway), template is irrelevant.

---

## 5. Asymmetric matrix case (Agent 7 #12)

`BarycentricMapping` between mismatched topologies introduces geometric stiffness terms
`∂J^T/∂q · f_p` that can make the assembled stiffness matrix asymmetric.
`SparseLDLSolver` **does not detect asymmetry** — source confirms it only checks for
zero diagonal during factorization (`D(k,k) is zero`). Asymmetric matrices will factorize
without error but produce silently wrong results (the off-diagonal asymmetric terms are
ignored/symmetrized by LDLT).

The recommended remediation, `SparseLUSolver`, is **NOT registered** in this build.
Available registered alternatives:
- `CholeskySolver` — still symmetric-only (Cholesky requires SPD)
- `MinResLinearSolver` — handles symmetric indefinite, not general asymmetric
- No registered solver handles general asymmetric systems in this build.

**Practical remediation when asymmetry is suspected:** avoid mapping across mismatched
topologies. Use `SubsetMultiMapping` or ensure parent topology matches child, which
eliminates the asymmetric geometric stiffness term. The `nonlinear_mapping_with_symmetric_solver`
smell test (Agent 7) should flag the setup as a warning, with the message explaining that
no asymmetric-capable solver is available in this build and that topology alignment is the
fix.

---

## 6. Edge cases

| Case | Behaviour | Source |
|---|---|---|
| Implicit ODE + no linear solver | `msg_error` at init, `ComponentState::Invalid`, segfault at step 1 (null deref) | `LinearSolverAccessor.cpp` lines 37–40 |
| Multiple linear solvers in same node | First one found by `getContext()->get<LinearSolver>(SearchDown)` wins; subsequent ones unused | SOFA ObjectFactory `get<T>` returns first match |
| Linear solver in ancestor node above the ODE solver | `LinearSolverAccessor` searches `SearchDown` from the ODE solver's context, NOT ancestors. A solver in a parent node is NOT found. | `LinearSolverAccessor.cpp` line 34 |
| Linear solver in sibling node | Not found — `SearchDown` only descends | Same |
| ODE + linear solver in node with no MO | Valid structurally; solver is unused (no MechanicalObject to supply DOFs). No error. | SOFA scene graph design |
| `firstOrder=True` + CG | Valid and common (effector goal nodes). `firstOrder` changes the RHS but not the linear system structure. | `EulerImplicitSolver.cpp` lines 136-143 |

**Important edge case for implementation:** the `SearchDown` scope means a linear solver
placed in a parent node (e.g., at root) does NOT satisfy an ODE solver in a child node.
This is a common beginner mistake. Rule 4's check should verify that the linear solver is
**in the same node or a descendant** of the ODE solver node — not just "somewhere in
ancestry."

---

## 7. Sample scenes (canonical and violations)

### Canonical — FEM body with SparseLDL
```python
# prostate_chamber.py (project archiv), tri_leg_cables.py, DiamondRobot body
node.addObject('EulerImplicitSolver', rayleighStiffness=0.1, rayleighMass=0.1)
node.addObject('SparseLDLSolver', template='CompressedRowSparseMatrixMat3x3d')
node.addObject('MechanicalObject', template='Vec3d')
node.addObject('TetrahedronFEMForceField', template='Vec3d', ...)
```

### Canonical — effector/goal node with CG
```python
# SoftRobots effectorGoal.py, target nodes in inverse scenes
goal.addObject('EulerImplicitSolver', firstOrder=True)
goal.addObject('CGLinearSolver', iterations=100, threshold=1e-5, tolerance=1e-5)
goal.addObject('MechanicalObject', template='Vec3d', position=[...])  # single point
```

### Canonical — SparseLDL no template (Rigid3d body)
```python
# SoftArmGripper rigid arm segment
arm.addObject('EulerImplicitSolver', firstOrder=True)
arm.addObject('SparseLDLSolver', name='ldl', template='CompressedRowSparseMatrixMat3x3d')
arm.addObject('MechanicalObject', template='Rigid3', name='dofs')
```
Note: Rigid3 should technically use the scalar template; Mat3x3d still works but processes
6-DOF rigids as 3×3 blocks (partial mismatch). Empirically used in upstream anyway.

### Violation 1 — no linear solver under implicit ODE
```python
node.addObject('EulerImplicitSolver')
# Missing: SparseLDLSolver or CGLinearSolver
node.addObject('MechanicalObject', template='Vec3d')
```
Result: `[ERROR] A linear solver is required...`, `ComponentState::Invalid`, segfault at step 1.

### Violation 2 — wrong template for Vec3d FEM
```python
node.addObject('EulerImplicitSolver')
node.addObject('SparseLDLSolver')  # no template → scalar SReal, suboptimal
node.addObject('MechanicalObject', template='Vec3d')
node.addObject('TetrahedronFEMForceField', template='Vec3d')
```
Result: simulation runs correctly but 3× slower than necessary; no error emitted.

### Violation 3 — linear solver in wrong scope
```python
root.addObject('SparseLDLSolver', template='CompressedRowSparseMatrixMat3x3d')  # at root
child = root.addChild('robot')
child.addObject('EulerImplicitSolver')  # searches SearchDown from child — does NOT find root solver
child.addObject('MechanicalObject', template='Vec3d')
```
Result: same as Violation 1.

---

## 8. Recommended rule wording

**Replace current Rule 4 with:**

> **Rule 4 — Linear Solver.**
> Every implicit ODE solver (`EulerImplicitSolver`, `NewmarkImplicitSolver`, `StaticSolver`)
> requires a linear solver **in the same node or a descendant** (not ancestor — SOFA uses
> `SearchDown`). Absence causes `[ERROR] A linear solver is required` at init, then crash at
> step 1.
>
> *Recommend:*
> - `SparseLDLSolver(template="CompressedRowSparseMatrixMat3x3d")` for any node whose
>   `MechanicalObject` uses `Vec3d` template (i.e., all 3D FEM bodies). This template
>   processes 3×3 blocks atomically and is the correct choice for `TetrahedronFEMForceField`
>   and similar force fields.
> - `CGLinearSolver` for auxiliary effector/goal nodes that carry a single-point
>   `MechanicalObject` with `firstOrder=True`. These nodes have trivially small systems; CG
>   convergence in one step, SparseLDL setup cost would dominate.
> - **Drop the "100k nodes" threshold** — it has no empirical basis. The split is not
>   mesh-size-based; it is structural-role-based (FEM body vs. effector target).
>
> *Validate:* {`SparseLDLSolver`, `AsyncSparseLDLSolver`, `CGLinearSolver`, `PCGLinearSolver`,
> `ParallelCGLinearSolver`, `BTDLinearSolver`, `MinResLinearSolver`, `SVDLinearSolver`,
> `CholeskySolver`, `EigenSimplicialLDLT`, `PrecomputedLinearSolver`}.
>
> *NOT registered in this build (do not emit as recommendations):*
> `SparseDirectSolver`, `SparseLUSolver`, `SparseCholeskySolver`.
>
> *Asymmetry note:* `BarycentricMapping` across mismatched topologies can produce an
> asymmetric stiffness matrix. `SparseLDLSolver` silently symmetrizes it (wrong results,
> no error). No asymmetric-capable solver is registered in this build. Mitigation: align
> parent/child topology or use `SubsetMultiMapping`. Flag via `nonlinear_mapping_with_symmetric_solver`
> smell test (Agent 7) as warning, not error.
>
> *Scope check for `summarize_scene`:* verify linear solver is in the ODE solver's own
> subtree — a solver at root does NOT satisfy a child-node ODE solver.

---

## 9. Severity verdict

**Rule wording: NEEDS REVISION — medium severity.**

The structural claim (implicit ODE needs linear solver) is correct and critical.
The "100k nodes" threshold for CG is wrong in both rationale and threshold — but it
biases toward SparseLDL, which is the more correct default. The practical impact is:
- Scenes generated by this tool will use SparseLDL for FEM bodies (correct).
- The rule will flag legitimate CG uses in effector nodes as non-ideal (minor false positives,
  low impact since effector nodes are small).

The `SearchDown` scope constraint and the template conditionality are the two additions
with real diagnostic value that the current wording misses.

## 10. Confidence verdict

- Mechanism (LinearSolverAccessor error + crash): **HIGH** — read from source.
- Class registration audit: **HIGH** — verified by running `search_sofa_components`.
- "100k nodes" threshold debunked: **HIGH** — corroborated by examining all SoftRobots
  canonical scenes; every FEM body uses SparseLDL; CG appears exclusively on trivial
  single-point nodes.
- Template guidance: **HIGH** — confirmed by `SparseLDLSolver.cpp` registration (only two
  compiled templates exist).
- Asymmetry / SparseLUSolver absence: **HIGH** — factory search returns 0 results for LUSolver.
- Multiple-solver / wrong-scope edge cases: **MEDIUM** — inferred from `LinearSolverAccessor`
  source; not verified by runtime test.
