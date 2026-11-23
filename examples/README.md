# Palace example benchmarks

Run these upstream Palace v0.19.0 examples from the repository root. The harness uses host Python 3
and its standard library. Bazel builds the selected solver from pinned sources and supplies the
matching upstream decks, meshes, and reference CSVs. The CPU target requires only the CPU
toolchain. The first build takes longer than an individual solve.
[Source build guide](../tools/palace/source/README.md)

```sh
runs="$HOME/.local/state/guvna/runs"
bazel run //examples:benchmark -- spheres --output "$runs/spheres-1"
bazel run //examples:benchmark -- coaxial --output "$runs/coaxial-1"
bazel run //examples:benchmark -- cpw --ranks 4 --threads 1 --output "$runs/cpw-1"
```

Set `--ranks` to choose the MPI process count and `--threads` to choose OpenMP threads per process.
Both default to one. The launchers set OpenBLAS to one thread. Choose a fresh directory per trial.
Each run directory includes the input deck, mesh, solver output in `solver.log`, and a validated
`summary.json`.
Palace writes the resolved configuration, scalar results, timing counters, and any requested
ParaView data under `postpro/`. Wall time starts immediately before solver process launch and ends
when it exits. It includes writing the upstream example's field outputs. Build, input preparation,
bundle extraction, and numerical comparison happen outside that interval. The source-built targets
save their version probe in `solver-version.log`.

Use the GPU target to build the CUDA solver and run it on the RTX 4070 Ti. Select CPU on that
same target to measure how much the GPU changes runtime using the same binary.

```sh
bazel run //examples:benchmark_gpu -- spheres --output "$runs/spheres-gpu-1"
bazel run //examples:benchmark_gpu -- spheres --device CPU --output "$runs/spheres-control-1"
```

For an existing `//examples:benchmark -- … --device GPU` command, change the target to
`//examples:benchmark_gpu`. The GPU target accepts an explicit `--device GPU` as well.

Use `//examples:benchmark_installed` with `--palace` to time a separately installed solver. Give
the launcher path and the requested device. This target fetches the decks and references only.

```sh
prefix="$HOME/.local/opt/guvna/cpu"
bazel run //examples:benchmark_installed -- coaxial --palace "$prefix/bin/palace" \
  --device CPU --output "$runs/coaxial-installed"
```

The initial performance reports used the release CPU wheel and an upstream development CUDA image.
Their reproduction commands use `//examples:benchmark_prebuilt`. On that target, `--device CPU`
selects the wheel and `--device GPU` selects the historical image launcher. For a CPU control in
the same image, pass `--device CPU --palace tools/palace_gpu`. The image requires separate
provisioning. [Historical GPU runtime instructions](../docs/palace-gpu.md)

## What the checks measure

- **Spheres.** Two third-order electrostatic solves give the 2 × 2 Maxwell capacitance matrix.
  Both terminal solves must report PCG convergence. Each entry must agree with the upstream
  regression data to relative error ≤ 1e-5 and with the analytical two-sphere solution to ≤ 4%.
  The example uses a finite grounded outer boundary. The analytical solution assumes unbounded
  vacuum. [Palace spheres example](https://awslabs.github.io/palace/stable/examples/spheres/)
- **Coaxial.** A 100 Ω lumped port drives a roughly 50 Ω coaxial line terminated in a wave port,
  then the reverse excitation supplies the second matrix column. Both excitations must report GMRES
  convergence at each of 5, 10, and 15 GHz. Each complex S value must lie within 0.0005 absolute
  error of the upstream regression value. The comparison preserves phase across ±180° wraps.
  [Palace coaxial example](https://awslabs.github.io/palace/stable/examples/coaxial/)
- **Coupled CPW.** Two neighboring coplanar lines have four lumped ports. This benchmark excites
  ports 1 and 2 separately at 2, 8, 14, and 20 GHz. It compares all 32 complex coefficients,
  including weak crosstalk, against upstream reference data with absolute tolerance 5e-4 and
  relative tolerance 1%. See [the application benchmark](../docs/application-benchmark.md).
- **Transmon.** The third-order eigenmode case starts with about 1.09 million unknowns and takes
  two adaptive refinement steps. At each of the three mesh levels, the harness checks both complex
  frequencies, loaded Q values, and the electromagnetic error-indicator norm against the matching
  upstream revision, all within 1% relative error. It requires each eigenpair's backward error to
  be at most 1e-8, increasing mesh DOF, and a decreasing indicator norm. The upstream deck saves
  both mode fields. [Transmon example](https://awslabs.github.io/palace/stable/examples/transmon/)

The transmon reference CSV contains the two `eig.csv` mode rows and the `error-indicators.csv`
norm from each of `iteration1/`, `iteration2/`, and the final output directory, for the release
and the historical development image. The estimator changed after v0.19.0, so the harness selects
the reference values by solver revision. [Release data][transmon-rel] and [CUDA data][transmon-dev].

[transmon-rel]:
  https://github.com/awslabs/palace/tree/v0.19.0/test/data/regression/ref/transmon/transmon_amr
[transmon-dev]:
  https://github.com/awslabs/palace/tree/be4b5d36f/test/data/regression/ref/transmon/transmon_amr

```sh
bazel run //examples:benchmark_gpu -- transmon --backend /gpu/cuda/shared \
  --output "$runs/transmon-gpu"
```

To read back a complete trial, use the same device, backend, rank, and thread options and append
`--check-existing`. This prints the numerical validation, leaves the run directory untouched, and
reports process wall time as null because no new solve was timed.

The CPW case keeps the published mesh, finite-element order, and solver tolerance. It uses explicit
STRUMPACK coarse solves and omits field snapshots for the port sweep. The default spheres and coax
cases also keep the published field outputs. A mesh or order study addresses spatial discretization
error.

For a larger CPU/GPU comparison, add `--refine-spheres` to the spheres command. This splits each
tetrahedron into eight and sets the number of field snapshots to zero. The analytical capacitance
check still applies. The summary records the change relative to the published coarse-mesh values.
