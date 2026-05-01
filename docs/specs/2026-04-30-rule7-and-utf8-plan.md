# Phase 6.3 #1 + #2 — Rule 7 false positives + `write_scene` UTF-8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two field-feedback bugs from the MOR-trunk dogfood session: `summarize_scene` rule 7 mis-flags `MeshTopology(src='@loader')` from `.vtk` and `BarycentricMapping` whose volumetric parent is loader-fed; `write_scene` fails on em-dashes in the script content because `open()` defaults to locale (ASCII) encoding.

**Architecture:** Both bugs are one-line / one-helper fixes. #2 is the same pattern that landed at `scene_writer.py:149,203` for `validate_scene` and `summarize_scene` tempfiles — apply it to `write_scene`'s output file. #1 has a single root cause (`_node_is_volumetric` doesn't follow `MeshTopology.src` to its loader); fixing that resolves both reported false positives because the BarycentricMapping rule already walks up to the parent — it just got "False" from an incomplete volumetric check.

**Tech Stack:** Python 3.12, SofaPython3 v24.12, pytest, the existing `_summary_runtime_template.py` runtime + `test_summarize_rules.py` test harness.

---

## Context

From `docs/feedback_2026-04-30_mor_trunk_session.md`:

- **Bug 4 (rule 7A):** A `Trunk` node has `MeshVTKLoader` + `MeshTopology(src='@loader')`. `_node_is_volumetric` reads `MeshTopology.filename`, which is empty in this pattern (the file is on the loader). Result: rule 7A fires `error` even though SOFA initializes the scene fine.
- **Bug 5 (rule 7B):** A cable subnode has `BarycentricMapping` whose parent is `Trunk`. The rule already walks up to `Trunk` via `parent_map`, but `_node_is_volumetric(Trunk)` returns `False` for the same reason as Bug 4. Same root cause.
- **Bug 3 (`write_scene` UTF-8):** `open(output_path, "w")` uses locale default. The FastMCP server resolves to ASCII, so any em-dash (U+2014) or other unicode in the script content raises `UnicodeEncodeError`. Mirror the `encoding="utf-8"` fix that already landed in `scene_writer.py:149,203`.

## File Structure

| Path | Action | Why |
|---|---|---|
| `sofa_mcp/architect/_summary_runtime_template.py` | modify `_node_is_volumetric` (lines 411-428); add `_resolve_topology_filename` helper near line 408 | Single root-cause fix for both rule-7 false positives |
| `sofa_mcp/architect/scene_writer.py` | modify `write_scene` (line 318) | Add `encoding="utf-8"` to output file open |
| `test/test_architect/test_summarize_rules.py` | add 2 tests near the existing rule-7 cluster (line 388) | Cover both false-positive shapes from the user's session |
| `test/test_architect/test_scene_writer.py` | add 1 test near the existing `test_write_scene_writes_file` (line 45) | Cover em-dash UTF-8 round-trip through `write_scene` |
| `docs/feedback_2026-04-30_mor_trunk_session.md` | mark items 1, 2, 3 (rule 7 + write_scene) resolved | Bookkeeping |
| `docs/plan.md` Phase 6.3 table | mark items #1, #2 shipped | Bookkeeping |
| `docs/progress.md` | new entry "Phase 6.3 #1 + #2" | History |

---

## Task 1: `write_scene` UTF-8 fix (item #2 — quick win first)

**Files:**
- Modify: `sofa_mcp/architect/scene_writer.py:318`
- Test: `test/test_architect/test_scene_writer.py`

- [ ] **Step 1: Write the failing test**

Add this test method to the `TestSceneWriter` class in `test/test_architect/test_scene_writer.py` (after `test_write_scene_writes_file`):

