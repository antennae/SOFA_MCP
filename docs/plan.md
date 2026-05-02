# SOFA_MCP — Portfolio Polish, Community-Ready Posture

*Last updated 2026-05-02 (Step 4 shipped + Phase 6.3 items #1, #2, #4, #5)* — forward-looking only. For completed work, see `docs/progress.md`. Technical reference for the diagnose toolkit lives in `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md`.

## Context

The user has clarified the project's purpose: **portfolio piece first, beginner-tool second**. They prefer reading SOFA source directly to using LLM-mediated tooling for their own work, so personal productivity is not a goal. The project should:

1. **Look polished as a portfolio piece** — a non-SOFA reviewer can understand the value in 5 minutes via a video and a clean README.
2. **Leave the door open for the beginner-tool path** — if any SOFA newcomer finds it, they can install and run it without external help. No commitment to ongoing maintenance.

## Goals (priority order)

1. The headline workflow runs reliably end-to-end and is showcased in the README.
2. A fresh machine can install and run the headline workflow in 10 minutes.
3. Project surface (tools, code, docs) reflects the headline — no dead code, no broken tools, no misleading claims.
4. Community-ready posture (LICENSE, CONTRIBUTING note, version pin) without maintenance commitment.

## Non-goals (explicit, so future sessions don't drift)

- Parameter sweeps, calibrator/serial bridge, scene templates.
- Mass refactor to fix every code-review item — only fix items that surface in the headline path or affect the security narrative.
- Improving personal productivity workflows.

(Originally also "inverse problem solver" and "debug ability" were non-goals. User pushed back — both are kept and folded in as Phase 6 because they are the features that make this project deeper than a wrapper.)

## Status snapshot (remaining)

| Phase | Status | Notes |
|---|---|---|
| 6.1 — Investigative debugging toolkit | ✅ done | Steps 1, 1.5, 2, 3, 4 done; Step 5 automated half done 2026-05-02; M5 passed 2026-05-02 by user dogfooding the toolkit in real authoring sessions |
| 6.3 — Field-feedback punch list | 🚧 partial | items #1, #2, #4, #5, #8 shipped (2026-04-30 / 2026-05-02); 3 of 8 still pending (low-severity #3, #6, #7) |
| 4 — Tell the story (README + SKILL) | 🚧 partial | SKILL.md tightened; README rewrite pending |
| 3 — Wrap the install (Dockerfile) | ⏳ deferred | M3 gate; deprioritized 2026-05-02 — beginner-install ergonomics, not portfolio-critical |
| 6.2 — Inverse-problem authoring (no new tool) | ✅ done | code+docs shipped 2026-05-02 (tri_leg_inverse.py + SKILL section + references); M6 passed 2026-05-02 — user confirmed render shows three legs reaching three goals |
| 5 — Open the door (LICENSE, CI, etc.) | 🚧 partial | test hygiene shipped 2026-05-02 — `pytest test/` now 113/113 green (was 7 pre-existing failures). LICENSE / CONTRIBUTING / issue template / pyproject polish still pending. CI deferred (would need SOFA-built runner). |

---

## Phase 6.1 — Investigative debugging toolkit (current focus)

**Framing:** the LLM agent debugs *behavioral* bugs in scenes that already run. The MCP doesn't return "the bug is X." The MCP provides good probes; the agent does the reasoning. Existing tools are partial probes; the new pieces are a sanity-report tool and a small set of targeted probes.

### Step 2 — Subprocess foundation + sanity report skeleton ✅ (2026-04-29)

Shipped — see `docs/progress.md` Step 2 entry. `diagnose_scene` MCP tool exists end-to-end; sanity-report shape (`success`, `metrics`, `anomalies`, `init_stdout_findings`, `solver_logs`, `scene_summary`) is the contract Step 3 fills out. Out-of-scope in Step 2 and explicitly stubbed for Step 3: `printLog` toggling, runtime/regex/structural smell tests, log truncation.

### Step 3 — Smell test catalog ✅ (2026-04-30)

Shipped — see `docs/progress.md` Step 3 entry. 6 rules + printLog activation + log truncation, all green in `pytest test/test_observer/test_diagnostics.py` (25 tests) and `test/test_architect/test_mcp_transport.py` (3 tests). Zero false positives on the four `archiv/` scenes. CG/LCP regex arm of `solver_iter_cap_hit` and per-step bucketing for `qp_infeasible_in_log` deferred to a future iteration when known-cap-hit fixtures and step-boundary-stable log formats are available.

### Step 4 — Probe library ✅ partial (2026-05-02)

High-leverage pair shipped: `enable_logs_and_run` + `perturb_and_run` (see progress.md). The two deferred probes — `compare_scenes` (~200 LOC, two-scene runtime diff) and `scan_init_stdout` (~50 LOC, init-only precheck) — are out of scope for now and get their own follow-up plan if M5 surfaces a need.

### Step 5 — E2E fixtures + M5 gate ✅ partial (2026-05-02)

Automated regression net shipped: four deliberately-broken fixtures
in `test/test_observer/fixtures/m5_*.py` exercising Rule 7, Rule 8,
Rule 9, and the no-anomaly data-driven path. Four E2E pytest cases
in `test_diagnose_e2e.py` assert the right slug/severity/metric.

**M5 milestone gate** ✅ passed 2026-05-02. User passed the gate by
dogfooding the toolkit in real authoring sessions (not via the formal
4-fixture rubric at `docs/specs/2026-05-02-m5-gate.md`) — the toolkit
held up in actual use, which is the bar that matters. Phase 6.1
officially closes.

---

## Other phases (waiting on 6.1 completion)

### Phase 3 — Dockerfile (M3 gate)

Derive from `~/workspace/prostate-biobot/dockerfile`. Strip ROS2, torch, PyGeM. Keep SOFA v24.12 source build + SoftRobots + SoftRobots.Inverse. Adapt for SOFA_MCP's Python deps. Expose 8000. **Do this after 6.1 closes** so the Dockerfile is sized to the final dependency set.

### Phase 6.2 — `run_inverse_problem` tool (M6 gate)

New tool, new module `sofa_mcp/observer/inverse_solver.py`. Uses `QPInverseProblemSolver`. Tool inputs: scene_path, effector_node_path, target_position, actuator_paths, steps. Returns actuator values that achieve target + JSON trajectory. ~180 LOC.

This is the second README demo — "give a target effector position, watch the robot reach it."

### Phase 5 — Open the door (no maintenance commitment)

- LICENSE — MIT. ⏳
- CONTRIBUTING.md — five lines, no SLA. ⏳
- `.github/ISSUE_TEMPLATE/bug.md` — minimal (SOFA version, OS, traceback, repro). ⏳
- `pyproject.toml` — author placeholder + top-of-file SOFA version comment. ⏳
- ✅ **Fixed three breaking test files** (2026-05-02): `test_observer/test_stepping.py` (`sample_data` → `data_preview` rename, 3 sites); `test_architect/test_scene_writer.py` (full rewrite around the `createScene(rootNode)` contract — single `MINIMAL_SCENE` constant, `checks` assertion updated to the `rule_*_*` slug schema introduced in Step 1.5); `test_architect/test_component_query.py::test_search_sofa_components_unavailable` (search path moved from live factory to `plugin_cache.load_plugin_map` — repointed mocks to the new path). `pytest test/` is now 113/113 green.
- `.github/workflows/test.yml` — minimal CI. **Skipped** — would need a runner with SOFA v24.12 + SoftRobots + SoftRobots.Inverse + SofaPython3 built from source (~10 min build per CI run). Not portfolio-critical; revisit if/when there's an upstream SOFA Docker image we can lean on.

### Phase 4 — README rewrite

Rewrite around the demo. Hero: tri_leg_cables PNG + best `mcp_demo/*.webm` converted to GIF. Quick-start: Docker one-liner. One worked example: tri_leg_cables walkthrough. Tool table: 15 surviving + diagnose + inverse. Status: research/portfolio, no SLA.

### Phase 6.3 — Field-feedback punch list

Real-world dogfooding from the MOR-trunk authoring session (2026-04-30, full report at `docs/feedback_2026-04-30_mor_trunk_session.md`) surfaced 8 concrete fixes. None blocked the user's task; all were workaround-able. Listed in the user's priority order:

| # | Item | Severity | Why it matters |
|---|---|---|---|
| 1 | ✅ **Rule 7 false positives** — shipped 2026-05-02. `MeshTopology(src='@loader')` from `.vtk` flagged non-volumetric; `BarycentricMapping` parent check doesn't walk *up* to find topology (cable subnodes false-positive) | medium | agents will second-guess correct scenes; user without `validate_scene` reflex might rewrite a working scene |
| 2 | ✅ **`write_scene` UTF-8 encoding** — shipped 2026-05-02. Fails on em-dashes in docstrings (same bug class as the Step 1.5+ encoding fix in `scene_writer.py:149,203`, but `write_scene` was missed) | medium | every multi-paragraph docstring an LLM agent writes hits this |
| 3 | **`find_indices_by_region` VTK support** — returns "Could not extract vertices" on `.vtk` (a primary SOFA mesh format) | medium | coverage gap on a primary format; ROM workflows often need exact tip/fixed-end indices at script-author time |
| 4 | ✅ **`diagnose_scene` verbose flag** — shipped 2026-04-30. Hybrid allowlist + tail-anchor filter via shared `sofa_mcp/_log_compact.py`. Default `verbose=False` cuts `solver_logs` ~4× on cantilever_beam (30748 → 7070 chars); ratio expected higher on stiffer scenes where `EulerImplicitSolver` printLog dominates. Smell tests still scan the full pre-compaction log | **high** | was the worst per-call token cost — 2 calls × ~30-50K tokens of log noise in the dogfood session |
| 5 | ✅ **`validate_scene` / `summarize_scene` log compaction** — shipped 2026-04-30 alongside #4 using the same shared filter. Validate's `SUCCESS:` sentinel now extracted+stripped (mirrors summarize's `SCENE_SUMMARY_JSON:` pattern). `verbose: bool = False` on both | medium | every iteration of the draft → summarize → validate loop now pays a smaller log cost |
| 6 | **`get_plugins_for_components` deprecated/meta handling** — `GenericConstraintSolver` returns "not found" instead of "deprecated, use NNCGConstraintSolver"; `RequiredPlugin` (meta) returns "not found" rather than being silently skipped | low | inconsistent with `validate_scene`'s clean migration message |
| 7 | **SKILL.md: `claude mcp add` registration section** — agent had to figure out the `--scope user` vs project-scope footgun and the `/mcp` reconnect step on its own | low | onboarding gap for new users |
| 8 | ✅ **`render_scene_snapshot` shipped explicit-triangle rendering 2026-05-02** — reads OglModel `position` + `triangles` (decomposes `quads` if needed); falls back to MO + sibling topology, then to point glyph cloud. Hull fallback removed. Regression test in `test/test_observer/test_renderer.py`. | shipped | — |

**Strategic note:** the user assessed the MCP as "net positive — `validate_scene` and `diagnose_scene` together caught the deprecation + verified physics in two calls, work that would have been ~5 manual cycles otherwise." Friction was concentrated in three areas: (a) false-positive health rules, (b) verbose log volume / token cost, and (c) the convex-hull render. As of 2026-05-02 all three are resolved. Items #3, #6, #7 are lower-severity ergonomic gaps that don't block agent workflows.

---

## Suggested execution order

Portfolio-first ordering (2026-05-02): the project is primarily a portfolio piece, secondarily a beginner-friendly tool. That moves visible artifacts (renders, headline demo, README) ahead of install ergonomics (Docker).

**M5 ✅ + M6 ✅ passed 2026-05-02** → 5 (LICENSE + fix two broken test files) → 4 (README rewrite — the actual portfolio artifact, last so it can showcase #8 + 6.2's tri-leg demo) → 3 (Docker, deferred — beginner-install ergonomics, not portfolio) → 6.3 #3/#6/#7 (low-severity ergonomic cleanups).

If energy is constrained: ship 6.3 #8 + 6.2 + Phase 5 + Phase 4 as v0.1 (portfolio-ready). Docker and the low-severity 6.3 items can wait until someone actually wants to run it locally without building SOFA from source.

---

## Pending milestones (manual stop-and-chat gates)

### M3 — Docker container runs the headline ⏳ (after Phase 3)
On a fresh machine: `docker run -p 8000:8000 sofa-mcp` brings up the server; tools/list and validate_scene against tri_leg_cables both work.

### M4 — README reads cold ⏳ (after Phase 4 draft)
A non-SOFA reader answers "what is this for / who is it for / how do I run it / what does it produce" in <5 minutes.

### M5 — Diagnose toolkit *finds real bugs* ✅ (passed 2026-05-02)
Passed via real-world dogfooding rather than the formal 4-fixture rubric at `docs/specs/2026-05-02-m5-gate.md` — the toolkit held up across the user's actual authoring sessions, which is the bar that matters. Rubric remains on disk as a reference artifact.

### M6 — Inverse-solver demo converges ✅ (passed 2026-05-02)
`archiv/tri_leg_inverse.py`: three legs, three goals, `QPInverseProblemSolver`. Automated regression in `test/test_observer/test_inverse_authoring.py` asserts no convergence stall + no QP infeasibility over 80 steps. User confirmed `/tmp/tri_leg_inverse.png` shows each leg tip at its goal.

(M1, M2 passed — see `docs/progress.md`.)

---

## Files yet to create / modify

For **6.1 Steps 4–5, Phases 3, 5, 6.2, 4** — see the spec at `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md` and the per-phase sections above.

---

## Verification (end-to-end)

End-state check that proves the whole plan worked. Items 1–6 are the portfolio-ready v0.1 bar; items 7–8 are the beginner-install bar (deferred).

1. `validate_scene` on `tri_leg_cables.py` succeeds.
2. `render_scene_snapshot` produces a PNG showing three-leg deformation with real surface mesh (not a convex hull).
3. `diagnose_scene` on a deliberately broken scene names the right anomaly + suggests a concrete fix.
4. `run_inverse_problem` on a tri-leg variant + target reaches target within tolerance; final-frame render shows the robot at the target.
5. `pytest test/` exits 0 (after Phase 5 test fixes).
6. README cold-read passes M4; `tools/list` returns ~21 tools, all of which appear somewhere in README or SKILL workflow.
7. `docker build -t sofa-mcp .` succeeds on a fresh machine in <45 minutes.
8. `docker run -p 8000:8000 sofa-mcp` exposes the MCP server on `http://127.0.0.1:8000/mcp` within 60 seconds.

---

## Effort estimate (remaining work)

- Phase 6.1 M5 gate: ✅ passed 2026-05-02 via dogfooding.
- Phase 6.3 remaining: ~half a day total for #3 + #6 + #7 (VTK reader, deprecated/meta plugin handling, MCP registration docs — all low severity).
- Phase 3: ~half a day
- Phase 6.2: ~1 day
- Phase 5: ~half a day
- Phase 4: ~1 day

**Remaining: ~3.5-4 days sequentially** (down from ~4-5 after Step 4 + Phase 6.3 high-leverage items shipped). Less if phases parallelize. End state reads as a *capable* tool, not just a polished one. Phases 1-5 ship as v0.1 (portfolio-ready); 6.2 lands as v0.2 (the substantive features that earn the deeper claim).
