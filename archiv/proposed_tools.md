# Proposed Tools for SOFA MCP

## 1. Visualization / Rendering

| Tool | Description |
|------|-------------|
| `render_scene_snapshot` | Headless render of the scene at a given step via offscreen VTK or SOFA's `ScreenshotManager` |
| `export_scene_to_vtk` | Write a VTK time series from a simulation run for external viewers (ParaView) |

## 2. Multi-Field / Multi-Node Extraction

| Tool | Description |
|------|-------------|
| `run_and_extract_multi` | Extract multiple fields (`position`, `velocity`, `force`) from multiple node paths in a single simulation run |
| `stream_simulation` | Step-by-step interactive control: inject actuator values at step N, read state, decide next input |

## 3. Inverse Problems / Goal-Directed Control

| Tool | Description |
|------|-------------|
| `run_inverse_problem` | Set an effector target position, run the inverse solver (`QPInverseProblemSolver`), return computed actuator inputs |
| `set_effector_target` | Update an effector's target position mid-simulation |

## 4. Parameter Sweeps / Batch Runs

| Tool | Description |
|------|-------------|
| `parameter_sweep` | Sweep a parameter (e.g., Young's modulus 1000→50000 over N samples), run each configuration, collect results |
| `compare_runs` | Compare metrics across multiple result files side-by-side |

## 5. Mesh Generation

| Tool | Description |
|------|-------------|
| `generate_volume_mesh` | Call GMSH or TetGen to tetrahedralize a surface `.stl`/`.obj` into a volumetric `.vtk`/`.msh` |
| `remesh_surface` | Resample a surface mesh to a target element count or edge length |

## 6. Collision / Contact Setup

| Tool | Description |
|------|-------------|
| `add_collision_pipeline` | Inject `CollisionPipeline`, `BruteForceBroadPhase`, `BVHNarrowPhase`, `DefaultContactManager`, and collision models onto specified nodes |
| `validate_collision_setup` | Verify collision geometry is present and compatible with scene topology |

## 7. Richer Metrics

| Tool | Description |
|------|-------------|
| `compute_strain_energy` | Extract internal elastic energy from force fields over a simulation run |
| `compute_reaction_forces` | Read forces at fixed boundary condition nodes |
| `compute_workspace` | For soft robots, map the reachable workspace of an effector across actuator input space |

## 8. Physical Robot Bridge (sim-to-real)

| Tool | Description |
|------|-------------|
| `connect_serial_device` | Open a serial port to a physical robot controller |
| `send_actuator_command` | Send pressure/cable displacement commands to hardware |
| `read_sensor_data` | Read encoders, IMUs, or force sensors from hardware |
| `calibrate_model` | Run a calibration loop: compare sim vs. real output, adjust material parameters iteratively |

## 9. Scene Templates / Snippets

| Tool | Description |
|------|-------------|
| `list_scene_templates` | Return available named templates (cantilever, soft robot, pneumatic chamber, cable-driven) |
| `instantiate_template` | Fill a named template with user parameters (mesh path, material properties, boundary conditions) |

## 10. Scene Graph Introspection at Runtime

| Tool | Description |
|------|-------------|
| `inspect_runtime_state` | After `Sofa.Simulation.init`, return the full state of a node: all data field names, types, and current values |
| `list_data_fields` | For a given node path in an initialized scene, list all accessible fields and their sizes |

---

## Priority Ranking

| Priority | Tool(s) | Rationale |
|----------|---------|-----------|
| 1 | `run_and_extract_multi` | Eliminates redundant simulation re-runs; high frequency pain point |
| 2 | `generate_volume_mesh` | Unblocks the most common mesh workflow gap (STL → tet mesh) |
| 3 | `render_scene_snapshot` | Agents can verify what they built visually |
| 4 | `run_inverse_problem` | Enables the core soft robotics use case (SoftRobots.Inverse) |
| 5 | `parameter_sweep` | Automates design exploration without N agent round-trips |
| 6 | `instantiate_template` | Reduces scene generation errors for common patterns |
| 7 | `stream_simulation` | Enables closed-loop control workflows |
| 8 | `inspect_runtime_state` | Debugging without guessing field names |
| 9 | Collision pipeline tools | Extends applicability to contact-heavy domains |
| 10 | Serial bridge / calibration | Completes the sim-to-real loop (stubs already exist) |