```python
    def test_write_scene_handles_utf8_in_docstring(self):
        # Em-dash (U+2014) and other unicode in a docstring used to crash
        # write_scene with 'ascii' codec can't encode... — see docs/feedback_2026-04-30.
        script = '''
def createScene(rootNode):
    """Soft trunk scene — uses cable actuators."""
    rootNode.addObject("RequiredPlugin", pluginName="Sofa.Component.StateContainer")
    rootNode.addObject("MechanicalObject", position=[0, 0, 0])
'''
        output_file = "utf8_scene.py"
        try:
            result = write_scene(script, output_file)
            self.assertTrue(result["success"], f"Failed with: {result.get('error')}")
            with open(output_file, "r", encoding="utf-8") as f:
                contents = f.read()
            self.assertIn("Soft trunk scene — uses cable actuators.", contents)
        finally:
            if os.path.exists(output_file):
                os.remove(output_file)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `~/venv/bin/python -m pytest test/test_architect/test_scene_writer.py::TestSceneWriter::test_write_scene_handles_utf8_in_docstring -v`

Expected: depends on the tester's locale — if their `LANG`/`LC_ALL` is UTF-8 the test will spuriously pass without the fix; on the FastMCP server process or in ASCII locales it fails with `UnicodeEncodeError`. To force the failure mode reliably:

```bash
LC_ALL=C ~/venv/bin/python -m pytest test/test_architect/test_scene_writer.py::TestSceneWriter::test_write_scene_handles_utf8_in_docstring -v
```

Expected with `LC_ALL=C`: FAIL with `UnicodeEncodeError: 'ascii' codec can't encode character '—'`.

- [ ] **Step 3: Apply the fix**

Modify `sofa_mcp/architect/scene_writer.py` line 318:

```python
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(create_scene_function)
```

- [ ] **Step 4: Run the test to verify it passes (in both locales)**

Run:
```bash
~/venv/bin/python -m pytest test/test_architect/test_scene_writer.py::TestSceneWriter::test_write_scene_handles_utf8_in_docstring -v
LC_ALL=C ~/venv/bin/python -m pytest test/test_architect/test_scene_writer.py::TestSceneWriter::test_write_scene_handles_utf8_in_docstring -v
```

Expected: PASS in both. The `LC_ALL=C` run is what the FastMCP server hits in production.

- [ ] **Step 5: Commit**

```bash
git add sofa_mcp/architect/scene_writer.py test/test_architect/test_scene_writer.py
git commit -m "$(cat <<'EOF'
write_scene: encode output as UTF-8

Phase 6.3 #2. write_scene's open() used the locale default; the FastMCP
server process resolves that to ASCII, so any em-dash in the script
content crashed with UnicodeEncodeError. Mirror the encoding="utf-8" fix
that already lives at scene_writer.py:149,203 for the validate/summarize
tempfiles. Test forces LC_ALL=C to reproduce the server-side failure.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Rule 7 — follow `MeshTopology.src` to its loader

This is the substantive fix. Adds one helper, modifies one function, adds two test cases. Resolves both Bug 4 and Bug 5 with one root-cause change.

**Files:**
- Modify: `sofa_mcp/architect/_summary_runtime_template.py` (add helper near line 408, modify `_node_is_volumetric` at lines 411-428)
- Test: `test/test_architect/test_summarize_rules.py` (after line 411)

- [ ] **Step 1: Write the first failing test (Bug 4 — `MeshTopology(src='@loader')` from `.vtk`)**

Add this test to `test/test_architect/test_summarize_rules.py` after `test_rule_7_edge_barycentric_with_shell_fem_parent` (around line 412):

```python
def test_rule_7_meshtopology_src_link_to_vtk_loader_is_volumetric():
    """Regression: MeshTopology(src='@loader') with a sibling MeshVTKLoader
    pointing at a .vtk file should NOT trigger rule 7. The previous check
    only looked at MeshTopology.filename and missed the src-link pattern.
    Verbatim from docs/feedback_2026-04-30 bug 4."""
    plugins = list(P_BASE) + [
        "Sofa.Component.IO.Mesh",                       # MeshVTKLoader
        "Sofa.Component.Topology.Container.Constant",   # MeshTopology
    ]
    # Use any .vtk fixture in the repo. meshes/prostate.vtk exists.
    import os
    vtk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "meshes", "prostate.vtk"))
    assert os.path.exists(vtk_path), "test depends on meshes/prostate.vtk fixture"
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(plugins)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MeshVTKLoader", name="loader", filename={vtk_path!r})
    body.addObject("MeshTopology", src="@loader")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("TetrahedronFEMForceField", youngModulus=1000, poissonRatio=0.3)
