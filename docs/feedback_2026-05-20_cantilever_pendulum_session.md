# Feedback — 2026-05-20 cantilever pendulum design session

> **Status (2026-06-13): items #1–#4 RESOLVED.** #1 (`template` ignored), #2 (no
> `templates` list), #3 (universal-field noise) fixed by the `query_sofa_component`
> rework — see `docs/specs/2026-06-13-query-sofa-component-rework.md`. The response
> now honors `template` (template-matched scaffold → correct per-template shapes),
> returns `templates`/`default_template`/`source_header`, and strips the 6 universal
> `BaseObject` fields by default (`include_universal=True` to keep them). #4 (server
> registration with Claude Code) addressed in README "Connect your agent" + SKILL.md
> bootstrap. #5 is a standing workflow note, not a bug.

Context: designing a pinned-hinge cantilever pendulum scene in
`/home/sizhe/workspace/MOR/scene/cantilever_pendulum/`. Used the
MCP via curl (server not registered as a Claude Code integration)
to query `PartialFixedProjectiveConstraint` and
`RestShapeSpringsForceField` after an earlier guess about a
6-element `fixedDirections` on `Rigid3d` proved incorrect.

## 1. `query_sofa_component` ignores the `template` parameter

- Called with `template="Rigid3d"`. Response was identical to the
  default call: `fixedDirections: fixed_array<bool,3>, value=[1 1 1]`.
- Source (`PartialFixedProjectiveConstraint.h:66`) defines
  `typedef fixed_array<bool, NumDimensions> VecBool;` and the `.cpp`
  registers both `Vec3Types` and `Rigid3Types`. For `Rigid3d`,
  `NumDimensions=6` — so the actual instantiation has 6 elements,
  not 3.
- Effect: the agent can't tell from the MCP response that the
  Data-field shape differs across templates. We had to grep the
  SOFA source to recover this.
- Suggested fix: make `query_sofa_component` template-aware. At
  minimum, surface per-template `coord_total_size` /
  `deriv_total_size`, and re-evaluate `fixed_array<bool, N>` sizes
  using the requested template.

## 2. No way to discover which templates a class is registered for

- The response object has no `templates: [...]` field. Had to grep
  the `.cpp` for `.add<Component<Type>>()` calls to learn that
  `PartialFixedProjectiveConstraint` is registered for `Vec1Types`,
  `Vec2Types`, `Vec3Types`, `Vec6Types`, `Rigid2Types`,
  `Rigid3Types`.
- Suggested fix: return `templates: ["Vec3d", "Rigid3d", ...]` in
  the `query_sofa_component` payload. Or add a dedicated
  `list_templates(component_name)` tool.

## 3. Output verbosity — universal boilerplate Data fields

- Every `query_sofa_component` response includes 6 fields that are
  inherited from `BaseObject` and constant across all components:
  `name`, `printLog`, `tags`, `bbox`, `componentState`, `listening`.
  Useless context-burning noise when querying many components.
- Suggested fix: `include_universal: bool = false` flag (default
  False) that strips these in the default path. Or a separate
  `query_sofa_component_minimal` tool that returns only the
  component-specific fields.

## 4. Server registration with Claude Code

- Started `~/venv/bin/python sofa_mcp/server.py` per SKILL.md.
  Server listens at `http://127.0.0.1:8000/mcp` but Claude Code's
  `ListMcpResourcesTool` only sees `claude.ai Notion`. Tools are
  not available via the native function-call surface — agents have
  to hit `curl` manually.
- Suggested fix: document in SKILL.md how to register the local
  server with Claude Code's MCP config so the tools show up as
  native functions in `ListMcpResourcesTool` / `ToolSearch`. (Per
  Claude Code docs, this is a `.mcp.json` or
  `~/.claude/settings.json` entry.) Without this, the agent loses
  the deferred-tool / per-tool-schema affordances that make MCP
  tools first-class.

## 5. Workflow observation — discovery before design

The skill's "Workflow: natural language → validated scene"
correctly puts plugin resolution + component query *before* writing
`createScene`. In this session I skipped that and tried to design
the scene from training-data knowledge, which led to two wrong
calls (`SubsetTopologicalMapping` Data shape, 6-element
`fixedDirections`). Both would have been caught by step 2 of the
skill workflow. Worth keeping the SKILL.md emphasis sharp — even
experienced agents skip the discovery step under time pressure.
