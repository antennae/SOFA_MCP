# SOFA_MCP — Portfolio Polish, Community-Ready Posture

*Last updated 2026-04-29 (Step 2 shipped)* — forward-looking only. For completed work, see `docs/progress.md`. Technical reference for the diagnose toolkit lives in `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md`.

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
| 6.1 — Investigative debugging toolkit | 🚧 in progress | Steps 1, 1.5, 2 done (see progress.md); Steps 3–5 pending |
| 4 — Tell the story (README + SKILL) | 🚧 partial | SKILL.md tightened; README rewrite pending |
| 3 — Wrap the install (Dockerfile) | ⏳ pending | M3 gate |
| 6.2 — Inverse-problem solver | ⏳ pending | M6 gate |
| 5 — Open the door (LICENSE, CI, etc.) | ⏳ pending | minimum CI viability still needs the test fixes from §5.5 |

---

## Phase 6.1 — Investigative debugging toolkit (current focus)

**Framing:** the LLM agent debugs *behavioral* bugs in scenes that already run. The MCP doesn't return "the bug is X." The MCP provides good probes; the agent does the reasoning. Existing tools are partial probes; the new pieces are a sanity-report tool and a small set of targeted probes.

### Step 2 — Subprocess foundation + sanity report skeleton ✅ (2026-04-29)

Shipped — see `docs/progress.md` Step 2 entry. `diagnose_scene` MCP tool exists end-to-end; sanity-report shape (`success`, `metrics`, `anomalies`, `init_stdout_findings`, `solver_logs`, `scene_summary`) is the contract Step 3 fills out. Out-of-scope in Step 2 and explicitly stubbed for Step 3: `printLog` toggling, runtime/regex/structural smell tests, log truncation.

### Step 3 — Smell test catalog ⏳ (NEEDS REVIEW)

Three classes: §6.A runtime checks, §6.B regex pattern matches, §6.C structural checks (using the existing summarize_scene rule infrastructure as building blocks). Full spec at `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md` §Step 3.

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

---

## Suggested execution order

**6.1 Step 3 (next)** → 6.1 Step 4 → 6.1 Step 5 → 3 (Docker) → 6.2 (inverse) → 5 (door + test fixes) → 4 (README rewrite, last so it can showcase everything that actually works).

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

For **6.1 Steps 3–5, Phases 3, 5, 6.2, 4** — see the spec at `docs/specs/2026-04-26-diagnose-scene-plan-v2.1.md` and the per-phase sections above.

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

- Phase 6.1 Steps 3-5: ~1 day
- Phase 3: ~half a day
- Phase 6.2: ~1 day
- Phase 5: ~half a day
- Phase 4: ~1 day

**Remaining: ~4-5 days sequentially.** Less if phases parallelize. End state reads as a *capable* tool, not just a polished one. Phases 1-5 ship as v0.1 (portfolio-ready); 6.2 lands as v0.2 (the substantive features that earn the deeper claim).