'''
    checks = _checks(_summarize(script))
    rule_7_errors = [c for c in checks if c["rule"] == "rule_7_topology" and c["severity"] == "error"]
    assert not rule_7_errors, (
        f"MeshTopology(src='@loader') from .vtk should be detected as volumetric; "
        f"got {rule_7_errors}"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `~/venv/bin/python -m pytest test/test_architect/test_summarize_rules.py::test_rule_7_meshtopology_src_link_to_vtk_loader_is_volumetric -v`

Expected: FAIL with at least one `rule_7_topology` error from `TetrahedronFEMForceField` requiring volumetric topology.

- [ ] **Step 3: Add the `_resolve_topology_filename` helper**

Insert this helper into `sofa_mcp/architect/_summary_runtime_template.py` directly before the `_node_is_volumetric` function (around line 410, between `_SHELL_FEM_CLASSES` and `_node_is_volumetric`):

```python
def _resolve_topology_filename(obj):
    """For a MeshTopology-like component, return the file it loads from.

    Two patterns:
      1. Direct: `MeshTopology(filename="...")` — return the filename Data.
      2. Via loader: `MeshTopology(src="@loader")` paired with a sibling
         MeshVTKLoader/MeshOBJLoader/MeshGmshLoader. Scan sibling objects in
         the same node for a mesh loader (class name ends with "Loader") that
         has a `filename` Data — follow whichever sibling has a non-empty one.

    Returns the filename string, or None if neither pattern resolves.

    NOTE: SOFA's Python API does not expose `MeshTopology.src` via
    `findLink('src')` (the `src` parameter is consumed internally by SOFA's
    DataEngine machinery and is not surfaced as a queryable Link). Sibling
    scanning is the empirically-discovered alternative that handles the
    canonical same-node `MeshVTKLoader` + `MeshTopology(src='@loader')`
    pattern. Cross-node `src='@../parent/loader'` references are NOT
    resolved by this helper — flagged as a residual gap; the canonical
    SOFA usage is same-node and is what the user's failing scene used.
    """
    fname = _data_value(obj, "filename")
    if fname and isinstance(fname, str):
        return fname
    try:
        ctx = obj.getContext() if hasattr(obj, "getContext") else None
    except Exception:
        ctx = None
    if ctx is None:
        return None
    for sibling in getattr(ctx, "objects", []):
        if sibling is obj:
            continue
        sib_cls = _safe_class_name(sibling)
        if sib_cls.endswith("Loader"):
            loader_fname = _data_value(sibling, "filename")
            if loader_fname and isinstance(loader_fname, str):
                return loader_fname
    return None
```

- [ ] **Step 4: Update `_node_is_volumetric` to use the helper**

In `sofa_mcp/architect/_summary_runtime_template.py`, replace the `if cls == "MeshTopology":` block inside `_node_is_volumetric` (lines 417-420) with:

```python
        if cls == "MeshTopology":
            fname = _resolve_topology_filename(obj)
            if fname and fname.lower().endswith((".vtk", ".msh", ".vtu")):
                return True
```

The full updated function body for reference:

```python
def _node_is_volumetric(node):
    """Heuristic: does this node carry a topology container that supports tetra/hexa elements?"""
    for obj in getattr(node, "objects", []):
        cls = _safe_class_name(obj)
        if cls in _VOLUMETRIC_TOPO_CLASSES:
            return True
        if cls == "MeshTopology":
            fname = _resolve_topology_filename(obj)
            if fname and fname.lower().endswith((".vtk", ".msh", ".vtu")):
                return True
        if cls in {"RegularGridTopology", "SparseGridTopology"}:
            n_data = _data_value(obj, "n")
            try:
                if n_data is not None and len(n_data) >= 3 and all(int(x) > 1 for x in n_data[:3]):
                    return True
            except Exception:
                pass
    return False
```

- [ ] **Step 5: Run the first test to verify it passes**

Run: `~/venv/bin/python -m pytest test/test_architect/test_summarize_rules.py::test_rule_7_meshtopology_src_link_to_vtk_loader_is_volumetric -v`

Expected: PASS.

- [ ] **Step 6: Write the second failing test (Bug 5 — `BarycentricMapping` in subnode whose parent is loader-fed)**

Add this test directly after the previous one in `test_summarize_rules.py`:

```python
def test_rule_7_barycentric_in_subnode_whose_parent_uses_vtk_loader():
    """Regression: BarycentricMapping in a child of a node whose volumetric
    topology comes via MeshTopology(src='@loader') should NOT trigger
    rule 7B. The rule already walks up to the parent; the bug was that
    _node_is_volumetric returned False on the loader-fed parent (same
    root cause as test_rule_7_meshtopology_src_link_to_vtk_loader_is_volumetric).
    Verbatim from docs/feedback_2026-04-30 bug 5."""
    plugins = list(P_BASE) + [
        "Sofa.Component.IO.Mesh",
        "Sofa.Component.Topology.Container.Constant",
        "Sofa.Component.Mapping.Linear",   # BarycentricMapping
        "Sofa.GL.Component.Rendering3D",   # OglModel
    ]
    import os
    vtk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "meshes", "prostate.vtk"))
    assert os.path.exists(vtk_path), "test depends on meshes/prostate.vtk fixture"
    script = f'''
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    {_plugins_block(plugins)}
    rootNode.addObject("DefaultAnimationLoop")
    body = rootNode.addChild("body")
    body.addObject("EulerImplicitSolver")
    body.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    body.addObject("MeshVTKLoader", name="loader", filename={vtk_path!r})
    body.addObject("MeshTopology", src="@loader")
    body.addObject("MechanicalObject", template="Vec3d")
    body.addObject("UniformMass", totalMass=1.0)
    body.addObject("TetrahedronFEMForceField", youngModulus=1000, poissonRatio=0.3)
    cable = body.addChild("cable")
    cable.addObject("MechanicalObject", template="Vec3d", position=[[0,0,0]])
    cable.addObject("BarycentricMapping")
