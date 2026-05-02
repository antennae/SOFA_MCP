# SOFA_MCP — Completed Work Log

*Last updated 2026-04-30 (Step 3 shipped + MOR-trunk dogfooding feedback)*

This file is the historical record of work that has shipped. The forward-looking roadmap lives in `docs/plan.md`; the technical specification for the `diagnose_scene` toolkit lives in `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md`. Real-world dogfooding feedback lives in `docs/feedback_*.md` files.

---

## Phase 1 — Headline workflow runs end-to-end ✅ (M1 passed)

`tri_leg_cables.py` validates, runs, and renders correctly. The headline demo is reproducible.

- gmsh dependency fix landed in `sofa_mcp/architect/mesh_generator.py`.
- `render_scene_snapshot` MCP tool shipped (`sofa_mcp/observer/renderer.py`) — auto-discovers `MechanicalObject`s, picks up sibling `OglModel` colors, runs offscreen via PyVista.
- `tri_leg_cables` PNG renders the three-legged structure deforming under cable actuation.

**M1 gate:** passed — non-SOFA reviewer can see the structure deform.

---

## Phase 2 — Cut dead surface ✅ (M2 passed)

Tool count reduced from 19 to 15 by removing dead/duplicate tools per per-item user approval.

- Removed: `math_sandbox.py`, `calibrator/`, `get_mesh_bounding_box`, `inspect_mesh_topology`.
- Each removal got explicit user approval before delete.

**M2 gate:** passed — every removal explicitly approved.

---

## Phase 6.1 — Investigative debugging toolkit (in progress)

