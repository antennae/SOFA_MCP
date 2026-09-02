  sofa-mcp feedback (as requested)

  - What worked well: diagnose_scene was the workhorse — nan_first_step + displacement_series + the compacted NNCG W/delta/lambda log block
  reproduced your divergence in one call, and the env override made the pulse-threshold and material-falsifier sweeps effortless (no scene
  edits). Log compaction with log_lines_dropped reporting is well judged.
  - Timeout gap: a 400-step hyperelastic run timed out with no way to raise the per-call budget, no async/job mode, and no indication
  whether the server was still busy afterwards. Long runs had to fall back to local scripts. Suggest: configurable timeout or a
  submit-then-poll pattern (server_status could report a running job).
  - rule_6 false positive: RestShapeSpringsForceField in the clamp child node is flagged error "no MechanicalObject in its ancestor chain",
  but SOFA resolves the parent node's MO via context and the pattern demonstrably works (it's the established corot clamp). The rule should
  walk context resolution the way SOFA does.
  - Minor: precedence between the dt argument and a scene that sets root.dt in createScene is undocumented.
