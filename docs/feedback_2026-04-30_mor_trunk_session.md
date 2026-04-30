# MCP feedback — kPCA-MOR trunk-scene authoring session, 2026-04-30

Real-world dogfooding: used the SOFA MCP from a Claude Code session in
`~/workspace/sofa` to author a 4-cable soft trunk scene for kPCA Model
Order Reduction experiments. Final output: `~/workspace/MOR/scene/trunk/trunk.py`,
validates and runs 100 steps under gravity (max tip displacement 113 mm,
solver converges in 2 NNCG iterations consistently).

Tools exercised: `health_check`, `search_sofa_components`, `resolve_asset_path`,
`mesh_stats`, `find_indices_by_region`, `get_plugins_for_components`,
`query_sofa_component` (via skill), `summarize_scene`, `validate_scene`,
`write_scene`, `diagnose_scene`, `render_scene_snapshot`.

---

## What worked well

1. **`validate_scene`** — caught the `GenericConstraintSolver` deprecation
   with the *exact* migration message (telling me to use
   `NNCGConstraintSolver`, `BlockGaussSeidelConstraintSolver`, etc.).
   This is the single most valuable tool in the kit. Real save.

2. **`summarize_scene`** — cheap pre-validate health-rule check is a
   good intermediate gate. Calling it with a partial draft caught the
   deprecation before paying for full SOFA init.

3. **`diagnose_scene`** — high-value combo of health rules + per-MO
   metrics (max disp, max force, NaN-first-step) + solver iteration
   counts. Confirmed the trunk physically does what I expect (113 mm
   sag, no NaN) before I committed to running the full ROM pipeline
   on it.

4. **`mesh_stats`** — instant bbox + topology kind from a path.
   Returned `{bbox: [-13,-12.7,0]→[13,12.8,195], volumetric}` from the
   trunk.vtk in <1s. Saved opening the file by hand.

5. **`render_scene_snapshot`** — offscreen PyVista PNG-out worked
   (no display server required). However, see bug 9 below — the
   rendered geometry is wrong.

6. **Schema-on-demand pattern** — only paying for schemas of tools I
   actually call keeps the deferred-tool list manageable. Worked fine
   with `ToolSearch` / `select:`.

---

## Real bugs

### 1. `find_indices_by_region` fails on `.vtk`

```
input:  file_path="/.../trunk.vtk", axis="z", mode="min", tolerance=20
output: {"success": false, "error": "Could not extract vertices from file."}
```

VTK is a primary SOFA mesh format. For ROM workflows where I need
exact tip-vertex or fixed-end-vertex indices (not just a bounding
box), this would block. I worked around with in-scene `BoxROI`, but
that's not always equivalent — sometimes the pipeline needs the index
list at *script-author* time (e.g. for trajectory-comparison code that
slices into `position.value`).

**Severity:** medium. Fallback exists but it's a coverage gap on a
core format.

### 2. `get_plugins_for_components` returns "not found" for valid components

```
input:  ["GenericConstraintSolver", "RequiredPlugin", ...other 14...]
output: {
  "GenericConstraintSolver": "Component not found in cache",
  "RequiredPlugin": "Component not found in cache",
  ...everything else resolves correctly...
}
```

- `GenericConstraintSolver` was deprecated in v25.12 but the cache
  should still know it lives in `Sofa.Component.Constraint.Lagrangian.Solver`
  (or at least flag it as deprecated rather than missing).
  Misleading vs. `validate_scene`'s clean migration message.
- `RequiredPlugin` is meta — fair to not have a plugin for it, but
  "not found" is the wrong signal. Should be a separate "meta-component"
  category or just silently skipped.

**Severity:** low (doesn't block — `validate_scene` catches the real
issue), but inconsistent UX between this tool and the validator.

### 3. `write_scene` ASCII-encodes content

```
input:  script_content has em-dash (—) in a docstring
output: Error: 'ascii' codec can't encode character '—' in position 28
```

Should default to UTF-8. Python source files are UTF-8 by default per
PEP 3120; ASCII-only is unexpected. Worked around by replacing em-dashes
with hyphens, but that's the kind of thing an LLM agent will hit *constantly*
because we naturally produce em-dashes / unicode in docstrings.

**Severity:** medium. Affects every multi-paragraph docstring an
agent writes.

### 10. `run_and_extract` response misreports `data_shape`

```
input:  steps=10, field=position, node_path=/Simulation/Trunk/dofs
response: {"data_shape": [709, 3], ...}
actual JSON file: {"data": shape (10, 709, 3)}
```

The `data_shape` in the response describes only the *last* frame
(N×3), but the saved JSON correctly stores the full trajectory
(T×N×3). The naming is misleading — an agent reading the response
might believe only one frame was saved and try to re-run with
different parameters, when in fact the trajectory is already there.

**Suggested fix:** rename to `trajectory_shape` or `data_shape: [T, N, 3]`
in the response. Or include both `last_frame_shape` and
`trajectory_shape` for clarity.

**Severity:** low. File contents are correct; the response
description just doesn't match.

