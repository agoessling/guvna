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
and MPI. See the [example guide](examples/README.md) for the available simulations. The first
planned GuVNA-specific simulation is a nominal 50 Ω PCB through-line.

For timings on kratos, start with the [source and prebuilt comparison](examples/PERFORMANCE.md).
The [four-port benchmark](docs/application-benchmark.md), [MPI measurements](docs/mpi.md), and
[MAGMA investigation](docs/magma.md) cover individual solver settings.
