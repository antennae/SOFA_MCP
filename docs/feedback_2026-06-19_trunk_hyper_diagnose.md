# sofa-mcp feedback — 2026-06-19 (trunk_hyper FOM instability debug)

Session: debugging a hyperelastic trunk scene that (a) segfaulted in runSofa
(`drawHyperelasticTets`) and (b) diverged suddenly under gravity with no
actuation. Used the MCP after ~2h of manual SofaPython3 bisection.

**Status:** RESOLVED (2026-06-30), except friction #3(b). Branch
`feature/trunk-hyper-feedback-2026-06-19`:

- **Friction #1 (env passthrough)** — `diagnose_scene` now accepts `env={...}`,
  merged over the server environment (not replacing it) and applied to both the
  summarize and runner subprocesses
  (`sofa_mcp/observer/diagnostics.py`, `sofa_mcp/architect/scene_writer.py`).
- **Friction #2 (solver_logs noise)** — `compact_log` collapses runs of
  identical lines into `… (×N)` (`sofa_mcp/_log_compact.py`); byte-exact so a
  cap-hit count (e.g. `Convergence after 100`) stays distinct from the noise.
- **Friction #3 (per-step series)** — (a) `displacement_series` (per-step max
  displacement per MO; `null` marks a non-finite step) is now returned by
  `diagnose_scene`. (b) `min_element_volume` per-step series **deferred** as a
  roadmap item (needs per-step element-volume computation from topology).
- **Friction #4 (rule_6 false positive)** — confirmed by reproduction (a FF
  wired to a sibling-subtree MO via an explicit `mstate` link). rule_6 now
  exempts explicit `mstate` wiring, not just `object1`/`object2`
  (`sofa_mcp/architect/_summary_runtime_template.py`).
- **`regularizationTerm` win** — captured as a principle-shaped hint in the
  `solver_iter_cap_hit` row of `references/debugging-playbook.md` (investigate
  `delta`/`lambda`, then query the correction's fields), deliberately *not* an
  n=1 symptom→fix rule.

## What worked — genuinely useful

- **`diagnose_scene` was decisive.** One call (scene_path + steps=80 + a prose
  `complaint`) returned exactly the signal manual probing had missed:
  - `solver_iterations` per step → NNCG converged in **2 iters through step 72,
    then hit the 100-cap at steps 73–79**. That localized the failure to the
    constraint solve in one number series.
  - `solver_logs` showed `delta=[-nan…]`, `lambda=[-nan…]`, "No convergence:
    error = nan" at the blowup step → confirmed a NaN enters the constraint
    solve (not element inversion: my own min-J tracking showed minJ≈0.95 right
    until detonation).
  - `anomalies` (Health Rules) flagged `excessive_displacement` with the exact
    ratio, plus `solver_iter_cap_hit` listing the precise steps [73..79]. The
    `rule_6_forcefield_mapping` error on the RestShapeSpringsForceField (no MO
    in ancestor chain) is a real structural note (though it fires for the linear
    trunk too, so it wasn't the bug here — see "improvement" below).
  - `class_counts` / `scene_summary` confirmed the graph as loaded.
- **`query_sofa_component` found the fix.** Querying `GenericConstraintCorrection`
  surfaced a `regularizationTerm` field (default 0.0, "adds ε·I to the compliance
  W") that I did not know existed — that field IS the fix (ε=1.0 cured the
  divergence). This is the canonical "don't guess the Data fields" win. Also
  `search_sofa_components "ConstraintCorrection"` → the 4 variants instantly, and
  the `regularizationTerm` help text told me the mechanism, not just the name.
- Stateless HTTP (no session-id handshake needed) made curl/urllib scripting
  trivial. `initialize` → `tools/list` → `tools/call` just worked.

## Friction / improvement areas

1. **`diagnose_scene` honors no env / param overrides for the scene.** The scene
   reads `TRUNK_HYPER_MATERIAL` from the environment; the MCP server process has
   its own env, so I could only diagnose the default material (NeoHookean). An
   optional `env: {...}` or `scene_args` passthrough would let me diagnose the
   specific variant (MooneyRivlin) without editing the scene. (Worked out here
   because both materials fail identically, but that was luck.)
2. **`solver_logs` is enormous and mostly noise.** It dumped ~70 identical
   "Convergence after 2 iterations" lines + 2162 "log_lines_dropped". The
   signal (the 3 NaN lines at the blowup) was buried at the very end. A
   `solver_logs_tail` or "only lines from steps near the first anomaly" mode
   would cut the payload ~50× and surface the actual failure faster.
3. **No per-step field series for arbitrary metrics in `diagnose_scene`.** It
   returns `max_displacement_per_mo` as a scalar (final/peak), but the *trajectory*
   of max-disp (and ideally min element volume J) per step is what reveals
   "healthy until one step then detonates". I had to write my own min-J tracker.
   A built-in `min_element_volume` per-step series (it already knows the topology)
   would be high-value for hyperelastic-inversion debugging specifically.
4. **`rule_6_forcefield_mapping` false-positive-ish.** It flagged
   RestShapeSpringsForceField "has no MechanicalObject in its ancestor chain" for
   a node whose PARENT has the MO ('mo' on /root/Trunk, FF in /root/Trunk/fixed).
   The FF does resolve to the parent MO at runtime (the linear trunk runs fine),
   so the rule seems to only check the FF's own node, not the ancestor chain it
   claims to. Either the message or the check is off by one level.

## Net

The MCP turned a multi-hour manual bisection into a ~10-minute root-cause +
fix once I used it. The two highest-value calls were `diagnose_scene`
(localized the constraint-solver NaN) and `query_sofa_component` (found the
`regularizationTerm` fix field). Would have saved hours if used FIRST instead
of after manual probing — reinforces the "query before guessing" rule.
