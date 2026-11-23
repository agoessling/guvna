# CPU MPI scaling on kratos

The released Palace v0.19.0 coaxial example ran fastest with four MPI ranks on the four performance
cores tested. Its median wall time was 4.515 s, compared with 6.045 s using four OpenMP threads
and 15.734 s using a single thread. Four ranks also more than doubled peak host memory relative to
four threads.

| MPI ranks | Threads per rank | Three wall times (s) | Median (s) | Peak host MiB¹ |
| ---: | ---: | --- | ---: | ---: |
| 1 | 1 | 15.760 / 15.722 / 15.734 | 15.734 | 194 |
| 2 | 1 | 8.497 / 8.486 / 8.486 | 8.486 | 275 |
| 4 | 1 | 4.511 / 4.526 / 4.515 | 4.515 | 441 |
| 1 | 4 | 6.033 / 6.045 / 6.092 | 6.045 | 203 |
| 2 | 2 | 5.701 / 5.752 / 5.755 | 5.752 | 277 |

¹ Largest Palace-reported peak node memory across the three trials, rounded to the nearest MiB.

Trials ran on November 22, 2026 with the same released solver and MPICH 4.3.2, order-3 coaxial
mesh (256 elements, 25,680 unknowns), input deck, six frequency/excitation solves, and field output.
Every trial checked the actual MPI size and OpenMP threads per rank in Palace metadata. GMRES
converged in 10, 11, 12, 11, 11, and 12 iterations in every run. The maximum absolute complex
S-parameter difference from the upstream reference across all runs was 7.44e-13 or less.

The solver group inherited CPU affinity 0,2,4,6 on the i5-13600K. The Linux scheduler placed the
ranks and threads within that mask. Each iteration changed the order of configurations, and trials
ran sequentially. Wall time spans process launch, mesh partitioning, solves, and field export.
Input staging, validation, and Bazel build time are outside the timer.

To reproduce one configuration, choose a new output directory for each trial. CPU IDs below refer
to this host.

```sh
out="$HOME/.local/share/guvna/benchmarks/mpi-repeat/coaxial-4r-1t"
bazel run --run_under='taskset -c 0,2,4,6' //examples:benchmark_prebuilt -- \
    coaxial --ranks 4 --threads 1 --output "$out"
```

The original decks, solver logs, CSVs, field output, and summaries are on kratos under
`~/.local/share/guvna/benchmarks/2026-11-22/mpi/coaxial-<ranks>r-<threads>t-<trial>/`.

## Two MPI ranks on the same RTX 4070 Ti

On the same coaxial input the pinned CUDA image ran six converged GMRES solves in 66 total
iterations with either one or two ranks. The launcher uses the image's Open MPI 5.0.10 for
multi-rank runs. Both ranks shared GPU 0 and the same pair of host performance cores (8,10).
Palace reported GPU-aware MPI and the requested rank count.

| GPU ranks | Wall times (s) | Maximum peak host MiB |
| ---: | --- | ---: |
| 1 | 7.88 / 7.83 | 909 |
| 2 | 13.97 / 13.51 | 1,698 |

These are process wall times including MPI startup and field output, with a warm kernel cache.
The largest absolute complex S difference between the rank counts was 2.05e-11. Use one GPU rank
for this small coax model. Timings with more ranks on a single GPU measure partitioning overhead
and contention as well as any parallel host-side work.

```sh
bazel run --run_under='taskset -c 8,10' //examples:benchmark_prebuilt -- \
    coaxial --device GPU --ranks 2 --output /tmp/guvna-coax-gpu-2r
```

The logs, output CSVs and individual wall times are under
`~/.local/share/guvna/benchmarks/2026-11-22/gpu-mpi/` on kratos.
