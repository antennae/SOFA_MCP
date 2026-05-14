# Test Prompts — `generate_volume_mesh`

Use these prompts to test the tool against the existing STL files in `meshes/`.
Start the server first: `~/venv/bin/python sofa_mcp/server.py`

---

## 1. Basic conversion

Tests the default pipeline end-to-end.

```
Convert meshes/prostate.stl to a volume mesh using generate_volume_mesh.
Use default parameters. What is the output file path?
```

Expected: `success: true`, output path ending in `.sofa_mcp_results/volume_<timestamp>.vtk`.

---

## 2. Custom output path

Tests that the user-specified output path is respected.

```
Run generate_volume_mesh on meshes/prostate.stl and save the result to
/tmp/prostate_volume.vtk. Confirm the output_file in the response matches
the path I gave.
```

Expected: `output_file` is `/tmp/prostate_volume.vtk`.

---

## 3. Mesh size factor — coarse vs fine

Tests that mesh_size_factor controls mesh density.

```
Generate a volume mesh from meshes/prostate.stl twice:
  - Once with mesh_size_factor=2.0 (coarse), saved to /tmp/prostate_coarse.vtk
  - Once with mesh_size_factor=0.5 (fine), saved to /tmp/prostate_fine.vtk
Then call mesh_stats on both output files. Which one has more cells?
```

Expected: the fine mesh (`0.5`) has significantly more cells than the coarse one (`2.0`).

---

## 4. Duplicate vertex removal

Tests the remove_duplicates flag on a mesh that may have shared vertices.

```
Call generate_volume_mesh on meshes/inner_0.stl with remove_duplicates=true.
Does it succeed? Does the response mention how many duplicate vertices were removed?
```

Expected: success, console output from `remove_duplicate_vertices` printed server-side.

---

## 5. Invalid input path

Tests fail-fast on missing file.

```
Call generate_volume_mesh with stl_path="meshes/does_not_exist.stl".
What error do you get?
```

Expected: `success: false`, error mentioning the missing file path.

---

## 6. SOFA integration — load the generated mesh in a scene

Tests the full workflow: generate mesh, then use it in a SOFA scene.

```
1. Generate a volume mesh from meshes/prostate.stl using generate_volume_mesh.
   Note the output_file path.
2. Write a minimal SOFA scene that loads the generated VTK mesh using
   MeshVTKLoader and adds a MechanicalObject on top of it.
3. Validate the scene with validate_scene.
Does SOFA successfully load the mesh?
```

Expected: agent uses the `MeshVTKLoader(filename=...)` hint from the response,
`validate_scene` returns success.

---

## 7. All three inner meshes in one session

Tests that repeated calls in the same session don't interfere (GMSH model isolation).

```
Generate volume meshes for all three files:
  meshes/inner_0.stl, meshes/inner_1.stl, meshes/inner_2.stl
Call them one after another using generate_volume_mesh.
After each call, verify success. Do all three succeed independently?
```

Expected: all three succeed; each produces a distinct output file.
