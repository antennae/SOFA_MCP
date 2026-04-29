# Rule 6 — ForceField Mapping: Pre-implementation Review

**Date:** 2026-04-26
**Rule under review:** "every `ForceField` must live in a node that has a `MechanicalObject`."
**Sources read:** `ForceField.h`, `BaseForceField.cpp`, `SingleStateAccessor.inl`, `PairStateAccessor.h`, `PairInteractionForceField.h`, `Node.cpp`, `BaseContext.cpp`, plugin cache (67 FF classes).

---

## 1. Mechanistic explanation

### How a ForceField links to its mstate

`ForceField<T>` inherits `SingleStateAccessor<T>`, which holds a `SingleLink<..., MechanicalState<T>>` named `mstate`. During `init()`:

```cpp
// SingleStateAccessor.inl — called at Sofa.Simulation.init()
if (!mstate.get())
{
    mstate.set(dynamic_cast<MechanicalState<DataTypes>*>(
        getContext()->getMechanicalState()));   // <- context lookup

    if (!mstate)
        msg_error() << "No compatible MechanicalState found in the current context.";
}
```

`getContext()->getMechanicalState()` calls `Node::getMechanicalState()`:

```cpp
// Node.cpp:662
core::behavior::BaseMechanicalState* Node::getMechanicalState() const
{
    if (this->mechanicalState)
        return this->mechanicalState;          // same-node first
    else
        return get<core::behavior::BaseMechanicalState>(SearchParents); // WALKS UP
}
```

**Critical finding:** `getMechanicalState()` walks up the ancestor chain if no MO is on the current node. This means a ForceField on a child node **can silently bind to the parent's MO** — it does not always error at init. The error only fires when **no MO exists anywhere in the ancestor path** and no explicit `mstate` link is given.

### `canCreate` check at factory time

`ForceField<T>::canCreate` (called before init, during `addObject`) also calls `context->getMechanicalState()`, which uses the same ancestor-walking logic. So `canCreate` also succeeds if the MO is in a parent.

### Pre-construction check (`_assert_required_components`)

The current `_assert_required_components` in `scene_writer.py` does not check Rule 6 at all — it only checks for animation loop, constraint solver, time integration, and linear solver. Rule 6 would be a new check in `_build_summary_wrapper`.

---

## 2. Edge cases

### Mapped subtree (most important)

**Canonical SOFA pattern (from `liver.py`, `springForceField.py`):**

```
/Liver
  MechanicalObject (dofs)          ← MO lives here
  TetrahedralCorotationalFEMForceField   ← FF in same node: Rule 6 satisfied
  /Visu
    OglModel
    BarycentricMapping (input=@../dofs, output=@VisualModel)
  /Surf
    MechanicalObject (spheres)     ← mapped child MO
    SphereCollisionModel
    BarycentricMapping
```

In `/Surf`, there *is* a MO (`spheres`). If a FF were placed here, it would bind to that MO — legitimate.

But what about a node with only a visual Mapping and no MO?

```
/Visu
  OglModel
  BarycentricMapping
  # No MO here
```

If a FF were added to `/Visu`, `Node::getMechanicalState()` walks up and finds `/Liver`'s MO. SOFA `canCreate` succeeds. This is technically valid but unusual — the FF forces are applied to the parent's MO DOFs. The rule as stated ("must live in a node that has a `MechanicalObject`") would false-positive on this case.

**However:** placing structural FFs (FEM, spring) on visual-only nodes is almost always a scene authoring error. The FF acts on the parent MO, but the FEM topology is likely in the parent too — the check catches a legitimate structural smell even if SOFA doesn't reject it.

