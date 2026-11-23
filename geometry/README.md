# Uniform coupled microstrip coupon

The trial section runs 8 mm along x between two lumped-port reference planes. Two straight
conductors sit at z = 0.508 mm on a lossless substrate with relative permittivity 3.48.
Both conductors are 1.1 mm wide and the edge-to-edge gap is 0.22 mm. These dimensions are
provisional. An isolated microstrip estimate with width/height = 2.165 and effective
permittivity 2.725 gives 51.7 ohms before including the nearby trace and enclosure. The coupled
even and odd modes have different impedances. The section extends all the way to the port planes.

The lower and upper metal walls are the ground plane at z = 0 and a flat lid 2 mm above the
strips. Each lateral metal wall is 2 mm away from the adjacent strip edge. The two x end faces
are magnetic walls except for the four port sheets. This termination represents the simulation's
end treatment. A coupon with physical launches and wall openings will have different fields.

| Physical tag | Location | Role |
| --- | --- | --- |
| 1, 2 | Below and above traces | Substrate and air volumes |
| 10 | Ground, lid, both y walls | Enclosure PEC |
| 11, 12 | Interface at z = 0.508 mm | Zero-thickness main and pickup PEC strips |
| 13 | Both x ends except the port sheets | Natural magnetic boundary |
| 21, 22 | Negative-y strip at x = 0 and 8 mm | Port 1 input and port 2 through |
| 23, 24 | Positive-y strip at x = 0 and 8 mm | Port 3 near pickup and port 4 far pickup |

Each rectangular port spans one trace width and connects vertically to ground. The integration
direction is +z at all four ports. Port 3 is the candidate forward-coupled port for the
backward-wave coupled pair. Preserve the signed coupling-to-isolation ratio to test that choice.
The model omits feed-line transitions, finite copper thickness, surface roughness and losses.

## Mesh

From the checkout, generate either resolution with Bazel. Each output directory receives an
ASCII Gmsh 2.2 model.msh and geometry.json with the dimensions, port map, physical groups and
mesh counts. The geometry uses the Gmsh Python API. Bazel fetches Gmsh 4.15.2, CPython 3.13
and shared libraries pinned by SHA-256 for Linux x86-64. A display and a system Gmsh install
are unnecessary. The geometry and mesh generation run on one CPU thread.

```sh
bazel run //geometry:generate -- --output /tmp/guvna-mesh0
bazel run //geometry:generate -- --output /tmp/guvna-mesh1 --refinement 1
```

The model extrudes one conforming cross section of quadrilaterals. Internal PEC trace sheets
share nodes with the air and substrate hexes. Nonuniform spacing concentrates cells near the
trace plane and the outer trace edges. The refinement increases resolution in all three axes.

| Refinement | x intervals | Across gap | Through substrate | Hexes | Quads per port |
| --- | --- | --- | --- | --- | --- |
| 0 | 12 | 2 | 3 | 1,920 | 12 |
| 1 | 20 | 4 | 5 | 8,840 | 35 |

The generator checks both material volumes, the area of every surface group, the reference
plane and extent of each port, consistency of boundary-to-volume adjacency, and positive
element orientation. All geometric elements are first order. The Palace deck independently
sets the finite-element approximation order.

Use `--length`, `--width`, `--gap`, `--substrate-height`, `--lid-clearance`, and
`--side-clearance` to override the dimensions in millimetres. Use `--relative-permittivity`
to change the substrate dielectric constant. Mesh interval counts stay fixed at each level as
dimensions change. Check convergence again when a sweep changes the dimensions substantially.

For a targeted mesh check, change one feature while holding the geometry and other counts fixed.

```sh
bazel run //geometry:generate -- --output /tmp/guvna-finer-gap --gap-cells 6
```

`--gap-cells`, `--strip-cells` and `--side-cells` set transverse counts through the coupling
gap, across each strip and between each outer edge and its side wall. `--length-cells` sets
the longitudinal count. `--substrate-cells` and `--air-cells` control the two vertical
intervals. Each accepts a positive integer and overrides the corresponding preset entry.
For Python callers, `MeshPolicy.preset(level)` supplies the same counts; use
`dataclasses.replace(policy, gap_cells=6)` to vary a feature. The output metadata records the
actual interval counts and any changes from the preset.

The geometry.json sidecar identifies the mesh with `mesh_file`. Its physical groups carry optional
display labels, colours and visibility defaults. Each mesh sizing rule records its axis, number of
intervals, and bounding boxes in millimetres. A viewer can display those annotations alongside the
boundary conditions and material parameters from the Palace deck.

`from geometry import CoupledMicrostrip, Dimensions, MeshPolicy, PortSheet` exposes the model
and mesh inputs without loading Gmsh. Each `PortSheet` defines an x-normal rectangular
terminal with a ground height and a +z integration direction. The model, Gmsh entity selector
and exported-mesh checks share the same terminal definitions.
