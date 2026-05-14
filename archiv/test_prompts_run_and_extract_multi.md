# Test Prompts — `run_and_extract_multi`

Use these prompts to test the new tool against the existing example scenes.
Start the server first: `~/venv/bin/python sofa_mcp/server.py`

---

## 1. Basic multi-field extraction (position + velocity)

Tests that two fields from the same node are extracted correctly in a single run.

```
Run the cantilever beam scene (cantilever_beam.py) for 10 steps at dt=0.01.
Extract both the position and velocity of the mechanical object at node path
"solver_node/mo". Use keys "pos" and "vel". Show me the shape of each field
and the preview of the final step.
```

Expected: `fields.pos.data_shape` should be `[N, 3]`, same for `vel`.

---

## 2. Multi-node extraction (two different nodes)

Tests that fields from different nodes in the scene graph are resolved and extracted correctly.

```
Load the prostate scene (prostate.py). Run it for 5 steps at dt=0.01.
I want to extract position from the FEM mechanics node and also from the
visual model node. Use run_and_extract_multi with two entries:
  - node_path: "mechanics/mo", field: "position", key: "fem_pos"
  - node_path: "visual/visual", field: "position", key: "visual_pos"
Tell me the shape of each field.
```

Expected: two separate shape summaries; server should not run the simulation twice.

---

## 3. Invalid node path — fail-fast before simulation

Tests that a bad node path is caught before the animate loop starts (no wasted steps).

```
Try to run cantilever_beam.py for 50 steps using run_and_extract_multi with:
  - node_path: "solver_node/mo", field: "position", key: "pos"
  - node_path: "THIS_NODE_DOES_NOT_EXIST/mo", field: "position", key: "bad"
What error do you get, and does it mention the bad path?
```

Expected: `success: false`, error referencing `THIS_NODE_DOES_NOT_EXIST` before any steps run.

---

## 4. Invalid field name — fail-fast before simulation

```
Run cantilever_beam.py for 20 steps using run_and_extract_multi.
Extract "position" (key: "pos") and "NONEXISTENT_FIELD" (key: "bad")
both from node "solver_node/mo".
Confirm the error is raised before the simulation starts.
```

Expected: `success: false`, error mentioning `NONEXISTENT_FIELD`.

---

## 5. Duplicate key detection

```
Call run_and_extract_multi on cantilever_beam.py with these fields:
  - node_path: "solver_node/mo", field: "position", key: "pos"
  - node_path: "solver_node/mo", field: "velocity", key: "pos"
Both use the same key "pos". What happens?
```

Expected: `success: false`, error mentioning duplicate key.

---

## 6. Compare efficiency vs repeated run_and_extract

Tests the core motivation: one run vs two runs.

```
I need position and velocity from cantilever_beam.py over 30 steps (dt=0.01).
First, use run_and_extract twice (once per field) and note the two output files.
Then, use run_and_extract_multi with both fields in a single call and note its
output file. Confirm that run_and_extract_multi produces a single output file
named sim_data_multi_<timestamp>.json and that both fields are present inside it.
```

Expected: single output file with a `"fields"` key containing both `pos` and `vel`.

---

## 7. Soft robot scene — position + cable displacement

Tests against the cable-driven scene with fields from separate child nodes.

```
Run tri_leg_cables.py for 15 steps at dt=0.01 using run_and_extract_multi.
Extract:
  - position from the main body mechanical object (find the correct node path
    by calling summarize_scene first)
  - the displacement field from one of the cable actuator objects
Use keys "body_pos" and "cable_disp".
Report the shapes of both fields.
```

Expected: agent first calls `summarize_scene` to find node paths, then calls `run_and_extract_multi`.

---

## 8. Optional key defaults

Tests that omitting the `key` field uses the `node_path/field` default.

```
Call run_and_extract_multi on cantilever_beam.py for 5 steps with:
  - {"node_path": "solver_node/mo", "field": "position"}   (no key)
  - {"node_path": "solver_node/mo", "field": "velocity"}   (no key)
What keys appear in the output file's "fields" dict?
```

Expected: keys are `"solver_node/mo/position"` and `"solver_node/mo/velocity"`.

---

## 9. Large step count — verify sys.modules cleanup

Tests that running the tool multiple times in the same session does not accumulate
scene modules in memory (regression test for the sys.modules leak fix).

```
Call run_and_extract_multi on cantilever_beam.py three times in a row,
each time extracting position and velocity for 5 steps.
After each call, call health_check to confirm the server is still responsive.
All three calls should succeed independently.
```

Expected: all three succeed, server stays healthy.

---

## 10. Output file location

Tests that the results file lands in `.sofa_mcp_results/` relative to the
project root, not the shell CWD.

```
Run cantilever_beam.py for 5 steps using run_and_extract_multi.
What is the full absolute path of the output file returned in "output_file"?
Does it end with .sofa_mcp_results/sim_data_multi_<timestamp>.json?
```

Expected: path anchored to the project root, filename prefixed with `sim_data_multi_`.