**Framing:** the LLM agent debugs *behavioral* bugs in scenes that already run (robot doesn't move, deformation too small, position diverges). The MCP doesn't return "the bug is X." The MCP provides good probes; the agent does the reasoning. Existing tools (`run_and_extract`, `render_scene_snapshot`, `process_simulation_data`, `summarize_scene`) are partial probes; the new pieces are a sanity-report tool and a small set of targeted probes.

### Step 1 — Health Rules docs ✅ (2026-04-21)

9 Health Rules in `skills/sofa-mcp/sofa-mcp/SKILL.md`, with `references/component-alternatives.md` for fetch-on-demand alternatives. Numbering matches the SKILL.md user-facing order (1-9), which differs from the v2.1 spec's 1-12 internal traceability numbering (documented in v2.1 §1.1 changelog).

### Step 1.5 — `summarize_scene` rule enforcement ✅ (2026-04-26)

Made the 9 SKILL.md rules machine-readable: each `summarize_scene` call returns a `checks` list of `{rule, severity, subject, message}` entries.

- `sofa_mcp/architect/_summary_runtime_template.py` — runtime template with 9 per-rule check functions, two sentinel tokens for plugin map + user createScene substitution. ~690 LOC.
- `sofa_mcp/architect/scene_writer.py` — `_build_summary_wrapper` reads template, substitutes sentinels, runs in subprocess.
- `test/test_architect/test_summarize_rules.py` — 24 pytest tests (9 happy + 9 trigger + 3 edges + pair-interaction exemption + legacy booleans + 2 upstream smokes). All passing.

**Notable findings during implementation:**
- Rule 1 trigger isn't naturally falsifiable — SOFA's factory crashes during `createScene` if a class's plugin isn't loaded. Test bypasses via `SofaRuntime.importPlugin`.
- Rule 6 "FF without MO in ancestor chain" is preempted by SOFA's factory (mstate-not-found). The rule's testable value is the pair-interaction exemption (`object1`/`object2`).
- `object1`/`object2` are `Sofa.Core.Link`, NOT Data fields — must use `findLink(name).getValueString()`, not `findData(name).value`.
- Wrapper uses unique sentinel tokens (`__SOFA_MCP_PLUGIN_MAP_SENTINEL__`, `__SOFA_MCP_USER_CREATE_SCENE_SENTINEL__`) because earlier markers collided with the file's own docstring.

### Step 1.5+ — Manual LLM smoke + transport hardening ✅ (2026-04-28)

Manual smoke against 4 real third-party scenes + 6 synthesized fixtures, **first via direct function call, then via the actual MCP transport.** The transport pass surfaced a real shipping-blocker bug the function-direct path missed.

**Encoding bug found and fixed:** `tempfile.NamedTemporaryFile(mode="w")` used the locale default. The FastMCP server process resolved that to ASCII; the wrapper file contains em-dashes (U+2014) in rule messages. Every `summarize_scene` and `validate_scene` call returned an error string. Fix: `encoding="utf-8"` at `scene_writer.py:149,203`.

**numpy youngModulus hardening:** SOFA returns `youngModulus` as a length-1 ndarray, not a scalar. `float(ym)` works today but raises `DeprecationWarning` in numpy 1.25 and will be a hard error. Fixed at `_summary_runtime_template.py:575`.

**Debugging playbook for the agent:** `skills/sofa-mcp/sofa-mcp/references/debugging-playbook.md` documents the investigative loop using only tools that exist today. SKILL.md gets a 5-line pointer (matches user's "tight, not bulky" feedback). When `diagnose_scene` ships, its sanity report folds into Step 2 of the playbook.

**MCP transport regression test:** `test/test_architect/test_mcp_transport.py` spawns a real server on a free port, calls `summarize_scene` via the official MCP client SDK, and asserts envelope + checks shape + Rule 4 trigger fires. ~6s end-to-end. Catches encoding regressions, JSON-shape changes, legacy-boolean drift. Verified: temporarily setting `encoding="ascii"` makes the test fail with the exact `—`-not-encodable error.

**`SOFA_MCP_PORT` env var added** (`server.py:174`) so the test picks a free port and never collides with a dev's running server.

### Step 2 — Subprocess foundation + sanity report skeleton ✅ (2026-04-29)

`diagnose_scene` MCP tool ships end-to-end. Two-subprocess architecture: `summarize_scene` (30s budget) supplies the `anomalies` field, runner (90s budget) supplies per-step metrics on every unmapped MechanicalObject. Tempfile-based payload exchange — runner writes JSON to a path passed on argv, parent reads after subprocess exits. Both subprocess invocations decode with `encoding="utf-8", errors="replace"` to dodge the locale-default-ASCII trap that Step 1.5+ already hit.

- `sofa_mcp/observer/_diagnose_runner.py` (~280 LOC) — fixed shipped runner, debuggable from the shell (`~/venv/bin/python sofa_mcp/observer/_diagnose_runner.py archiv/cantilever_beam.py 5 0.01 /tmp/out.json`). Loads scene via `importlib.util.spec_from_file_location`. Mapped-MO predicate uses the plugin cache (mirrors `check_rule_3_time_integration`).
- `sofa_mcp/observer/diagnostics.py` (~180 LOC) — parent orchestrator. Tempfile lifecycle wrapped in `try`/`finally` with `os.remove`. JSONDecodeError + missing-file + empty-file collapse to one failure shape.
- `sofa_mcp/server.py` — `diagnose_scene` MCP tool registered (signature: `scene_path, complaint=None, steps=50, dt=0.01`). `complaint` accepted but unused in Step 2 (Step 5 playbook will wire it).
- `test/test_observer/test_diagnostics.py` — 4 cases passing in ~36s: happy path on cantilever_beam, Rule 4 anomaly lift, runner-timeout (`time.sleep(200)` fixture, monkeypatched 5s budget), `createScene`-raises (explicit `RuntimeError("intentionally broken for test")`).
- `test/test_architect/test_mcp_transport.py` — extended with a `diagnose_scene` round-trip over real MCP transport.

**Smoke verification on cantilever_beam.py:** `success: true`, `nan_first_step: null`, `max_displacement_per_mo = {"/root/beam": 12.85}`, `max_force_per_mo = {"/root/beam": 54388.5}`, 9 anomalies (all `ok` severity), `scene_summary.actuators_only: false`. End-to-end including warm SOFA cold-start ≈4-6s.

**Out of Step 2 scope, deferred to Step 3:** `printLog` toggling on solver classes, §6.A runtime smell tests, §6.B stdout regex, §6.C structural checks, log truncation. `init_stdout_findings` returned as `[]` placeholder.

### Step 3 — Smell test catalog ✅ (2026-04-30)

Six rules ship + printLog activation + log truncation, per the plan-mode design at `~/.claude/plans/cosmic-bubbling-salamander.md` (review trimmed 22 spec rules to 6). Two commits, each independently green:

**Commit 1 — runner extensions** (`d313d32`):
- `_diagnose_runner.py` ~+170 LOC. Pre-init walk runs §6.C `multimapping_node_has_solver` (plugin attribution + `endswith("MultiMapping")` filter, strictly node-local; verified against `MechanicalIntegrationVisitor.cpp:71`) and toggles `printLog=True` on constraint solvers, ODE solvers, animation loops, and constraint corrections. Predicate is two-tier: plugin attribution (primary) with class-name suffix fallback for core-builtin classes not in the plugin cache (e.g., `DefaultAnimationLoop`). The fallback only fires when the class is absent from `_PLUGIN_FOR_CLASS`, so `SparseLDLSolver` (linear, in-cache) is correctly excluded.
- Post-init capture: per-MO initial bbox extent (`extents_per_mo`), constraint-solver `maxIterations` (`solver_max_iterations`); per-step capture of `currentIterations` (`solver_iterations`) and QP `objective` (`objective_series`).
- Failure-path preservation: `_empty_payload()` skeleton populated in-place; `main`'s except writes whatever was filled, so structural anomalies and printLog state survive an init or animate Python exception.
- Test fixtures land alongside: `multimapping_with_solver.py`, `qp_infeasible.py`. 4 new tests (call runner subprocess directly).

**Commit 2 — parent smell tests + truncation** (`8c83055`):
- `diagnostics.py` ~+170 LOC. Five pure functions: `_check_excessive_displacement` (10× warn / 100× err two-tier), `_check_solver_iter_cap_hit` (NNCG/BGS path; CG/LCP regex deferred), `_check_inverse_objective_not_decreasing` (window=5; relative+absolute tolerance with at-optimum guard `obj[-1] > 1e-6`), `_check_qp_infeasible_in_log` (regex with `match_count`), `_truncate_log` (5KB head + 25KB tail). Orchestrator runs smell tests on full pre-truncation log, lifts §6.C anomalies on both success and failure paths, then truncates.
- `excessive_displacement.py` and `iter_cap_hit.py` fixtures land alongside.
- 13 pure-fn unit tests + 4 integration tests + 2 MCP transport extensions (clean-scene no-false-positives + multimapping slug surfaces over JSON-RPC).

**Prerequisite (verified before commit 1):** built `qp_infeasible.py` (CableActuator with inverted force bounds: minForce=100, maxForce=-100). Empirically confirmed `QP infeasible` appears 10× in `solver_logs` for 5 steps **without** printLog activation — SOFA emits it via `msg_warning`/`msg_error` from `QPInverseProblemImpl` (qpOASES rejection paths), bypassing the printLog gate. §6.B.2 has signal independent of printLog activation.

**Empirical fixture calibration:**
- `excessive_displacement.py`: 50mm beam free-falling under gravity, dt=0.1, 5 steps. Lands at 1472mm displacement / 50mm extent = 29.4× — squarely in the warning band, no NaN. No threshold tuning required.
- `iter_cap_hit.py`: NNCG with `maxIterations=2, tolerance=1e-12` plus a `CableConstraint` that creates Lagrangian constraints. Every step hits the cap (5/5).

**Smoke verification on archiv/:** cantilever_beam.py, tri_leg_cables.py, prostate.py, prostate_chamber.py — zero smell-test fires across all four (no false positives).

**Test counts:** `test_diagnostics.py` grew from 4 → 25 tests; `test_mcp_transport.py` from 2 → 3. Full repo `pytest test/`: 72 passing, 8 pre-existing Phase-5 failures (test_scene_writer.py + test_stepping.py contract drift, unrelated to Step 3).

---

## Phase 6.3 #4 + #5 — `verbose` flag for log compaction ✅ (2026-04-30)

Lifted ahead of Phase 6.1 Step 4 because every long debug session was paying ~30-50K tokens of `solver_logs` noise per `diagnose_scene` call (worst per-call token cost in the kit; ~30-40% of the dogfood session's MCP tokens). Plan at `~/.claude/plans/cosmic-bubbling-salamander.md`.

- `sofa_mcp/_log_compact.py` (new, ~95 LOC): `compact_log(text, *, tail_lines=20) -> (text, dropped)`. Hybrid allowlist + tail-anchor filter, multi-line traceback state machine. Allowlist: `[ERROR]/[WARNING]/[FATAL]/[DEPRECATED]/[SUGGESTION]`, plugin loads, convergence/iterations/residual lines, `QP infeasible`, traceback markers, runtime-template sentinels.
- `validate_scene` and `summarize_scene` accept `verbose: bool = False`. Validate's `SUCCESS:` sentinel now extracted+stripped (mirrors summarize's `SCENE_SUMMARY_JSON:` pattern) — removes a noise line from every successful response.
- `diagnose_scene` accepts `verbose: bool = False`. Smell tests scan the full pre-compaction log; compaction runs after, then head/tail char truncation. Response carries `log_lines_dropped: int` when filtering happened.
- `server.py` MCP wrappers pass `verbose` through; SKILL.md documents the flag.
- 14 pure-function unit tests in `test/test_log_compact.py`; 1 integration test in `test_diagnostics.py` (verbose vs. compact comparison on cantilever_beam); 1 transport test in `test_mcp_transport.py`. Full affected suite: 45 tests passing.

**Empirical ratio on cantilever_beam (steps=20, dt=0.01):** verbose=True 30748 chars / 59 visible lines, verbose=False 7070 chars / 35 lines, dropped=459. **4.35× cut on a non-stiff scene** that doesn't exercise EulerImplicitSolver f-vector dumps; cut expected closer to the user's reported ~10× on stiff scenes (e.g., the MOR-trunk dogfood scene).

---

## Phase 6.3 #1 + #2 — Rule 7 false positives + write_scene UTF-8 ✅ (2026-05-02)

Two field-feedback bugs from the MOR-trunk dogfood session, fixed in
two commits.

- **`write_scene` UTF-8** (`6bbe028`): now opens its output file with
  `encoding="utf-8"`. Same pattern that already landed at
  `scene_writer.py:149,203` for the validate/summarize tempfiles.
  Test forces `LC_ALL=C` to reproduce the locale-ASCII fallback the
  FastMCP server hits in production.
- **Rule 7 false positives** (`14b9f8b` + `103895f` follow-up):
  `_summary_runtime_template.py` adds `_resolve_topology_filename`,
  which detects `MeshTopology(src='@loader')` paired with a sibling
  mesh loader (class name ends with `Loader`) and reads the loader's
  `filename`. SOFA's Python API does not expose the `src` link via
  `findLink`, so sibling-scanning is used instead — the canonical
  `MeshVTKLoader` + `MeshTopology` pattern is fully covered. Resolves
  both rule-7 false positives reported by the user (4: `TetrahedronFEM`
  with loader-fed `MeshTopology`; 5: `BarycentricMapping` whose parent
  uses the same pattern). Test fixtures use `meshes/prostate.vtk`. The
  follow-up commit narrows a too-broad `try/except` per code review.

Residual gap: `src="@../path/to/loader"` cross-node references are
not resolved (sibling-scan is same-node only). The canonical SOFA
pattern uses same-node loaders, so this is acceptable; flagged for
future work if a real scene hits it.

---

## Files created during completed work

- `sofa_mcp/architect/_summary_runtime_template.py` (Step 1.5 runtime, ~690 LOC)
- `sofa_mcp/observer/_diagnose_runner.py` (Step 2 subprocess runner, extended in Step 3, ~450 LOC)
- `sofa_mcp/observer/diagnostics.py` (Step 2 parent orchestrator, extended in Step 3, ~360 LOC)
- `test/test_architect/test_summarize_rules.py` (24 tests)
- `test/test_architect/test_mcp_transport.py` (transport regression — summarize + diagnose, 3 tests)
- `test/test_observer/test_diagnostics.py` (25 tests after Step 3)
- `test/test_observer/fixtures/{qp_infeasible,multimapping_with_solver,iter_cap_hit,excessive_displacement}.py` (Step 3 trigger fixtures)
- `skills/sofa-mcp/sofa-mcp/references/debugging-playbook.md` (agent-facing investigative guide)
- `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md` + `docs/specs/diagnose-scene-research/*` (12 rule-review files)
- `sofa_mcp/observer/renderer.py` (Phase 1)

## Files modified during completed work

- `sofa_mcp/architect/scene_writer.py` — sentinel substitution wiring + `encoding="utf-8"` on tempfiles
- `sofa_mcp/server.py` — `SOFA_MCP_PORT` env var; `diagnose_scene` tool added (Step 2); tool registrations trimmed during Phase 2
- `skills/sofa-mcp/sofa-mcp/SKILL.md` — debug-workflow pointer; Health Rules numbered 1-9
- `sofa_mcp/architect/mesh_generator.py` — gmsh fix (Phase 1)

---

## Effort actuals (retrospective)

- Phase 1: ~half a day
- Phase 2: ~1 hour
- Phase 6.1 Step 1: docs only, ~half day
- Phase 6.1 Step 1.5: **~1 day** (vs estimated half day; ~690+600 LOC vs estimated 170+250 — over-estimate explained by per-rule helpers, link-vs-data field handling, and full-scene fixtures)
- Phase 6.1 Step 1.5+: encoding fix + playbook + transport test, ~half day
- Phase 6.1 Step 2: ~half a day (matched estimate; ~460 LOC impl + ~120 LOC tests, slightly under the ~440+~100 plan budget)
- Phase 6.1 Step 3: ~half a day (under estimate; ~340 LOC impl + ~280 LOC tests = ~620 vs plan budget ~430. Test fixtures + uniform-shape failure paths cost more than the plan accounted for; smell-test logic itself was lighter than expected)

---

## Milestones passed

- **M1 — Headline workflow renders correctly** ✅ (after Phase 1)
- **M2 — Deletion approval** ✅ (before Phase 2)

---

## Real-world dogfooding events

- **2026-04-30 — MOR-trunk authoring session.** Used the MCP from a separate Claude Code session in `~/workspace/sofa` to author a 4-cable soft-trunk scene for kPCA Model Order Reduction work (final output `~/workspace/MOR/scene/trunk/trunk.py`, 100 steps, 113mm tip displacement, no NaN). Net assessment: **net positive** — `validate_scene` and `diagnose_scene` together caught a `GenericConstraintSolver` v25.12 deprecation + verified physics in two calls, work the user estimated at ~5 manual cycles otherwise. Surfaced 7 concrete bugs / friction points (3 real bugs, 2 false-positive Rule 7 paths, 3 ergonomic gaps) — full report at `docs/feedback_2026-04-30_mor_trunk_session.md`, prioritized punch list folded into `docs/plan.md` Phase 6.3.

---

## Phase 6.1 Step 4 — Probe library (high-leverage pair) ✅ (2026-05-02)

Two new MCP probes that close the "instrument or modify" rows of the
debugging playbook:

- **`enable_logs_and_run`** (`10bda27` + `5d67ab9`) — toggle
  `printLog=True` on objects matching user-supplied `log_targets`
  (class names or node-path fragments), animate for N steps, return
  captured stdout filtered through `compact_log`. The agent uses this
  to see what a specific solver, mapping, or constraint says at
  runtime after `diagnose_scene` flags an anomaly.
- **`perturb_and_run`** (`098c96a` + `09a8b00`) — apply Data-field
  overrides specified as `{"/path": {"field": value}}` before init,
  animate for N steps, return per-MO metrics in the same shape as
  `diagnose_scene`. Foundational to "modify minimally, re-measure,
  falsify" hypothesis testing. Path can be an object path (single
  object) or a node path (fans out across the node).

Both probes share a runner (`sofa_mcp/observer/_probe_runner.py`) that
dispatches by `--mode` argv. Parent orchestrator at
`sofa_mcp/observer/probes.py` mirrors `diagnostics.py` (tempfile
lifecycle, JSON-based subprocess invocation, `compact_log` integration).

**Plan-code bugs caught during implementation:**
- `_resolve_node_at_path` needed longest-prefix match (first-match
  produced wrong residuals).
- SOFA scalar Data fields are 1-element numpy arrays, not Python
  scalars; assigning a bare `100.0` raises TypeError. Wrap in
  `[value]` on TypeError.
- `numpy_array or []` raises ambiguous truth-value; use explicit
  `if raw is not None` checks.
- `_capture_metrics` takes `root` directly rather than reaching
  through `mos[0][1].getContext()`.

**Scope cut from spec v2.1 (user-confirmed 2026-05-02):**
`compare_scenes` (~200 LOC) and `scan_init_stdout` (~50 LOC) are
deferred. The four M5 fixtures don't strictly need them; if Step 5
surfaces a case where they're required, they get their own plan.

**Tests:** 5 integration tests in `test/test_observer/test_probes.py`
covering class-name targets, unmatched targets, default log
compaction, youngModulus perturbation effect on
`archiv/cantilever_beam.py`'s `HexahedronFEMForceField` (path
`/root/beam/FEM`), and unmatched-path reporting.

