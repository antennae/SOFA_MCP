# SOFA_MCP — Portfolio Polish, Community-Ready Posture

*Last updated 2026-04-30 (Step 3 shipped)* — forward-looking only. For completed work, see `docs/progress.md`. Technical reference for the diagnose toolkit lives in `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md`.

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
| 6.1 — Investigative debugging toolkit | 🚧 in progress | Steps 1, 1.5, 2, 3 done (see progress.md); Steps 4–5 pending |
| 6.3 — Field-feedback punch list | 🚧 partial | items #1, #2, #4, #5 shipped (2026-04-30 / 2026-05-02); 4 of 8 still pending |
| 4 — Tell the story (README + SKILL) | 🚧 partial | SKILL.md tightened; README rewrite pending |
| 3 — Wrap the install (Dockerfile) | ⏳ pending | M3 gate |
| 6.2 — Inverse-problem solver | ⏳ pending | M6 gate |
| 5 — Open the door (LICENSE, CI, etc.) | ⏳ pending | minimum CI viability still needs the test fixes from §5.5 |

---

## Phase 6.1 — Investigative debugging toolkit (current focus)

**Framing:** the LLM agent debugs *behavioral* bugs in scenes that already run. The MCP doesn't return "the bug is X." The MCP provides good probes; the agent does the reasoning. Existing tools are partial probes; the new pieces are a sanity-report tool and a small set of targeted probes.

### Step 2 — Subprocess foundation + sanity report skeleton ✅ (2026-04-29)

Shipped — see `docs/progress.md` Step 2 entry. `diagnose_scene` MCP tool exists end-to-end; sanity-report shape (`success`, `metrics`, `anomalies`, `init_stdout_findings`, `solver_logs`, `scene_summary`) is the contract Step 3 fills out. Out-of-scope in Step 2 and explicitly stubbed for Step 3: `printLog` toggling, runtime/regex/structural smell tests, log truncation.

### Step 3 — Smell test catalog ✅ (2026-04-30)

Shipped — see `docs/progress.md` Step 3 entry. 6 rules + printLog activation + log truncation, all green in `pytest test/test_observer/test_diagnostics.py` (25 tests) and `test/test_architect/test_mcp_transport.py` (3 tests). Zero false positives on the four `archiv/` scenes. CG/LCP regex arm of `solver_iter_cap_hit` and per-step bucketing for `qp_infeasible_in_log` deferred to a future iteration when known-cap-hit fixtures and step-boundary-stable log formats are available.

### Step 4 — Probe library (4 probes) ⏳ (NEEDS REVIEW)

Targeted instrumentation — force/energy access, time-series sanity, mapping consistency, constraint convergence. Each probe is a focused helper the agent can call from the playbook. Full spec §Step 4.

### Step 5 — Playbook integration + tests + M5 gate ⏳ (NEEDS REVIEW)

Wire probes + sanity report into a `diagnose_scene` tool; integration tests; M5 user gate (does the toolkit *find real bugs* in 3-4 deliberately-broken scenes?). Full spec §Step 5.

---

## Other phases (waiting on 6.1 completion)

### Phase 3 — Dockerfile (M3 gate)

Derive from `~/workspace/prostate-biobot/dockerfile`. Strip ROS2, torch, PyGeM. Keep SOFA v24.12 source build + SoftRobots + SoftRobots.Inverse. Adapt for SOFA_MCP's Python deps. Expose 8000. **Do this after 6.1 closes** so the Dockerfile is sized to the final dependency set.

### Phase 6.2 — `run_inverse_problem` tool (M6 gate)

New tool, new module `sofa_mcp/observer/inverse_solver.py`. Uses `QPInverseProblemSolver`. Tool inputs: scene_path, effector_node_path, target_position, actuator_paths, steps. Returns actuator values that achieve target + JSON trajectory. ~180 LOC.

This is the second README demo — "give a target effector position, watch the robot reach it."

### Phase 5 — Open the door (no maintenance commitment)

- LICENSE — MIT.
- CONTRIBUTING.md — five lines, no SLA.
- `.github/ISSUE_TEMPLATE/bug.md` — minimal (SOFA version, OS, traceback, repro).
- `pyproject.toml` — top-of-file SOFA version comment.
- **Fix two breaking test files**: `test_observer/test_stepping.py` (`sample_data` → `data_preview`) and `test_architect/test_scene_writer.py` (`add_scene_content` contract drift — recommend rewriting as one happy-path integration test against `tri_leg_cables.py`). Until this lands, `pytest test/` shows 7 pre-existing failures unrelated to recent work.
- `.github/workflows/test.yml` — minimal CI; optional.

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
| 8 | **`render_scene_snapshot` shows convex hull, not mesh geometry** — PyVista falls back to point-cloud→hull rendering because no topology is passed; cable-subnode point clouds get rolled in too | medium-high | the render tool exists for visual sanity ("did gravity pull the right way?"); a hull obscures exactly the deformation you want to see |

