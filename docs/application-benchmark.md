# Four-port driven RF benchmark

On kratos, Palace completed the coupled-line frequency sweep in **14.04 s** on one RTX 4070 Ti,
**18.30 s** on four CPU ranks using the same binary, and **29.69 s** on four CPU ranks using
the packaged release. These final trials ran back-to-back with the same four performance cores
available to each process group. The GPU gave a 1.30× speedup over the four-rank image CPU run
and a 2.11× speedup over the four-rank release CPU run.

| Final isolated trial | Eight driven solves | Peak host MiB |
| --- | ---: | ---: |
| v0.19.0 release, four MPI ranks | 29.69 s | 1,072 |
| CUDA image on CPU, four MPI ranks | 18.30 s | 2,982 |
| CUDA image on GPU, one rank, MAGMA | 14.04 s | 1,004 |

All trials converged and agreed with the published complex S-matrix columns. Across the final
three, the worst absolute error was below 1e-7 and the worst relative error was below 0.003%.
Each final trial used CPUs 0, 2, 4, and 6, with a warm CUDA kernel cache for the GPU run.

## Coupled-line model

This benchmark uses the Palace v0.19.0 example of two parallel, 4 mm coplanar waveguides on a
500 μm sapphire substrate. Each line has a 30 μm signal trace and 18 μm slots. A 200 μm ground
strip separates the lines. All four lumped ports use 56.02 Ω. Ports 1 and 2 terminate opposite
ends of one line. Ports 3 and 4 are at the near and far ends of the adjacent line for excitation
at port 1. This is a crosstalk workload with port observables relevant to GuVNA.
[Palace CPW example](https://awslabs.github.io/palace/stable/examples/cpw/)

The loaded mesh has 14,628 tetrahedra and 94,618 second-order electric-field unknowns. A direct
sweep at 2, 8, 14, and 20 GHz solves for excitations at ports 1 and 2, yielding two columns of
the scattering matrix at each frequency. The harness checks all eight GMRES convergence messages
and compares all 32 complex coefficients with the corresponding rows of the upstream regression.
The absolute and relative complex tolerances are 0.0005 and 1%, respectively. The relative check
also exercises weak paths, including a far-end response of −70.25 dB at 14 GHz.

Input changes relative to the published uniform-sweep example are the frequency subset, disabled
3D field output, and explicit STRUMPACK as the coarse solver across builds. Other postprocessing
is retained. All trials use the same mesh, source excitations, port definitions, and requested
linear tolerance of 1e-8. The shell commands below include host CPU affinity for this machine.

## Run a trial

```sh
runs="$HOME/.local/state/guvna/runs"
taskset -c 0,2,4,6 bazel run //examples:benchmark_prebuilt -- cpw \
  --ranks 4 --threads 1 --output "$runs/cpw-release-4x1"
taskset -c 0,2,4,6 bazel run //examples:benchmark_prebuilt -- cpw \
  --device GPU --backend /gpu/cuda/magma --output "$runs/cpw-magma"
```

To compare CUDA backends, select `/gpu/cuda/shared` for the second trial. To share the GPU across
two processes, pass `--ranks 2`. To run the CUDA-capable binary on the CPU, use
`--device CPU --palace tools/palace_gpu`. Choose a new output directory for each trial.

For released and development binaries, dependencies, affinity, mesh, and output all affect
elapsed time. The released CPU solver uses Palace v0.19.0. The CUDA image supplies Palace
`v0.19.0-541-gbe4b5d36f` built without OpenMP. Image CPU and GPU runs use one host thread per
rank. All timings cover process launch through exit with outputs written to disk. Bazel fetch and
input preparation are outside the timed interval.

## Thread, process, and backend comparisons

Measured November 22, 2026 on an Intel i5-13600K and RTX 4070 Ti. The release CPU cases used
logical CPUs 0, 2, 4, and 6 (four different performance cores). The GPU host processes used CPUs
8 and 10. The single-rank image CPU control used CPU 0 and the four-rank control used 0, 2,
4, and 6. Each GPU run used the same card and the unmodified image with its persistent CUDA kernel
cache. Some CPU and GPU cases ran concurrently on separate CPU masks and shared memory bandwidth.
The table reports individual samples.

| Build and device | MPI × threads | Wall time (s), in order | Peak host MiB¹ |
| --- | ---: | --- | ---: |
| Release CPU | 1 × 4 | 45.29 | 842 |
| Release CPU | 2 × 2 | 41.38 | 892 |
| Release CPU | 4 × 1 | 29.71 | 1,075 |
| Image CPU | 1 × 1 | 62.62 | 1,190 |
| Image CPU | 4 × 1 | 18.44 | 2,982 |
| Image GPU, MAGMA | 1 × 1 | 19.75, 14.61 | 1,038 |
| Image GPU, shared | 1 × 1 | 22.92, 16.53 | 1,057 |
| Image GPU, MAGMA | 2 × 1 | 25.15, 22.31 | 1,818 |
| Image GPU, shared | 2 × 1 | 27.48 | 1,827 |

¹ Largest Palace-reported peak host memory across the listed runs. GPU allocations are additional.

At one rank on the same image, the GPU MAGMA repeat took 14.61 s versus 62.62 s on CPU (4.29×
speedup). Palace's preconditioner timer fell from 35.15 to 0.38 s. The coarse solve
increased from 1.90 to 3.29 s and postprocessing from 0.34 to 3.76 s. STRUMPACK reported that
SLATE was unavailable for full GPU support. End-to-end timing includes the work performed on the
host and data movement.

At 8 GHz on the release CPU, the primary-line transmission was −0.529 dB, near-end pickup was
−45.245 dB, and far-end pickup was −55.178 dB. Both GPU backends reproduced the small signals
within the regression tolerances. Between the two single-rank GPU backend repeats, the maximum
absolute complex S difference across all paths and frequencies was 3.4e-13. GuVNA's eventual
20 dB coupling design needs its own geometry and convergence study.

Per-trial inputs, mesh, complete logs, `summary.json`, and magnitude/phase CSVs are in
`~/.local/state/guvna/benchmarks/2026-11-22/cpw/` on kratos. The `one-point-pilot` directory
contains an untimed configuration check and is excluded from the table.
