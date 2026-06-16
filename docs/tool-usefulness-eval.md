# Tool Usefulness Evaluation

*2026-06-16. Evaluator: Claude (agent perspective). Scope: the 22 tools registered in `sofa_mcp/server.py` as of this date.*

## Method

A tool earns its slot on the MCP surface only if it gives the **consuming agent**
something it **cannot already do** with its native `Read` / `Write` / `Edit` /
`Bash` tools, or already know from its SOFA training data. By that yardstick the
22 tools fall into four tiers.

This is a deliberately critical pass — the goal is a tight, all-load-bearing
surface for a portfolio piece, not flattery. It complements the earlier
"Usefulness assessment (agent perspective)" in
`docs/feedback_2026-04-30_mor_trunk_session.md`, which asked "is the MCP useful
*at all*"; this doc asks "does *each tool* pull its weight."

## Tier 1 — Load-bearing (the reason this MCP exists)

Wrap SOFA *runtime* or *local build state* — genuinely unknowable without
executing SOFA.

| Tool | Why it's irreplaceable |
|---|---|
| `validate_scene` | "Does it init + step?" is a runtime fact. Structured bool + compacted log. The core oracle. |
| `diagnose_scene` | Health Rules + per-step metrics + smell tests. The debugging core; nothing else produces this. |
| `render_scene_snapshot` | Visual geometry signal an LLM literally cannot generate from text. Also the portfolio centerpiece. |
| `query_sofa_component` | Per-template Data schema from *this* build. Beats training data (version drift), can't be grepped. |
| `generate_volume_mesh` | Real GMSH computation. Not derivable, not greppable. |
| `mesh_stats` | Facts about the user's actual mesh files (bbox / topology / counts). |
| `get_plugins_for_components` | Which plugin to import for a class — build- and version-specific. |

## Tier 2 — Useful but secondary / situational

Real value, but narrower or partially overlapping.

| Tool | Note |
|---|---|
| `search_sofa_components` | Mostly a hallucination-guard + long-tail discovery. Agent often already knows class names. |
| `perturb_and_run` | Strong *during debugging* (hypothesis testing), idle otherwise. |
| `enable_logs_and_run` | Same — debugging-only probe. |
| `run_and_extract` + `process_simulation_data` | Quantitative trajectory extraction, but the two-tool split is clumsy and the metrics overlap `diagnose_scene`. |
| `find_indices_by_region` | Useful for BoxROI-style index lookup — but still has the VTK gap (Phase 6.3 #3). |
| `summarize_scene` | Its `checks` list **is** `diagnose_scene`'s `anomalies` field. Justified only as the *cheap* structural pass (1 subprocess vs diagnose's 2). |

## Tier 3 — Thin wrappers, dominated by the agent's native tools

In a Claude Code session the consuming agent already has `Read` / `Write` /
`Edit` / `Bash`. These add little SOFA-specific value on top.

| Tool | Problem |
|---|---|
| `load_scene` | Pure `Read` redundancy. |
| `write_scene` | Pure `Write` redundancy (the UTF-8 handling `Write` already does). |
| `resolve_asset_path` | `~`-expand + existence check — that's `ls` / `Bash`. |
| `update_data_field` **and** `patch_scene` | Two different scene-patching implementations, both dominated by the more flexible native `Edit`. Pick one or drop both. |
| `health_check` | Returns a static dict; fully subsumed by `server_status`. |

## Tier 4 — Justified infra

| Tool | Note |
|---|---|
| `server_status` | Low-frequency, but earns its place given the documented silent-crash history (pneunet session). Fold `health_check` into it. |
| `write_and_test_scene` | The *good* combined tool (write + validate + auto-correct). Makes standalone `write_scene` redundant. |

## Bottom line

The MCP is strongest exactly where the MOR-trunk note said: a
**runtime/validation oracle** (Tier 1). The weakness is **surface bloat** —
Phase 2 deliberately cut 19→15 tools, but diagnose/probes/query/status additions
pushed it back to **22**, and ~6 of those are thin file-IO/patch wrappers the
consuming agent can already do natively. For a portfolio piece, a tight,
all-load-bearing surface reads better than a long list with redundancy in it.

### Trim executed 2026-06-16 (22 → 17)

Surface-only removals — every underlying function stays (still used
internally and still covered by its tests); only the `@mcp.tool()` wrapper
was removed:

- Cut `load_scene` — `Read` covers it. (Function still used by `patch_scene`'s impl.)
- Cut `write_scene` — `Write` covers it; `write_and_test_scene` is the useful variant.
- Cut `resolve_asset_path` — `Bash`/`ls` covers it. (Function still used by `mesh_stats` + `find_indices_by_region`.)
- Cut `health_check` — folded into `server_status` (now also returns `version`).
- Cut `patch_scene` (textual, dominated by native `Edit`); kept `update_data_field`
  (semantic field patch). On closer reading the two are **complementary, not
  duplicates** — the original "collapse into one" note was wrong. Also fixed
  `update_data_field`'s non-atomic write (code_review.md #8) via tempfile + `os.replace`.

Docs updated: `README.md`, `intro.md`, `skills/sofa-mcp/sofa-mcp/SKILL.md`,
`references/debugging-playbook.md` (the playbook's `patch_scene` calls now use
`update_data_field`). Verified: `test/test_architect/` 74 passed,
`sofa_mcp/optimizer/test_patcher.py` 6 passed, MCP transport boots the trimmed
server clean.

### Two overlaps left in place (deliberately not cut)

- `summarize_scene` vs `diagnose_scene` — cheap structural pass vs full runtime; both kept.
- `run_and_extract` + `process_simulation_data` — clumsy split, but real quantitative extraction; both kept.