---

## Phase 6.1 Step 5 — E2E fixtures + M5 gate (automated half) ✅ (2026-05-02)

Four deliberately-broken fixtures in `test/test_observer/fixtures/`,
plus an automated regression net in `test/test_observer/test_diagnose_e2e.py`:

- **`m5_cables_unactuated.py`** — `tri_leg_cables` variant with
  `CableConstraint(value=0)`. NO anomaly fires. Test asserts low
  `max_displacement_per_mo` and that `perturb_and_run` with restored
  value produces ≥3× larger displacement on the perturbed leg. Tests
  the data-driven hypothesis path (the agent-reasoning part is
  manual).
- **`m5_units_mismatch.py`** — `gravity=[0,-9810,0]` (mm/g/s) with
  `youngModulus=5e9` (SI-Pa scale). Rule 9 fires at warning.
- **`m5_missing_collision.py`** — `TriangleCollisionModel` on a body
  without the 5-cluster pipeline at root. Rule 8 fires at error.
- **`m5_broken_mapping.py`** — `BarycentricMapping` in a child whose
  parent has only a bare `MeshTopology` (no filename, no loader, no
  shell FEM). Rule 7B fires at error.

**Tests:** 4 new E2E cases in `test_diagnose_e2e.py`; 80 total green
across `test_log_compact + test_diagnostics + test_summarize_rules +
test_mcp_transport + test_probes + test_diagnose_e2e`.