### 9. `render_scene_snapshot` renders convex hull, not mesh geometry

The output PNG shows a smooth lozenge envelope of the trunk MOs'
point clouds, NOT the actual trunk surface mesh (tetrahedra surface
or OglModel triangles). Looks like PyVista is being handed raw
positions with no topology, so it falls back to point-cloud →
convex-hull rendering. Cable subnodes' point clouds also get rolled
into the hull, distorting the apparent shape further.

**Suggested fix:** the renderer should:
- pull `MeshTopology` triangles/tetrahedra from the same node as the
  MO and use `pyvista.UnstructuredGrid` with explicit cells, OR
- use the sibling `OglModel`'s loaded `.stl` or surface mesh directly,
  OR
- if neither topology is available, fall back to point cloud
  (`render_points_as_spheres=True`) with a warning rather than silent
  convex hull.

**Severity:** medium-high. The render tool is supposed to enable
visual sanity checks ("did gravity pull the right way?") but a
convex-hull render of a trunk + 4 cable polylines obscures the actual
deformation — exactly the thing you want to see.

---

## False-positive health rules (Rule 7)

### 4. `MeshTopology` from `.vtk` flagged as non-volumetric

```
summarize_scene response (and diagnose_scene anomaly):
{
  "rule": "rule_7_topology",
  "severity": "error",
  "subject": "/root/Simulation/Trunk",
  "message": "'TetrahedronFEMForceField' requires a volumetric topology
   container (TetrahedronSetTopologyContainer / HexahedronSetTopologyContainer
   / MeshTopology from .vtk|.msh|.vtu / 3D RegularGridTopology) in scope."
}
```

The Trunk node has `MeshVTKLoader -> MeshTopology(src='@loader')`. The
rule message itself acknowledges "`MeshTopology` from .vtk|.msh|.vtu"
as valid — but the check apparently doesn't follow the loader to
inspect its filename extension. SOFA actually initializes the scene
fine.

### 5. `BarycentricMapping` flagged as non-volumetric parent on cable subnodes

```
{
  "rule": "rule_7_topology",
  "severity": "error",
  "subject": "/root/Simulation/Trunk/cable3",
  "message": "BarycentricMapping's parent node is neither volumetric
   nor a shell FEM (TriangularFEMForceField / QuadBendingFEMForceField)."
}
```

The cable subnode has a `BarycentricMapping` that maps from cable-routing
waypoints up to the **trunk parent's** volumetric topology. This is the
canonical SoftRobots cable pattern (see
`SoftRobots/examples/tutorials/Trunk/trunk.py:88`). The rule appears to
check the cable subnode itself, not its parent.

**Severity for both:** medium — these *will* cause user confusion. The
agent (me) read the rule failures, then second-guessed itself, then
ran `validate_scene` to override the summary's verdict. A user without
the `validate_scene` reflex might rewrite a perfectly working scene.

**Suggested fix:** rule 7's check should resolve `MeshTopology.src`
to its loader and inspect the filename, AND walk *up* the node chain
from a `BarycentricMapping` to find the topology, not just check the
mapping's own subnode.

---

## Ergonomic friction

### 6. `diagnose_scene` solver_logs are extremely verbose

The `solver_logs` field returns the full SOFA stdout, including
~2700+ lines of f-vector dumps from `EulerImplicitSolver`'s
`printLog`-style output. The convergence summary at the end (`NNCGConstraintSolver
Convergence after 2 iterations`) is what I actually wanted; the f-vectors
were noise for diagnostic purposes.

**Suggested fix:** add `verbose: false` mode that filters to:
- plugin load lines
- solver convergence/non-convergence lines
- any `[ERROR]` / `[WARNING]` lines
- last N lines if non-convergence detected

The full log can stay opt-in for deep debugging.

### 7. Rule 9 acknowledged correct, but rule 7 simultaneously errored

Rule 9 (units) returned `"ok"` while rules 4 and 7 disagreed about
whether the same scene is valid. The summary read "5 oks, 2 errors"
and the errors were both false positives. A user has to read each rule
*name* and decide which to trust. Suggested: severity scaling, or a
top-level `verdict` field that excludes rules with known false-positive
shapes when the validator agrees the scene works.

### 8. SKILL.md doesn't cover `claude mcp add` registration

The skill assumes the agent already has the MCP registered. In our
session I had to figure out:
1. `claude mcp add --transport http sofa-mcp http://127.0.0.1:8000/mcp`
2. The first attempt registered to the *wrong project scope*
   (running the command from `~/workspace/SOFA_MCP` registered it
   only for that project; needed to re-run from this session's cwd
   or use `--scope user`).
3. After registering, `/mcp` reconnect was needed to surface tools.

This is the new-user onramp. Worth a short "Bootstrap & registration"
section at the very top of SKILL.md, or a separate `references/cc-registration.md`.

---

## Workflow observations

- The `summarize_scene` → fix → `validate_scene` → `write_scene`
  loop matches how an LLM naturally drafts: cheap structural checks
  before paying for runtime checks. SKILL.md prescribes this flow
  and it does match how I worked.

