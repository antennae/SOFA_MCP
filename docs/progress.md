# SOFA_MCP — Completed Work Log

*Last updated 2026-04-29 (Step 2 shipped)*

This file is the historical record of work that has shipped. The forward-looking roadmap lives in `docs/plan.md`; the technical specification for the `diagnose_scene` toolkit lives in `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md`.

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

---

## Files created during completed work

- `sofa_mcp/architect/_summary_runtime_template.py` (Step 1.5 runtime, ~690 LOC)
- `sofa_mcp/observer/_diagnose_runner.py` (Step 2 subprocess runner, ~280 LOC)
- `sofa_mcp/observer/diagnostics.py` (Step 2 parent orchestrator, ~180 LOC)
- `test/test_architect/test_summarize_rules.py` (24 tests)
- `test/test_architect/test_mcp_transport.py` (transport regression — summarize + diagnose)
- `test/test_observer/test_diagnostics.py` (4 tests, Step 2)
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

---

## Milestones passed

- **M1 — Headline workflow renders correctly** ✅ (after Phase 1)
- **M2 — Deletion approval** ✅ (before Phase 2)