**Strategic note:** the user assessed the MCP as "net positive — `validate_scene` and `diagnose_scene` together caught the deprecation + verified physics in two calls, work that would have been ~5 manual cycles otherwise." Friction is concentrated in three areas: (a) false-positive health rules, (b) verbose log volume / token cost, and (c) the convex-hull render. None of these blocked the task. Items #1, #2, #4, and #8 have the highest "agent embarrassment" or token-cost impact and are prime candidates to interleave ahead of Step 4. Item #4 in particular has cross-cutting leverage — every long debug session pays it.

---

## Suggested execution order

**6.1 Step 4 (default next)** → 6.1 Step 5 → 6.3 (field-feedback punch list) → 3 (Docker) → 6.2 (inverse) → 5 (door + test fixes) → 4 (README rewrite, last so it can showcase everything that actually works).

Alt order if user-facing polish or token budget matters more than completing the debug toolkit: lift the high-leverage 6.3 items (#1 rule-7 FPs, #2 write_scene UTF-8, #4 diagnose_scene verbose flag, #8 render geometry) ahead of Step 4 — these directly affect agent embarrassment / token cost in real authoring sessions, while Step 4's probe library is mostly load-bearing for the M5 gate. #4 in particular has the strongest case for jumping the queue, since every long debug session (including the M5 gate runs themselves) pays its cost.

If energy is constrained: ship Phases 1–5 as v0.1 (portfolio-ready), sit on it, decide whether Phase 6.2 is worth the investment based on whether anyone actually finds and uses v0.1.

---

## Pending milestones (manual stop-and-chat gates)

### M3 — Docker container runs the headline ⏳ (after Phase 3)
On a fresh machine: `docker run -p 8000:8000 sofa-mcp` brings up the server; tools/list and validate_scene against tri_leg_cables both work.

### M4 — README reads cold ⏳ (after Phase 4 draft)
A non-SOFA reader answers "what is this for / who is it for / how do I run it / what does it produce" in <5 minutes.

### M5 — Diagnose toolkit *finds real bugs* ⏳ (after 6.1)
Feed 3-4 scenes with behavioral bugs (cables not actuated, wrong material modulus, missing collision pipeline, wrong mapping). The agent uses the new probes + sanity report to (a) flag the right anomaly, (b) propose a hypothesis a human SOFA dev would also propose, (c) verify by running the right follow-up probe. Bar: "junior SOFA dev with no help, not stochastic parrot."

### M6 — Inverse-solver demo converges ⏳ (after 6.2)
Tri-leg variant with a target effector position. Solver converges in <200 steps. Final-frame render shows the robot reaching the target.

(M1, M2 passed — see `docs/progress.md`.)

---

## Files yet to create / modify

For **6.1 Steps 4–5, Phases 3, 5, 6.2, 4** — see the spec at `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md` and the per-phase sections above.

---

## Verification (end-to-end)

End-state check that proves the whole plan worked:

1. `docker build -t sofa-mcp .` succeeds on a fresh machine in <45 minutes.
2. `docker run -p 8000:8000 sofa-mcp` exposes the MCP server on `http://127.0.0.1:8000/mcp` within 60 seconds.
3. `validate_scene` on `tri_leg_cables.py` succeeds.
4. `render_scene_snapshot` produces a PNG showing three-leg deformation.
5. `diagnose_scene` on a deliberately broken scene names the right anomaly + suggests a concrete fix.
6. `run_inverse_problem` on a tri-leg variant + target reaches target within tolerance.
7. `pytest test/` exits 0 (after Phase 5 test fixes).
8. README cold-read passes M4.
9. `tools/list` returns ~17 tools, all of which appear somewhere in README or SKILL workflow.

---

## Effort estimate (remaining work)

- Phase 6.1 Steps 4-5: ~half a day
- Phase 6.3 (field-feedback punch list): ~half a day for items #1/#2/#3/#6 (rule fixes + encoding + VTK reader + cache cleanup), ~half a day for #4 + #5 together (verbose flag pattern reused across `diagnose_scene` + `validate_scene` + `summarize_scene`), plus ~half a day for #8 (render geometry). So ~half a day minimum, ~1.5 days for the full punch list.
- Phase 3: ~half a day
- Phase 6.2: ~1 day
- Phase 5: ~half a day
- Phase 4: ~1 day

**Remaining: ~4-5 days sequentially** (was ~3-4 before 6.3 landed). Less if phases parallelize. End state reads as a *capable* tool, not just a polished one. Phases 1-5 ship as v0.1 (portfolio-ready); 6.2 lands as v0.2 (the substantive features that earn the deeper claim).
