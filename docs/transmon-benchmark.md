# Transmon adaptive eigenmode benchmark on kratos

The pinned Palace v0.19.0 transmon example computes the two eigenmodes nearest 4 GHz for a
superconducting qubit coupled to a readout resonator and feedline. The mesh starts with 58,961
tetrahedra and 1,093,338 third-order electric-field unknowns. The stock input requests two rounds
of adaptive mesh refinement (AMR) and saves the fields for both modes on each mesh.
[Palace transmon example](https://awslabs.github.io/palace/stable/examples/transmon/)

## Results on November 22, 2026

The GPU completed the first two meshes. The CPU completed the first. The following are
Palace's cumulative timings and peak host memory for completed stages. Both runs used separate
performance cores concurrently and shared host memory bandwidth.

| Configuration and mesh | Field unknowns | Total so far | Host peak | Modes (GHz) |
| --- | ---: | ---: | ---: | --- |
| Release CPU, initial | 1,093,338 | 16.29 min | 6.85 GiB | 4.290769, 5.701514 |
| CUDA shared, initial | 1,093,338 | 4.88 min | 2.31 GiB | 4.290769, 5.701514 |
| CUDA shared, first refinement | 1,312,842 | 17.89 min | 3.22 GiB | 4.358522, 5.704946 |

At 2,711,337 unknowns the stock GPU process segfaulted in libCEED during setup after 18.21 min.
The last solver VRAM sample was 11,442 MiB. On the reconstructed final mesh a fresh process with
a 24-vector GMRES basis and seven-vector eigenbasis explicitly failed a 20.7 MiB CUDA allocation.
The original null dereference had no allocation backtrace. A second retry used a real
preconditioning matrix and 14-vector GMRES basis; it converged one of the two eigenmodes before
the requested stop. The CPU trial was stopped on its middle mesh after 37.67 min. No complete
three-mesh timing, final two-mode validation, or full-run speedup was obtained.

Inputs, stage outputs, field files, logs, and retry settings are under
`~/.local/state/guvna/benchmarks/2026-11-22/transmon/` on kratos.

## Reproduce a trial

Run these commands from the repository root on kratos with fresh output directories. The GPU
trial uses the shared CUDA backend, which previously completed our cubic-element spheres test.
The CPU command uses four MPI ranks, each with one OpenMP thread on a separate performance core.

```sh
runs="$HOME/.local/state/guvna/runs"
taskset -c 0,2 bazel run //examples:benchmark_prebuilt -- transmon \
  --device GPU --backend /gpu/cuda/shared --output "$runs/transmon-gpu"
taskset -c 4,6,8,10 bazel run //examples:benchmark_prebuilt -- transmon \
  --ranks 4 --threads 1 --output "$runs/transmon-cpu"
```

The CPU release uses SuperLU for the coarse solve. The CUDA image uses STRUMPACK. Both use
SLEPc for the eigenproblem and retain the upstream solver tolerances, materials, boundary
conditions and field exports. The AMR error estimator changed between the builds. The benchmark
checks both modes and the error indicator on each mesh against the matching upstream version.

## Estimating GPU capacity

We sampled the stock solver process's GPU memory every 250 ms. The first two mesh stages,
including postprocessing, reached 6,632 MiB at 1,093,338 unknowns and 9,560 MiB at 1,312,842
unknowns. Scaling each observed peak in proportion to 2,711,337 unknowns gives a rough
16–19 GiB budget for the final stage. Only 11,504 MiB was available before launch. The final
stock stage failed, so its actual full working set is unknown.

At 2,711,337 unknowns, each packed double-complex field vector alone costs 41.4 MiB. The geometry,
preconditioner, Krylov and eigenvector bases, and export buffers also contribute. Calibration
should use the same analysis type, element order, rank count, backend, solver settings, and
output settings as the intended job. For GuVNA the driven CPW case is the relevant baseline.
Palace's `--dry-run` checks the configuration file. Pilot runs supply memory measurements.

## Restarting an interrupted mesh level

For long AMR runs, set `Model.Refinement.SaveAdaptMesh` and `SaveAdaptIterations` to true.
Palace writes the newly adapted mesh before the next solve. After a crash, set `Model.Mesh` to
that mesh, use a fresh output directory, and set `Model.Refinement.MaxIts` to the number of
refinements still needed (zero when restarting on the final mesh). That level's eigensolve starts
over. The stock input enabled iteration archives and disabled `SaveAdaptMesh`, so recovering its
final mesh required replaying the saved refinement indicators.
[Palace AMR output guide](https://awslabs.github.io/palace/stable/guide/postprocessing/)

In three local write tests, serial MFEM took 0.43–0.44 s to write the 21.46 MiB final mesh.
Compressing that file with gzip level 6 and flushing the 6.75 MiB result took another
1.14–1.15 s. The test used one efficiency core and local NVMe. Palace additionally gathers
the mesh to rank 0 and computes topology counts. Full field exports on the initial GPU mesh
used 467 MiB and took 17.0 s (5.8% of that stage).

## Why a GPU solve also used one full CPU core

We sampled the GPU rank's main host thread in a separate 80 s initial-mesh pilot, pinned to
CPUs 0 and 2. During 34 s of GMRES the thread consumed 99.92% of one core. Across 35 device
polls, GPU utilization had a median of 100% and a mean of 94.2%.

Of 136 stacks sampled every 250 ms of main-thread CPU time, 123 were inside the CUDA driver.
75 went through device-to-host copies, including 46 returning cuBLAS dot-product results and
29 on the MFEM/STRUMPACK path. Another 42 went through kernel launch. In 66 samples the thread
was yielding inside the driver or executing its polling loop. Those 66 overlap the API counts.
Nine samples landed in OpenBLAS. The CPU can consume a full core checking for completion while
the GPU executes kernels. These samples describe the host thread and do not measure GPU arithmetic
throughput or PCIe bandwidth.
