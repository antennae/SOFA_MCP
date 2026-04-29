# Agent 6 — SOFA discussions older / non-Q&A

**Mining bucket:** `sofa-framework/sofa` GitHub Discussions, OLDER threads (>18 months) and the non-Q&A categories (Ideas/Suggestions, Share your achievements, Announcement). Captured 2026-04-25.

**Method:** WebFetch against discussion category pages. Sampled 16 threads, biased to scene-structure / mapping / constraint / actuation / topology gotchas to complement Agents 1, 4, and 5.

## Executive summary

The older General-bucket threads converge hard on the same five themes Agent 4 surfaced (units, constraint pipeline, plugin loading, mappings, topology) but add three diagnostic patterns Agents 1/4 did not capture: (a) **`FreeMotionAnimationLoop` without a `*ConstraintCorrection` is the canonical "scene runs but nothing moves" failure**, named explicitly by maintainers as "characteristic"; (b) **`ArticulatedHierarchyContainer` / `ArticulatedSystemMapping` mis-indexing** silently chains articulations that should be parallel — looks like "only one DoF moves"; (c) **topology-changing scenes (SofaCarving, Tearing) crash any forcefield using non-`TopologySubsetIndices` index Data**. None contradict the spec or Agents 1/4; several refine smell-test thresholds and add three new playbook entries. One refinement-of-emphasis: F4 below partly contradicts Agent 1's M6 — there *is* a uniform path for *constraint* forces (just not for per-FF elastic forces).

## Findings

### F1. "Nothing moves under FreeMotionAnimationLoop" = missing ConstraintCorrection
- Link: https://github.com/sofa-framework/sofa/discussions/2731
- Summary: Maintainer states explicitly that an object failing to move under `FreeMotionAnimationLoop` is "characteristic from a missing ConstraintCorrection."
- Diagnostic flow: `low_displacement` fires AND scene contains `FreeMotionAnimationLoop` AND no descendant of any deformable MO node has a `*ConstraintCorrection` (`UncoupledConstraintCorrection`, `LinearSolverConstraintCorrection`, `PrecomputedConstraintCorrection`, `GenericConstraintCorrection`).
- Insight: Static structural check, fires before stepping. High-confidence, well documented.

### F2. ArticulatedSystemMapping with wrong parent/child indices chains parallel joints
- Link: https://github.com/sofa-framework/sofa/discussions/2691
- Summary: User's gripper articulations were sequential ("Articulation_2 depends on Articulation_1") because `parentIndex`/`childIndex` of the second `ArticulationCenter` were set to make jaw 2 child of jaw 1 instead of child of base.
- Diagnostic flow: complaint "only one DoF/joint moves" + `ArticulatedHierarchyContainer` present → walk `ArticulationCenter` nodes, flag any whose `parentIndex` matches another center's `childIndex` unless intentional.
- Insight: New playbook row: "only the first articulation moves" → check articulation index graph for accidental chains.

### F3. Topology-changing scenes silently corrupt indices in non-topology-aware forcefields
- Link: https://github.com/sofa-framework/sofa/discussions/3008
- Summary: `RestShapeSpringsForceField.indices` is plain `Data<vector<Index>>`; under SofaCarving (or Tearing) the indexed points get removed and the FF crashes with `Out of Bounds m_indices detected. ForceField is not activated.`
- Diagnostic flow: detect topology-modifying components (`SofaCarving`, `TetrahedronSetTopologyModifier` with handlers, `TearingEngine`); then verify that every index-bearing component (`RestShapeSpringsForceField`, `FixedConstraint`, `BoxROI` consumers, `ProjectiveConstraintSet`) uses `TopologySubsetIndices` not raw `Data<vector<Index>>`.
- Insight: New smell test `topology_changing_with_static_indices`. Library-side fix is `createTopologyHandler`; diagnostic is "warn user this combination will crash mid-run."

### F4. Contact forces under Lagrange require `computeConstraintForces=1` plus an H^T·λ transform
- Link: https://github.com/sofa-framework/sofa/discussions/3812
- Summary: To extract contact forces under `FreeMotionAnimationLoop` you need: (1) `LCPConstraintSolver` or `GenericConstraintSolver` with `computeConstraintForces=1`, (2) `DefaultContactManager` with `response="FrictionContactConstraint"`, (3) `*ConstraintCorrection` on each object. Then read `constraintForces` (impulses; divide by dt) and apply `F(x,y,z) = H^T · λ(n,t1,t2)` to map to world frame.
- Diagnostic flow: when complaint = "I can't read contact forces" or `low_forces` should cover contacts, check the four prerequisites; if any missing, that's the answer.
- Insight: Probe library v2 should add `read_constraint_forces(scene, dt)` that handles the H^T·λ transform. Lightly contradicts Agent 1's M6 — there *is* a uniform path for *constraint* forces, just not per-FF elastic forces.

### F5. Haptic "no force feedback" requires `LCPForceFeedback`, not just a constraint solver
- Link: https://github.com/sofa-framework/sofa/discussions/2918
- Summary: Constraint solver computes contact forces in physics; **device** receives nothing unless `LCPForceFeedback` (or equivalent) is wired into the haptic node. Reference: `Geomagic-RigidSkull.scn`.
- Diagnostic flow: complaint "haptic feels nothing" + scene has Geomagic/Haply/etc. + no `LCPForceFeedback` descendant → that's the bug.
- Insight: Niche but very high signal when it fires. Add to playbook under "haptic feedback dead."