'''
    checks = _checks(_summarize(script))
    rule_7_errors = [c for c in checks if c["rule"] == "rule_7_topology" and c["severity"] == "error"]
    assert not rule_7_errors, (
        f"BarycentricMapping with loader-fed volumetric parent should not trigger rule 7; "
        f"got {rule_7_errors}"
    )
```

- [ ] **Step 7: Run the second test to verify it passes**

Run: `~/venv/bin/python -m pytest test/test_architect/test_summarize_rules.py::test_rule_7_barycentric_in_subnode_whose_parent_uses_vtk_loader -v`

Expected: PASS (no separate fix needed — the helper from Step 3 resolves both bugs).

- [ ] **Step 8: Run the full rule-7 + summarize suite to confirm no regression**

Run: `~/venv/bin/python -m pytest test/test_architect/test_summarize_rules.py -v -k "rule_7 or rule_8"`

Expected: every existing rule-7 test still passes (happy tetra topo, surface-topo trigger, shell-FEM exemption) plus both new tests pass.

- [ ] **Step 9: Commit**

```bash
git add sofa_mcp/architect/_summary_runtime_template.py test/test_architect/test_summarize_rules.py
git commit -m "$(cat <<'EOF'
rule 7: follow MeshTopology.src link to resolve loader-fed volumetric topology

Phase 6.3 #1. Two false positives from the MOR-trunk dogfood session
shared one root cause: _node_is_volumetric only checked
MeshTopology.filename, missing the canonical SOFA pattern of
MeshVTKLoader -> MeshTopology(src='@loader'). With this fix:

  - Bug 4: TetrahedronFEMForceField under a node with MeshTopology(src=
    '@loader') from a .vtk file no longer triggers rule 7A.
  - Bug 5: BarycentricMapping in a subnode whose parent is loader-fed
    no longer triggers rule 7B (the rule already walked up; the bug
    was that the parent reported as non-volumetric).

New helper _resolve_topology_filename scans sibling objects in the
same node for a mesh loader (class name ending in 'Loader') and reads
its filename. The SOFA Python API does not expose the src link via
findLink, so the sibling-scan approach is used instead. Two new tests
cover both bug shapes verbatim from the user's session, using
meshes/prostate.vtk as a real .vtk fixture.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Bookkeeping — mark items shipped in docs

**Files:**
- Modify: `docs/feedback_2026-04-30_mor_trunk_session.md`
- Modify: `docs/plan.md`
- Modify: `docs/progress.md`

- [ ] **Step 1: Mark items resolved in feedback file**

In `docs/feedback_2026-04-30_mor_trunk_session.md`:

1. Change `### 4. \`MeshTopology\` from \`.vtk\` flagged as non-volumetric` → `### 4. \`MeshTopology\` from \`.vtk\` flagged as non-volumetric ✅ (resolved 2026-04-30)`
2. Change `### 5. \`BarycentricMapping\` flagged as non-volumetric parent on cable subnodes` → `### 5. \`BarycentricMapping\` flagged as non-volumetric parent on cable subnodes ✅ (resolved 2026-04-30)`
3. Change `### 3. \`write_scene\` ASCII-encodes content` → `### 3. \`write_scene\` ASCII-encodes content ✅ (resolved 2026-04-30)`

In the "Suggested follow-up improvements" priority list at the bottom, mark items 1 and 2 with `✅ shipped 2026-04-30`.

- [ ] **Step 2: Update plan.md status row + Phase 6.3 table**

In `docs/plan.md`, update the status snapshot row:

```markdown
| 6.3 — Field-feedback punch list | 🚧 partial | items #1, #2, #4, #5 shipped 2026-04-30; 4 of 8 still pending |
```

In the Phase 6.3 table, mark items #1 and #2 with the same checkmark/date pattern used for #4 and #5 in the previous commit.

- [ ] **Step 3: Add a progress.md entry**

Append a new entry to `docs/progress.md` after the Phase 6.3 #4 + #5 entry:

```markdown
## Phase 6.3 #1 + #2 — Rule 7 false positives + write_scene UTF-8 ✅ (2026-04-30)

Two field-feedback bugs from the MOR-trunk dogfood session, fixed
together in two commits (one per bug class).

- `write_scene` now opens its output file with `encoding="utf-8"`. Same
  pattern that already landed at `scene_writer.py:149,203` for the
  validate/summarize tempfiles. Test forces `LC_ALL=C` to reproduce
  the locale-ASCII fallback the FastMCP server hits in production.
- `_summary_runtime_template.py` adds `_resolve_topology_filename`,
  which follows `MeshTopology.src` to its loader (e.g.
  `MeshVTKLoader`) and reads the loader's `filename`. Resolves both
  rule-7 false positives reported by the user (4: TetrahedronFEM with
  loader-fed `MeshTopology`; 5: `BarycentricMapping` whose parent
  uses the same pattern). Test fixtures use `meshes/prostate.vtk`.
```

- [ ] **Step 4: Commit the docs**

```bash
git add docs/feedback_2026-04-30_mor_trunk_session.md docs/plan.md docs/progress.md
git commit -m "$(cat <<'EOF'
docs: mark Phase 6.3 #1 + #2 shipped

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Verification (end-to-end)

After all three tasks complete:

1. **Targeted regression run:**
   ```bash
   ~/venv/bin/python -m pytest test/test_log_compact.py test/test_observer/test_diagnostics.py test/test_architect/test_summarize_rules.py test/test_architect/test_mcp_transport.py test/test_architect/test_scene_writer.py -v
   ```
   Expected: every previously-green test still passes, plus the 3 new tests added here.

2. **Manual smoke against the MOR-trunk scene** (the source of the bug reports):
   ```bash
   ~/venv/bin/python sofa_mcp/server.py &  # start MCP server
   # then via MCP transport, call summarize_scene on
   # ~/workspace/MOR/scene/trunk/trunk.py
   ```
   Expected: `rule_7_topology` no longer fires `error` on either the trunk
   `TetrahedronFEMForceField` or the cable subnodes' `BarycentricMapping`.

3. **`write_scene` round-trip with em-dashes via MCP:**
   Call `write_scene` over MCP transport with a script containing an em-dash docstring. Expected: file written, contents include the em-dash byte-for-byte (verify via `python -c "open(path,'rb').read()" | grep $'\xe2\x80\x94'`).

## Out of scope (deferred, for clarity)

- **Phase 6.3 #3 (`find_indices_by_region` VTK support):** separate work — touches `mesh_inspector.py`, not these files. Defer to its own plan.
- **Phase 6.3 #6 (`get_plugins_for_components` deprecated/meta handling):** low severity, defer.
- **Phase 6.3 #7 (SKILL.md `claude mcp add` registration):** docs work, defer.
- **Phase 6.3 #8 (`render_scene_snapshot` mesh geometry):** medium-high but multi-day — separate plan.
- A full audit of every place `_node_is_volumetric` returns False to look for analogous src-link bugs in other rules. Rule 7 is the only consumer; YAGNI.

## Self-Review

**Spec coverage:** Plan covers items #1, #2, and (transitively via the same root cause) #5 from the punch list. Item #1's two sub-bugs (4 + 5 in the bug numbering) both resolved by Task 2. ✓

**Placeholder scan:** No TBDs, no "appropriate error handling," no "similar to Task N." All code blocks are concrete. ✓

**Type consistency:** `_resolve_topology_filename` is referenced in Task 2 Step 3 (defined) and Task 2 Step 4 (called). Names match. ✓

**Test fixture availability:** `meshes/prostate.vtk` confirmed to exist (verified before plan write).

---
