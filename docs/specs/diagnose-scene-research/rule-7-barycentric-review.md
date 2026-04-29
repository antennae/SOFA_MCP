# Review: Rule 7 Extension — BarycentricMapping Parent Topology

**Verdict: Ship with refinements.** Two concrete gaps must be fixed before shipping. Full findings below.

## 1. Mechanistic Explanation

`BarycentricMapping::createMapperFromTopology()` (verified in `/home/sizhe/workspace/sofa/src/Sofa/Component/Mapping/Linear/src/sofa/component/mapping/linear/BarycentricMapping.inl`, lines 141–236) inspects the parent topology at init time and dispatches to one of eight typed mapper implementations by dynamic type check and element-count priority: tetra > hexa > quad > triangle > edge > fallback `MeshTopology`. When the parent topology is surface-only (triangles/quads) or edge-only, the mapper stores 2D or 1D barycentric coordinates relative to those lower-dimensional elements, so any child DOF that lies off-plane receives physically meaningless coordinates — it snaps to the nearest surface element centroid rather than to its true containing tetrahedron. The error `Cannot find edge 0 [28, 77] in triangle 0` (Agent 6 F6) is emitted by `BarycentricMapperMeshTopology::init()` when it attempts edge lookups on a topology container that contains only triangles.

## 2. Completeness of the Volumetric Set

**All eight mapper specializations confirmed from source:**

| Topology | Mapper | Volumetric? |
|---|---|---|
| `RegularGridTopology` | `BarycentricMapperRegularGridTopology` | **Only if `hasVolume()` true** (3D grid) |
| `SparseGridTopology` | `BarycentricMapperSparseGridTopology` | **Only if `hasVolume()` true** |
| Any `TopologyContainer` with hexahedra | `BarycentricMapperHexahedronSetTopology` | Yes |
| Any `TopologyContainer` with tetrahedra | `BarycentricMapperTetrahedronSetTopology` | Yes |
| Any `TopologyContainer` with quads only | `BarycentricMapperQuadSetTopology` | No — surface |
| Any `TopologyContainer` with triangles only | `BarycentricMapperTriangleSetTopology` | No — surface |
| Any `TopologyContainer` with edges only | `BarycentricMapperEdgeSetTopology` | No — 1D |
| `MeshTopology` (fallback) | `BarycentricMapperMeshTopology` | **Conditional** |

**Critical finding on `MeshTopology`:** `MeshTopology.hasVolume()` is defined in `/home/sizhe/workspace/sofa/src/Sofa/Component/Topology/Container/Constant/src/sofa/component/topology/container/constant/MeshTopology.h` as `(getNbTetrahedra() + getNbHexahedra()) > 0`. When loaded from an OBJ file via `MeshOBJLoader`, `MeshTopology` contains only triangles — `hasVolume()` is false, and `BarycentricMapperMeshTopology::init()` falls into the 2D triangle branch. **The rule must not accept `MeshTopology` unconditionally.** It is safe only when the parent's linked loader has a volumetric file extension (`.msh`, `.vtk`, `.vtu`). Recommended: check the loader `filename` extension; if `.obj`/`.stl`/`.ply`, fire `warning`; if volumetric extension, suppress; if unknown, fire `info`.

**No missing valid-volumetric topology classes** — the rule's listed set covers all sources from the C++ switch.

## 3. Completeness of the Shell-FEM Exemption — Concrete Gap Found

**Current exemption: `TriangularFEMForceField`, `QuadBendingFEMForceField`**

Both verified registered (SOFA_CLASS macro + extern template in `Sofa.Component.SolidMechanics.FEM.Elastic`).

**Missing exemption classes (all verified registered):**

| Class | Evidence |
|---|---|
| `TriangleFEMForceField` | `/home/sizhe/workspace/sofa/src/examples/Tutorials/ForceFields/TutorialForceFieldLiverTriangleFEM.scn` uses it with `MeshTopology` + `BarycentricMapping` — official SOFA tutorial, legitimate shell FEM, **would produce false positive under current rule** |
| `TriangularFEMForceFieldOptim` | Verified registered; used in `TriangleFEMForceField_compare.scn` with triangle topology |
| `TriangularAnisotropicFEMForceField` | Subclass of `TriangularFEMForceField`; inherits surface-topology requirement |
| `BeamFEMForceField` | Uses edge-only `MeshTopology`; however in corpus (`BarycentricMappingTrussBeam.scn`) the BarycentricMapping maps FROM the volumetric Truss TO the Beam — the Beam is the child, not the parent. Rule does not fire. No exemption needed. |
| `TriangularBendingFEMForceField` (Shell plugin) | Present in corpus (`stenosis.scn`) but BarycentricMapping parents in that scene are volumetric anyway. Add as precaution. |