### F6. BarycentricMapping requires a volumetric (tetra/hexa) parent topology
- Link: https://github.com/sofa-framework/sofa/discussions/2690
- Summary: User's brain VTK had only surface triangles; `BarycentricMapping<Vec3d,Vec3d>` errored `Data attribute 'input' does not point to a mechanical state of data type 'Vec3d'` plus `Cannot find edge 0 [28, 77] in triangle 0`. Real cause: parent topology must be volumetric.
- Diagnostic flow: `BarycentricMapping` present → ensure parent node has `TetrahedronSetTopologyContainer` or `HexahedronSetTopologyContainer` (not `TriangleSetTopologyContainer`). Also flag scale mismatch between parent and child meshes.
- Insight: Reinforces Agent 4 pattern #12 but adds the *error-message signature* a regex can match.

### F7. AttachConstraint requires matching DOF templates
- Link: https://github.com/sofa-framework/sofa/discussions/2735
- Summary: AttachConstraint between `Rigid3d` and `Vec3d` MOs throws `Link name 'mechanicalStates' already used` or silently no-ops. Working alternatives: `BilateralInteractionConstraint` with mapped interaction points, or `MechanicalMatrixMapper` to rigidify a subset.
- Diagnostic flow: scene contains `AttachConstraint` with `object1` and `object2` of different MO templates → flag.
- Insight: New smell test `attach_constraint_template_mismatch`. Cheap, structural.

### F8. IdentityMultiMapping concatenation node must NOT carry its own ODE solver
- Link: https://github.com/sofa-framework/sofa/discussions/2738
- Summary: The node holding the merged DoFs should be a sibling under a parent that owns the `EulerImplicitSolver`/`CGLinearSolver`; placing solvers inside the concatenation node breaks multimapping evaluation.
- Diagnostic flow: scene has `*MultiMapping` (Identity, Subset, Beam, Rigid) AND the *output* node also has its own ODE solver → flag.
- Insight: New smell test `multimapping_node_has_solver`.

### F9. SoftRobots `getObject()` is deprecated; SoftRobots issues belong in their own repo
- Link: https://github.com/sofa-framework/sofa/discussions/2689
- Summary: Maintainer redirected to SofaDefrost/SoftRobots. Useful nugget: `stlib3.getObject` is deprecated since v21.12.
- Diagnostic flow: complaint "SoftRobots example errors" → grep Python for `getObject(`; recommend `node.getChild()` / direct attribute access.
- Insight: Lightweight playbook row only.

### F10. `printLog` visibility is inconsistent; some plugins ship their own MessageHandler
- Link: https://github.com/sofa-framework/sofa/discussions/2913
- Summary: Reinforces Agent 1's M4 — `printLog` semantics drift; the multithreading plugin in particular is "experimental, without any guarantee."
- Diagnostic flow: when `log_solvers=True` and stdout is empty after one step, also try `Sofa.Helper.MessageHandler.setMainHandler(StdoutMessageHandler())` before `init()`.
- Insight: Concrete reinforcement of Agent 1's regression-test recommendation.

## Recommended additions

### New smell tests (high-confidence, all structural / pre-step)
1. `freemotion_without_constraintcorrection` (F1)
2. `topology_changing_with_static_indices` (F3)
3. `attach_constraint_template_mismatch` (F7)
4. `multimapping_node_has_solver` (F8)
5. `barycentricmapping_surface_parent` (F6)

### New playbook rows
- "only the first articulation/joint moves" → check `ArticulationCenter` parent/child indices (F2)
- "haptic device produces no force" → check for `LCPForceFeedback` node (F5)
- "scene crashes mid-run after carving/tearing" → check index Data types (F3)
- "BarycentricMapping errors about Vec3d input" → parent topology probably surface-only (F6)
- "AttachConstraint silently does nothing" → DOF template mismatch (F7)

## Contradictions / refinements vs spec and Agents 1/4

- **Refines Agent 1 M6** (`low_forces` per-FF unavailable): F4 shows that *constraint* forces ARE uniformly extractable via the `constraintForces` Data on the constraint solver when `computeConstraintForces=1`. Recommend the spec drop per-FF elastic forces (per Agent 1) but ADD a per-contact magnitude rule fed by constraint-solver output.
- **Reinforces Agent 1 M4** (printLog semantics): F10 — also set the `MessageHandler` sink, not just `printLog`/`verbose`.
- **No outright contradictions** with the spec. F1 and F8 are net-new structural rules the spec did not anticipate, both very cheap (pure scene-graph walks before stepping).

## Coverage notes

- "Share your achievements" / "Show and Tell" categories are mostly publication/release announcements with low diagnostic content; the one debugging-relevant entry (multi-sim parallel, #3907) overlaps with F10 on threading caveats.
- "Ideas/Suggestions" is forward-looking feature requests; the only diagnostic gold was #3812 (F4) and #4713 (suction cup → "wait for the plugin").
- Older "Write/Run a simulation" threads (Feb–Jun 2022) are the richest seam; F1, F2, F6, F7, F8 all came from this 5-month window.