**M5 manual gate** at `docs/specs/2026-05-02-m5-gate.md` — strict
grading: every fixture must clear three binary criteria (right
anomaly read, plausible hypothesis, right probe call). Awaits user
verification; once passed, M5 closes Phase 6.1.

**Spec deviation:** v2.1 §Step 5's playbook table referenced smell
tests we never shipped (`actuator_lambda_zero`, `child_only_motion`,
etc.) and probes we deferred (`compare_scenes`). The fixtures here
are derived from the actual diagnostic surface; the M5 doc explicitly
supersedes the v2.1 fixture table.

## Phase 6.3 #8 — `render_scene_snapshot` mesh geometry ✅ (2026-05-02)

Replaced the "MO points → Delaunay-3D → convex hull on failure" pipeline with explicit-triangle rendering. The renderer now does two-pass discovery:

1. **Visual models** — every `OglModel` / `VisualModelImpl` is rendered using its own `position` + `triangles` Data fields (or `quads` decomposed into triangles, when `triangles` is empty). Color comes from the visual model's own `color` Data when set.
2. **Topology fallback** — for nodes not covered by pass 1, a sibling topology container's triangles/quads are used with the MO's position. Lets simple scenes without an OglModel still render properly.
3. **Point-cloud final fallback** — only if neither pass produced any geometry, every unmapped MO is drawn as a point glyph cloud. The renderer never builds a convex hull.

Cable subnodes (sparse MOs with no surface) are filtered naturally: they're not visual models and they have no triangle topology, so they only show up if nothing else rendered — which doesn't happen for any real scene.

**Empirical confirmation:** `archiv/tri_leg_cables.py` exposed `position=44 triangles=102 quads=51` per OglModel after init+animate, matching the expected leg surface. Render of the same scene now shows three distinct deformed legs with visible surface mesh (vs. three convex-hull blobs before); the actuated leg is clearly bent toward the common pull point.

**Tests:** `test/test_observer/test_renderer.py` — asserts `tri_leg_cables` renders exactly 3 visual models (one per leg, cables excluded), and a topology-only fixture (`render_no_visual_fallback.py`) renders without hull or crash. Total adjacent-suite count: 82 passed.

**SKILL.md:** added a one-liner pointing agents at OglModel as the renderer's primary input.