**Cosserat plugin:** `Actuator.py` uses `BarycentricMapping` in child nodes with edge/point topologies, but the BarycentricMapping parent (the `finger` node) is volumetric. Rule would not fire. No exemption needed.

**Recommended final exemption set:**
```python
SHELL_FEM_EXEMPTIONS = {
    "TriangularFEMForceField",           # current spec — correct
    "TriangleFEMForceField",             # MUST ADD — false positive on SOFA tutorial scene
    "TriangularFEMForceFieldOptim",      # MUST ADD — registered, triangle topology
    "TriangularAnisotropicFEMForceField",# ADD — subclass of TriangularFEMForceField
    "QuadBendingFEMForceField",          # current spec — correct
    "TriangularBendingFEMForceField",    # ADD (Shell plugin) — defensive
}
```

## 4. Edge Cases

| Case | Handled? |
|---|---|
| **Rigid3d parent (no topology)** — `BarycentricMapping<Vec3,Rigid3d>` requires `BarycentricMapperTetrahedronSetTopologyRigid`; without volumetric topology, `d_mapper = nullptr`, component enters Invalid state | Rule fires correctly — no exemption needed |
| **Point-set-only parent** — `populateTopologies()` emits `msg_error("No input topology found")` | Rule fires correctly |
| **MeshTopology with both triangles AND tetrahedra** — `BarycentricMapperMeshTopology::init()` branches on `!tetras.empty()` first, takes volumetric path | Rule suppresses correctly if loader-extension check is implemented |
| **2D `RegularGridTopology`/`SparseGridTopology`** — `hasVolume() == false`, mapper falls to `BarycentricMapperMeshTopology`, triangle path | **False negative** — rule does not fire, but interpolation is incorrect. Static check cannot determine grid dimensions from class name alone without reading `nx/ny/nz`. Recommend downgrading `RegularGridTopology`/`SparseGridTopology` acceptance to `info` severity. |
| **Cross-ancestry BarycentricMapping** (`input="@../../other/MO"`) — `getContext()->get(topology)` walks ancestor chain; rule's "check parent node" may inspect wrong node | **Known limitation** — rare in corpus, acceptable to defer to v2.2 |

## 5. Sample Scenes

**Should trigger (real bug patterns):**
- Any beginner scene loading `MeshOBJLoader` → `MeshTopology` (surface triangles) in parent, then `BarycentricMapping` in child without shell FEM — direct reproduction of Agent 6 F6
- A scene with `TriangleSetTopologyContainer` as the only parent topology, no FEM exemption class present

**Should NOT trigger (legitimate patterns — verified from corpus):**

| Scene | Path | Reason |
|---|---|---|
| `skybox.scn` | `/home/sizhe/workspace/sofa/src/examples/Demos/skybox.scn` | `TriangularFEMForceField` — current exemption covers it |
| `TutorialForceFieldLiverTriangleFEM.scn` | `/home/sizhe/workspace/sofa/src/examples/Tutorials/ForceFields/TutorialForceFieldLiverTriangleFEM.scn` | `TriangleFEMForceField` — **false positive without the fix** |
| `BarycentricMapping.scn` (TorusFEM) | `/home/sizhe/workspace/sofa/src/examples/Component/Mapping/Linear/BarycentricMapping.scn` | `MeshTopology` from `.msh` (volumetric) + `TetrahedronFEMForceField` |
| `BarycentricMapping.scn` (TorusFFD) | same | `RegularGridTopology` 3D + spring FF |
| `BarycentricMappingTrussBeam.scn` | `/home/sizhe/workspace/sofa/src/examples/Component/Mapping/Linear/BarycentricMappingTrussBeam.scn` | Beam is child (not parent) of BarycentricMapping; parent is volumetric Truss |

## 6. Summary of Required Changes

1. **Add `TriangleFEMForceField`, `TriangularFEMForceFieldOptim`, `TriangularAnisotropicFEMForceField` to the exemption list.** Without this, the official SOFA tutorial `TutorialForceFieldLiverTriangleFEM.scn` produces a false positive. Blocking correctness issue.
2. **Do not accept `MeshTopology` as unconditionally safe.** Check the linked loader file extension: `.obj`/`.stl`/`.ply` → fire `warning`; volumetric extensions (`.msh`, `.vtk`, `.vtu`) → suppress; unknown → fire `info`.
3. **Document that `RegularGridTopology`/`SparseGridTopology` 2D cases are not caught** — false negative, defer to v2.2.
4. **Document cross-ancestry scope limitation** — defer to v2.2.
