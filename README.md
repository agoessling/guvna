# GuVNA

GuVNA is a hardware vector network analyzer project. The first design task is a wideband directional
coupler. The [design requirements](REQUIREMENTS.md) record the RF targets and what each simulation
needs to preserve for system-level analysis.

## Build and simulation

Bazel is the common build and test entry point for the monorepo. Python analysis tools and web apps
will consume the same simulation results, and future firmware and FPGA builds may share hardware
definitions. Bazel targets will make those dependencies explicit and give
contributors and coding agents the same commands to reproduce a result.

On Linux x86-64, running Palace or a benchmark builds the selected solver from pinned sources
on first use. The GPU target builds Palace v0.19.0 for the RTX 4070 Ti. Bazel reuses the build
when the inputs are unchanged.

```sh
bazel run //tools/palace -- --version
bazel run //tools/palace:palace_gpu -- --version
```

The benchmark targets build their respective solvers and check results against upstream values.
Use a fresh output directory for each run.

```sh
bazel run //examples:benchmark -- cpw --ranks 4 --output /tmp/guvna-cpw-cpu
bazel run //examples:benchmark_gpu -- cpw --output /tmp/guvna-cpw-gpu
```

The benchmark saves its input, log, numerical results, and validation summary in that directory.
The [source build guide](tools/palace/source/README.md) covers prerequisites, caches, offline use
and MPI. See the [example guide](examples/README.md) for the upstream simulations.

## Parametric geometry and meshing

The [Python geometry library](geometry/README.md) generates a boxed pair of coupled microstrips
with the Gmsh API. Dimensions are in millimetres. A sweep can vary coupling gap, section length,
or lid clearance and pass each candidate to the same four-port Palace workflow.

Keep mesh refinement rules separate from the physical dimensions. Attach local sizing rules to
features such as trace edges, coupling gaps, and ports so the refinement follows each geometry.
This lets us refine a fixed design and check whether its predicted directivity converges.

The [coupler run guide](coupler/README.md) covers running Palace on a coupon and accessing its
complex S-parameters and field outputs.

## Geometry and mesh inspector

Open a Palace input deck and its tagged Gmsh mesh with `--case`, or use `--run` for a generated
geometry or archived run directory. A run directory supplies its `palace.json`, or a
`geometry.json` and mesh for a geometry-only preview. The inspector reads the input mesh and
boundary assignments independently of the Palace executable. Supply each model explicitly, in
display order. One model opens directly. With several models, choose one from the toolbar.

```sh
bazel run //viewer:serve -- --case /path/to/model.json
bazel run //viewer:serve -- --run /path/to/first-run --run /path/to/second-run
```

To inspect a coupon before solving, generate its mesh and open the output directory.

```sh
run="$HOME/.local/state/guvna/coupler/trial01"
bazel run //geometry:generate -- --output "$run"
bazel run //viewer:serve -- --run "$run"
```

On the laptop, forward the port and open [the inspector](http://localhost:8765/). Replace
`kratos` with your simulation host if needed.

```sh
ssh -N -L 8765:127.0.0.1:8765 kratos
```

Pick a face or tree row to see its physical tag, material or Palace boundary assignments.
The eye controls visibility across both **Geometry** and **Gmsh mesh**. Press **Esc** to
clear the selection. Curved, higher-order elements are displayed using their corner nodes.

For a completed driven run with a Palace `port-S.csv`, the **Port response** dock plots the
output traces for one excitation. Click the plot or use its arrow keys to move between frequency
samples. Diamonds on the axis identify saved volume fields for that excitation. Selecting one
updates the 3D layers in place and opens a field cut if no layer is active. A sample without a
saved field still has port values in the table and clears the field overlay. Use the trace
checkboxes to show or hide curves and click a trace name to inspect its marker values. Click
**Port response** in the dock header to collapse the plot.

For a completed driven `--run`, **Field cut** overlays the electric field magnitude on the
current section. The toolbar lists the drives and frequencies with saved volume fields. Click
the legend to choose a 40 dB, 60 dB, or linear scale, set the reference in V/m, or restrict the
section to a material. The reference stays fixed when moving the cut or changing the sample.
**Fit to cut** sets it to the peak on the displayed section. The electric-field legend also offers
signed Ex, Ey, and Ez on cuts and material faces. Use the RF phase dial, enter degrees, or press
**Play** to see propagation. These views use a linear, zero-centered V/m scale. Fit uses the
selected component's peak amplitude across phase, so the colors remain comparable during playback.

Enable **Surface fields** to overlay sheet current on visible boundary groups or an explicitly
selected group. To color dielectric faces, enable **Surface electric field**, choose the source
material and select all its faces or a tagged boundary. The field comes from that material side.
With **All material faces** selected, moving the **Cut plane** also colors the newly exposed face
from the retained material's volume data. **Field cut** can extend that plot across other volumes,
including air. Both electric-field plots share a V/m scale. Sheet current has its own A/m legend.
**Geometry** shows visible group outlines over these colors. Switch to **Gmsh mesh** to see the
input mesh edges on the same surfaces and section.

A geometry generator can attach model properties, sizing boxes, or display labels using
`geometry.json`. Its `mesh_file` identifies the mesh relative to that file (default `model.msh`).
Annotations in `physical_groups` match on both `dimension` and `tag`. Sizing boxes use viewer
coordinates in millimetres. An ordinary Palace deck needs only its mesh and assignments to
populate the inspector.

Enable **Cut plane** in the toolbar. Choose the X, Y, or Z normal and enter a position in model
millimetres, or drag the blue arrow handle in the viewport. In a face-on view, drag upward
to increase the coordinate. **Keep side** reverses the cut. Switching between **Geometry** and
**Gmsh mesh** keeps the same plane. The mesh section shows where each cell meets it, including
between node layers.

Drag a model face, mesh face, or colored field slice to orbit around the point you grabbed.
Scroll to zoom at the pointer. Starting an orbit over empty space reuses the last point you zoomed
or orbited around. A crosshair briefly marks that point. Middle- or right-drag pans the view.
Double-click a surface to center it. Click a view-cube face for an axial view or press **F** with
the viewport focused to fit the model. The toolbar offers perspective and orthographic projection.

## Benchmark results

For timings on kratos, start with the [source and prebuilt comparison](examples/PERFORMANCE.md).
The [four-port benchmark](docs/application-benchmark.md), [MPI measurements](docs/mpi.md), and
[MAGMA investigation](docs/magma.md) cover individual solver settings.
