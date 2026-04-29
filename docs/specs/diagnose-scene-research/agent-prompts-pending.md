# Pending agent prompts for `diagnose_scene` review

Re-launch each of these as a sub-agent **after** the permission allowlist is configured (see bottom of this file). All agents should read `docs/specs/2026-04-25-diagnose-scene-design.md` (the design spec) and `docs/specs/diagnose-scene-review-findings.md` (Agent 1 + Agent 4 findings — don't duplicate that work) before starting.

Common output format for all data-mining agents (under 700 words):
- Executive summary (3-5 sentences)
- 8-12 patterns/findings each with: source link, content summary, applicability to our smell tests/playbook
- Recommended additions to smell tests (with rationale)
- Recommended additions to playbook (with rationale)
- Anything that contradicts the spec or Agent 1/Agent 4 findings

## Agent 2 — Scene pattern miner (subagent_type: Explore)

Empirically validate the Scene Health Rules at `skills/sofa-mcp/sofa-mcp/SKILL.md` (the "Scene Health Rules" section) against actual SOFA example scenes in `~/workspace/sofa/src/` and `~/workspace/sofa/plugins/`. Find Python files containing `def createScene` and XML scene files (`.scn`, `.xml`). For each rule: confirmed / partial / contradicted. Report top alternatives our rules miss (with prevalence), patterns we haven't codified, and co-occurrence stats for the most common 5-10 component classes — especially: which constraint solvers appear with FreeMotionAnimationLoop, which constraint corrections, which linear solvers pair with EulerImplicitSolver, prevalence of VisualStyle, structure of collision-equipped scenes. Cite file paths.

## Agent 3 — SOFA recent closed issues (subagent_type: general-purpose)

Mine `sofa-framework/sofa` closed issues from the past ~24 months for debug-flavored stories. Use `gh issue list --repo sofa-framework/sofa --state closed --limit 200 --search "sort:updated-desc"` then sample 25-30 most-substantive (high comments, references to specific components, clear what-broke + how-diagnosed + what-fix). De-prioritize docs/CI/build/typo issues. **Do not duplicate the patterns Agent 4 already found** (read `diagnose-scene-review-findings.md` first).

## Agent 5 — SOFA discussions Q&A recent (subagent_type: general-purpose)

Mine `sofa-framework/sofa` Discussions tab Q&A category, past ~18 months. Try `gh api graphql -f query='query { repository(owner: "sofa-framework", name: "sofa") { discussions(first: 50, orderBy: {field: UPDATED_AT, direction: DESC}) { nodes { number title category { name } answer { body } comments(first: 5) { nodes { body } } } } } }'` or WebFetch fallback on `https://github.com/sofa-framework/sofa/discussions`. Sample 20-25 substantive answered Q&A threads. Especially look for threads where someone enabled `printLog=True` and showed output; threads with investigation flows; threads about specific solver internals.

## Agent 6 — SOFA discussions older / non-Q&A (subagent_type: general-purpose)

Mine `sofa-framework/sofa` Discussions older than 18 months AND non-Q&A categories (General, Show and Tell, Ideas). Sample 20-25 substantive threads. Especially: "common pitfalls" threads, debug technique walkthroughs, "I solved X by doing Y" posts, threads about scene structure / health, threads about specific component classes the smell tests reference. **Note:** previous run hit the org monthly token limit; keep sampling tight.

## Agent 7 — SOFA docs general (subagent_type: general-purpose)

Mine `https://sofa-framework.github.io/doc/` for general/tutorial/FAQ/troubleshooting/best-practices content. SKIP per-component reference pages (Agent 8 covers those). Especially look for: explicit lists of "what every SOFA scene needs" (compare to our Health Rules), explicit debug techniques, common error messages and meanings, scene-authoring patterns the docs explicitly recommend or warn against, anything that contradicts our hand-written rules.

## Agent 8 — SOFA docs component reference (subagent_type: general-purpose)

Mine `https://sofa-framework.github.io/doc/` per-class component reference. Priority components: `EulerImplicitSolver`, `RungeKutta4Solver`, `SparseLDLSolver`, `CGLinearSolver`, `SparseDirectSolver`, `NNCGConstraintSolver`, `LCPConstraintSolver`, `BlockGaussSeidelConstraintSolver`, `GenericConstraintCorrection`, `LinearSolverConstraintCorrection`, `UncoupledConstraintCorrection`, `MechanicalObject`, `TetrahedronFEMForceField`, `FreeMotionAnimationLoop`, `DefaultAnimationLoop`. For each: what `printLog=True` outputs (verified Y/N — note unverified, don't fabricate), other useful Data fields (e.g., `verbose`, `f_listening`, `tags`), required dependencies, common parameters and ranges, documented common errors. Output as a per-component table.

## Agent 9 — SoftRobots family (subagent_type: general-purpose)

Mine `SofaDefrost/SoftRobots` and `SofaDefrost/SoftRobots.Inverse` — issues + discussions for both. Combined budget 15-25 substantive items. Especially: cable-actuator gotchas (CableConstraint), pneumatic chamber issues, `printLog=True` on `QPInverseProblemSolver` (what does it output? high info density?), inverse-solver convergence problems, mapping between forward-sim and inverse-sim. The QPInverseProblemSolver finding is the most important — validates a key design assumption of our toolkit.

---

## Permissions to allowlist before re-launching

Add to `.claude/settings.local.json` `allow` array:
- `Bash(gh:*)` — for GitHub API access on public repos (no auth needed)
- `Bash(find:*)` — for Agent 2 file discovery
- `Bash(grep:*)` — for Agent 2 pattern mining
- `Bash(ls:*)` — for Agent 2 directory traversal
- `WebFetch(domain:github.com)`
- `WebFetch(domain:api.github.com)`
- `WebFetch(domain:sofa-framework.github.io)`
- `WebFetch(domain:sofa-framework.org)`
- `WebSearch` — confirm enabled (Agent 4 used it as fallback)

Use the `update-config` skill or edit the file directly. Once permissions are in, launch all 7 agents in parallel (single message, multiple Agent tool calls), background mode.