- Calling tools in parallel was fine (e.g. simultaneous
  `health_check` + `search_sofa_components` + `resolve_asset_path`).
  No race / state issues observed.

- The plugin-load log on every `validate_scene` is reassuring — I
  could see exactly which `.so` files got pulled in, which would help
  diagnose `RequiredPlugin` mistakes faster than a typical SOFA
  traceback would.

---

## Suggested follow-up improvements (priority order)

1. **Fix rule 7 false positives** (4, 5) — agents will second-guess
   correct scenes.
2. **`write_scene` UTF-8** (3) — every long docstring will hit this.
3. **`find_indices_by_region` VTK support** (1) — coverage gap on a
   primary format.
4. **`diagnose_scene` verbose flag** (6) — output is currently
   ~10× larger than it needs to be.
5. **`get_plugins_for_components` deprecated/meta handling** (2) —
   minor, but inconsistent with validator's behavior.
6. **SKILL.md registration section** (8) — onboarding.

---

## Bottom line

The MCP is **net positive** for this workflow — `validate_scene` and
`diagnose_scene` together caught the deprecation + verified physics in
two calls, work that would have been ~5 manual cycles otherwise.
Friction is concentrated in (a) the false-positive health rules and
(b) the verbose log volume. None of the bugs blocked the task; all
were workaround-able. The end-to-end loop (clarify -> resolve plugins ->
draft -> summarize -> validate -> write -> diagnose -> render) is a real
workflow improvement over hand-authoring.

---

## Usefulness assessment (agent perspective)

**Question asked:** Is this MCP useful, or does the agent already know
enough that it's redundant?

### Where the MCP is genuinely load-bearing (i.e. the agent CAN'T know)

1. **Version drift.** The agent's training data has a knowledge cutoff;
   SOFA evolves. In this session I'd have written `GenericConstraintSolver`
   from memory and shipped it; `validate_scene` caught the v25.12
   deprecation with the exact migration message
   (`-> NNCGConstraintSolver`). One call saved a debug cycle that would
   have surfaced as an obscure factory error.

2. **Local build state.** "Does this user's SOFA build have plugin X?"
   "What plugins are installed?" "What `Data` fields does the local
   `CableConstraint` expose?" The agent can't know without probing the
   filesystem or running SOFA. `query_sofa_component` /
   `get_plugins_for_components` answer these directly.

3. **Mesh-specific facts.** Bbox, topology kind, vertex counts of *this*
   user's mesh files. Without `mesh_stats` I'd have to open the file
   manually or run a separate Python probe.

4. **Behavioral confirmation.** "Does the scene actually init and step?"
   is fundamentally a runtime question. `validate_scene` packages it as
   a bool + structured stdout, which is much better signal than parsing
   `runSofa` stderr.

### Where the agent has enough knowledge already

5. **Component class names + plugin name conventions.** I knew
   `TetrahedronFEMForceField`, `BoxROI`, `FixedProjectiveConstraint`,
   `MeshVTKLoader`, etc. from training data + the upstream Trunk
   reference scene I'd already read. `search_sofa_components` gave the
   same info but I could have produced it from memory in this case.

6. **Scene structure patterns.** FreeMotion + ConstraintSolver +
   ConstraintCorrection + per-subtree ODE/linear solver — I had this
   from training. The Health Rules in SKILL.md were a good *cross-check*
   but didn't teach me anything I didn't have.

7. **Unit conventions.** mm/g/s vs SI — I had this from prior MOR work.
   Rule 9's automatic detection is nice but not load-bearing.

### Estimated efficiency multiplier

- For an agent with strong prior SOFA knowledge: roughly **2-3x** on
  scene authoring. The validator + diagnose tools save real cycles by
  packaging "did this work?" into one call.
- For an agent learning SOFA from scratch (or from a stale knowledge
  cutoff): **much higher**. The Health Rules and tool reference in
  SKILL.md are themselves educational; the validator's deprecation
  messages are pedagogically useful.
- For a non-LLM user: the value-add is smaller — most of these checks
  exist in `runSofa` + reading source already.

### What would push the multiplier higher

- Coverage on mesh tools (rule-7 false positives, VTK in
  `find_indices_by_region`) -- because mesh-handling is *exactly* where
  agents lack domain knowledge.
- Render that shows actual geometry -- visual feedback is a strong
  signal an LLM can't generate from text alone.
- The verbose-log filter -- by default the diagnose tool's output is
  large enough to noticeably eat context window in a long session.

### What I would NOT add

- More natural-language reformulations of what the agent could grep
  itself.
- Tools that just wrap `runSofa <file.py>` without adding structure
  to the result.
- Expansive tutorial-style helpers — agents prefer "answer me
  programmatically" over "guide me through a workflow".

### Honest one-line summary

The MCP is most valuable as a **runtime/validation oracle**: things
the agent can't know without executing. Component lookup is helpful
but secondary. Keep the validator + diagnose path as the load-bearing
features and the tool stays useful even as model capabilities improve.