**Verdict for the rule wording:** Loosen from "same node" to "same node OR parent" would accept essentially all scenes (since SOFA itself accepts them). The useful check is: **does a FF exist on a node whose nearest MO is not a mechanical simulation node** (i.e., it's a visual-only or mapped visual node)?

This is complex to detect statically in Python. A simpler, more reliable formulation:

> Flag any ForceField on a node that contains no MechanicalObject **and** also contains a visual component (`OglModel`, `VisualModel`) but no Mapping pointing to a mechanical parent.

Even simpler and practically effective: **flag ForceField on a node that has no co-located MechanicalObject and no Mapping.** Nodes with Mapping are mapped subtrees (legitimate); nodes without either are almost certainly errors.

### PairInteractionForceField (SpringForceField, MeshSpringForceField, etc.)

`SpringForceField` extends `PairInteractionForceField<T>` extends `PairStateAccessor<T>`, which holds **two** MO links (`object1`, `object2`). These FFs can live at a common ancestor node and reference MOs in sibling children (as shown in `SpringForceField.py` test: FF added to root, MOs in `/plane_1` and `/plane_2`).

`PairStateAccessor::init()` also falls back to `getContext()->getMechanicalState()` if no explicit link is given — which on a root-level placement finds nothing and errors. But in practice, these FFs always have `object1`/`object2` explicitly specified. `PairInteractionForceField::canCreate` explicitly requires `object1` and `object2` to resolve to valid MOs.

**Rule 6 as stated ("must live in a node that has a MechanicalObject") misfires here:** `SpringForceField` placed at root with `object1=@/plane_1/mo` and `object2=@/plane_2/mo` has no MO on root — but it is correct.

This is a **confirmed false positive** for `PairInteractionForceField` subclasses.

### MixedInteractionForceField (InteractionEllipsoidForceField)

Same as PairInteractionForceField — two linked MOs in different nodes. Same false positive risk.

### MultiMapping output nodes (Rule 12 territory)

A `SubsetMultiMapping` output node may carry a ForceField targeting its own MO. The MO is present in that node — Rule 6 passes correctly.

---

## 3. Class enumeration (67 ForceField classes)

Three structural groups:

**Group A: Single-MO (`ForceField<T>` subclasses) — 58 classes**
All standard FEM, spring, pressure, gravity-style FFs. Rule 6 applies: they need an MO in context.
Examples: `TetrahedronFEMForceField`, `ConstantForceField`, `PlaneForceField`, `RestShapeSpringsForceField` (confirmed `ForceField<T>`).

**Group B: PairInteractionForceField subclasses — exempted**
`SpringForceField`, `MeshSpringForceField`, `RegularGridSpringForceField`, `JointSpringForceField`, `GearSpringForceField`, `PolynomialSpringsForceField`, `VectorSpringForceField`, `FrameSpringForceField`, `ParallelSpringForceField`, `ParallelMeshSpringForceField`, `RepulsiveSpringForceField`, `AngularSpringForceField`, `PenalityContactForceField`.

These carry `object1`/`object2` links and can live at a common ancestor without a local MO. **Exempt from Rule 6.**

**Group C: MixedInteractionForceField subclasses — exempted**
`InteractionEllipsoidForceField`. Same exemption as Group B.

**Group D: Ambiguous — check by class name**
`BeamHookeLawForceField`, `BeamHookeLawForceFieldRigid` — beam FFs, but they target a single beam MO. No exemption needed.

Detection heuristic: classes that register with `object1`/`object2` data fields at creation time can be identified at the Python tree-walk level by checking `obj.getData('object1')`.

---

## 4. Sample scenes

### Canonical (should NOT trigger)

**C1 — Standard FEM node:**
```python
body = root.addChild('Body')
body.addObject('MechanicalObject', ...)
body.addObject('TetrahedronFEMForceField', ...)    # same-node MO: OK
```

**C2 — SpringForceField at root (cross-node, PairInteraction):**
```python
root.addObject('SpringForceField', object1='@/plane_1/mo', object2='@/plane_2/mo', ...)
# Root has no MO, but this is PairInteraction: exempt
```

**C3 — FF on mapped child with its own MO:**
```python
# /Surf has its own MechanicalObject (spheres) + BarycentricMapping
surf.addObject('MechanicalObject', name='spheres', ...)
surf.addObject('SphereCollisionModel', ...)
surf.addObject('BarycentricMapping', ...)
# If a FF were placed here, it targets spheres MO: OK
```

### Violations (should trigger)

**V1 — FF in visual-only node (no MO, no Mapping):**
```python
visu = body.addChild('Visu')
visu.addObject('OglModel', ...)
visu.addObject('TetrahedronFEMForceField', ...)   # ERROR: no MO, no Mapping
```
SOFA silently binds to parent's MO; behavior is correct but placement is wrong. Rule 6 fires.

**V2 — FF in root with no MO and no explicit link (single-MO type):**
```python
root.addObject('RestShapeSpringsForceField', ...)  # no MO in root or ancestors
```
`SingleStateAccessor::init()` emits `msg_error` at init time. Rule 6 fires as a pre-check.

**V3 — FF in orphan node (no MO anywhere in ancestor chain, no Mapping):**
```python
orphan = root.addChild('Orphan')
orphan.addObject('ConstantForceField', totalForce=[0,-9.81,0])  # no MO anywhere above
```
SOFA errors at init. Rule 6 fires.

---

## 5. Severity verdict

**Severity: `warning`** (not `error`), for the following reasons:

1. **Covered by init-time errors (mostly):** When no MO exists in the ancestor chain at all, SOFA's `init()` emits `msg_error` at runtime. Rule 6 as a pre-step structural check catches this earlier and with a clearer message.
2. **Not always an init-time error:** When a FF is on a visual-only child and the parent has a MO, `Node::getMechanicalState()`'s ancestor walk silently succeeds. SOFA doesn't error — it just applies forces to the parent's MO. This is a structural confusion, not caught at init, making Rule 6 **genuinely additive** for this class of bugs.
3. **Not a guaranteed crash:** The scene may still run (case: ancestor walk finds parent MO), so `error` severity is too strong. `warning` is correct.

For V2/V3 (truly no MO anywhere): severity can be promoted to `error` if the tree walk shows zero ancestor MOs.

---

## 6. Final rule wording

**Rule 6 — ForceField Mapping (revised):**

> For every component whose class name ends in `ForceField` (from the registered class list):
> - **Exempt** if the component has a non-empty `object1` data field (PairInteractionForceField / MixedInteractionForceField). These carry explicit MO links and may legitimately live at a common ancestor node.
> - **Otherwise (single-MO):** Check that the node or any ancestor node contains a `MechanicalObject`. If no MO exists in the ancestor chain: **error**. If an MO exists only in an ancestor but the current node is a visual-only node (contains `OglModel` or `VisualModel`): **warning** (structural confusion — FF probably belongs one level up).

Detection in `_build_summary_wrapper` tree walk:
1. For each node, collect all FF objects.
2. For each FF, call `obj.getData('object1')` — if non-null and non-empty, skip (PairInteraction).
3. Walk up ancestor path from `nodes[]` list to find nearest MO.
4. If none: emit `error`. If MO is in ancestor and node has visual component: emit `warning`.

---

## 7. Confidence verdict

**High confidence** on:
- The ancestor-walk mechanism (directly read from `Node::getMechanicalState()` source).
- PairInteractionForceField false-positive risk (directly read from `PairStateAccessor.h` and confirmed in `SpringForceField.py` test scene).
- Error message text: `"No compatible MechanicalState found in the current context."` (from `SingleStateAccessor.inl`).
- Class breakdown: 67 registered FFs, all Group A subclass `ForceField<T>` except the spring cross-node types.

**Medium confidence** on:
- The `getData('object1')` detection approach for PairInteraction at Python tree-walk time — this works at SOFA object level but needs testing with the actual SofaPython3 binding.
- The "visual-only node" heuristic — it catches the most common confusion but could misfire on unusual scene structures.

**Recommended action before implementation:** add one fixture test confirming that `SpringForceField` at root with `object1`/`object2` does not trigger Rule 6, and one confirming that `TetrahedronFEMForceField` on a node without MO (V2 pattern) does trigger it.
