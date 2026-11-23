# Palace example results on kratos

Measured November 22, 2026 on Ubuntu 26.04, Intel Core i5-13600K (6 performance cores and
8 efficiency cores), 31 GiB system RAM, and a GeForce RTX 4070 Ti with 12 GiB VRAM. The NVIDIA
driver was 595.99.02. These examples exercise the solver before designing the GuVNA coupon.

See [CPU and GPU MPI scaling](../docs/mpi.md) for the rank-count study and the
[four-port CPW benchmark](../docs/application-benchmark.md) for the larger driven RF workload.
The [transmon benchmark](../docs/transmon-benchmark.md) follows a third-order eigenmode solve
through two rounds of adaptive mesh refinement.

The [example guide](README.md) lists the source-built CPU and GPU commands. The historical
benchmarks use `//examples:benchmark_prebuilt`.

## Source build versus prebuilt

The comparison on kratos used CPUs 0, 2, 4, and 6 and ran one solver at a time. Each build got
one warm-up followed by three timed runs per case and device. Build order alternated by trial.
Timing includes solver startup and the upstream deck's requested output. The four-port CPW case
uses STRUMPACK and checks two complex S-matrix columns at each of four frequencies. Spheres
uses BoomerAMG. Coaxial uses the upstream deck's default linear solver.

Median elapsed seconds on the same inputs and hardware are below. CPU CPW used four MPI ranks
with one thread each. CPU spheres and coaxial used one rank with four threads. All GPU runs used
one rank, one thread, and the MAGMA backend. All 36 timed runs passed their regression checks.

| Case | CPU prebuilt | CPU source | GPU prebuilt | GPU source |
| --- | ---: | ---: | ---: | ---: |
| Four-port CPW | 29.74 | 32.53 | 14.13 | 17.98 |
| Spheres | 7.51 | 8.11 | 9.62 | 22.28 |
| Coaxial | 6.06 | 6.72 | 7.90 | 9.25 |

Raw decks, solver logs, and per-run summaries are on kratos under
`~/.local/state/guvna/benchmarks/source-comparison-7JBLqH/`.

The CPU comparison uses the same Palace v0.19.0 release. On this host the PyPI wheel loads
AVX2/FMA-capable x86-64-v3 variants of Palace, MFEM, HYPRE, and libCEED built with GCC 14.2.1.
The GuVNA recipe uses GCC 13.2.0 in Release mode with no explicit CPU architecture flag for
Palace. The wheel uses MPICH 4.3.2 and OpenBLAS 0.3.34. GuVNA uses Open MPI 4.1.6 and
OpenBLAS 0.3.26. [Wheel tuning recipe][wheel-hwcaps]

The prebuilt GPU image runs a later Palace commit, `be4b5d36f`, built using GCC 15 and CUDA
13.4.2 with OpenMP disabled. GuVNA builds v0.19.0 with GCC 13, CUDA 12.9, and OpenMP enabled.
Both include native kernels for the RTX 4070 Ti's `sm_89`. The image also targets other GPUs.
The CPW logs show that GuVNA used Umpire host allocation and the image used standard host
allocation. The later revision also shares a device-memory pool between MFEM and HYPRE. The
median CPW operator-construction timers were 2.76 s for GuVNA and 0.63 s for the image. Revision,
allocator, compiler, and libraries changed together, so the timing cannot isolate a single cause.
[Image build recipe][gpu-spack] · [Upstream memory configuration][gpu-alloc]

To isolate host allocation, four extra CPW runs used the same prebuilt GPU binary. In run order,
Umpire, standard, standard, and Umpire took 15.14, 14.13, 14.13, and 15.12 s. Logs confirmed
that device allocation stayed on Umpire. Switching host allocation to Umpire added about 1.00 s
overall, including 0.72 s in operator construction. All four runs had identical Krylov iteration
counts and maximum complex S-parameter error. The full gap between the two builds was 3.85 s.

[wheel-hwcaps]:
  https://github.com/benvial/palace-solver/blob/v0.19.0/wheelbuild/hwcaps.py
[gpu-spack]:
https://github.com/awslabs/palace/blob/be4b5d3/.github/actions/build-container/spack_env/spack.yaml
[gpu-alloc]:
  https://github.com/awslabs/palace/blob/be4b5d36f/palace/utils/device.cpp#L44-L76

## Released CPU solver

Palace v0.19.0 ran with one MPI rank and one OpenBLAS thread. Each case was run three times
per OpenMP setting, with CPU affinity 0,2,4,6 (four distinct performance cores). Initial GPU setup
and pilot runs overlapped some release CPU trials. Timing covers process startup, solve, and field
export, after Bazel build and input preparation. The table gives individual wall times and the
largest Palace-reported peak host memory across the three trials.

| Case | Threads | Wall time (s), runs 1 / 2 / 3 | Median (s) | Peak host MiB |
| --- | ---: | --- | ---: | ---: |
| Spheres | 1 | 13.77 / 13.73 / 13.97 | 13.77 | 791 |
| Spheres | 4 | 9.03 / 7.52 / 8.53 | 8.53 | 796 |
| Coaxial | 1 | 15.71 / 15.78 / 15.82 | 15.78 | 195 |
| Coaxial | 4 | 6.05 / 6.12 / 6.08 | 6.08 | 204 |

For the spheres, all runs converged for both terminal excitations. The maximum relative difference
from the analytic capacitance was 3.53%. For the coax, all six frequency/excitation combinations
converged in 10–12 GMRES iterations per run. The largest absolute complex S difference from the
upstream regression across the CPU runs was below 1e-12.

## CPU and GPU using the same binary

For the device comparison, both runs use the same checksum-pinned upstream CUDA image, Palace
`v0.19.0-541-gbe4b5d36f`, one MPI rank, and a warmed CUDA kernel cache. This image was built
without OpenMP. On the stock examples, the resolved input decks differ only in `Solver.Device`.
Each trial includes the field exports. Repetitions ran serially after the release CPU timings.

| Case | Image device | Wall time (s), runs 1 / 2 / 3 | Median (s) |
| --- | --- | --- | ---: |
| Spheres | CPU | 9.86 / 9.82 / 9.87 | 9.86 |
| Spheres | RTX 4070 Ti | 9.64 / 9.67 / 9.63 | 9.64 |
| Coaxial | CPU | 7.52 / 7.55 / 7.52 | 7.52 |
| Coaxial | RTX 4070 Ti | 7.90 / 7.90 / 7.95 | 7.90 |

Among these one-rank configurations, the four-thread release CPU solver was fastest on both cases.
For the coax, four release CPU ranks reduced wall time further. [CPU MPI scaling](../docs/mpi.md)
The same-image CPU and GPU solutions agreed to within 2e-13 absolute complex S on the first coax
trial. The development image differed from the release reference by 1.11e-4, within the 5e-4
regression tolerance. The same-image comparison isolates the device change.

On spheres trial 3 the preconditioner took 2.08 s on CPU and 0.06 s on GPU. ParaView output took
0.56 s on CPU and 2.62 s on GPU. Whether we save full fields matters to end-to-end timing.

## Larger mesh with scalar output

We refined the spheres mesh uniformly once and disabled field snapshots for both devices. The
resulting problem has 114,896 tetrahedra and 524,261 electrostatic unknowns. The default CUDA
backend (`/gpu/cuda/magma`) aborted after the first terminal solve with a libCEED vector read-lock
error. The failed run is retained in `cuda-image/refined-GPU-1/solver.log`. A subsequent
[kernel trace and controlled experiment](../docs/magma.md) identified the shared-memory limit.

With `--backend /gpu/cuda/shared`, both terminals converged in 8 iterations each. The CPU and GPU
results from the same image agreed within 8.1e-13 relative for every capacitance matrix entry.
The largest relative difference from the unbounded-domain analytic result was 3.55%.

| Configuration | Wall time (s), individual trials | Max peak host MiB |
| --- | ---: | ---: |
| Released CPU, 4 threads | 55.01 | 4,722 |
| CUDA image running on CPU, 1 rank | 68.20 | 5,057 |
| CUDA image running on RTX 4070 Ti, shared backend | 36.94 / 32.36 | 2,833 |

The second GPU run reused the compiled CUDA kernels. Its largest sampled solver GPU memory usage
was 2,938 MiB across 31 samples. The two GPU trials were 1.49–1.70× faster than the four-thread
release CPU trial and 1.85–2.11× faster than the CPU trial from the same image. On the refined
mesh, the preconditioner alone dropped from 22.78 s on image CPU to 1.16 s on the first successful
GPU run. Both mesh size and output settings differ from the stock example, so locating a crossover
point would require further trials. See the [GPU commands](../docs/palace-gpu.md) to reproduce it.

## Coaxial phase convergence

For an independent physical check, we ran the v0.19.0 mixed-port coax at 10 GHz. The analytic TEM
phase delay of the 40 mm dielectric-filled line is approximately 192.43 ps, using relative
permittivity 2.08. That predicts an S21 phase of −692.75°, or +27.25° after phase wrapping.
The example intentionally uses a 100 Ω lumped port against roughly 50 Ω coax, which explains the
approximately −9.54 dB input reflection.

| Finite-element order | Unknowns | S11 (dB) | S21 phase (degrees) |
| --- | ---: | ---: | ---: |
| 1 | 1,328 | −8.0824 | 42.5209 |
| 2 | 8,352 | −9.3861 | 27.4098 |
| 3 | 25,680 | −9.5416 | 27.2563 |

All three linear systems met the solver's stopping criterion for each excitation. Raising the order
on the same 256-element mesh reduced the phase error from about 15.27° to less than 0.01°.
This check covers the two-port example at one frequency. A coupler will need its own convergence
study at the isolated port.

To reproduce, start from the normalized JSON deck and mesh written by the coaxial benchmark. Make a
separate copy for each order. Set `Solver.Order` to 1, 2, or 3, `Solver.Driven.Samples` to
`[{"Type": "Point", "Freq": [10.0]}]`, and `Solver.Driven.Save` to `[]`. Run the CPU Palace
launcher in each copy with one thread and read the 10 GHz row of `port-S.csv`.

## Run records on kratos

The release CPU trials are under `~/.local/state/guvna/benchmarks/2026-11-22/v019-cpu/`.
The image trials and the polynomial-order study are under
`~/.local/share/guvna/benchmarks/2026-11-22/` in `cuda-image/` and `coax-order/`.

To inspect the release coax fields interactively, open
`postpro/paraview/driven/excitation_1/excitation_1.pvd` inside a coaxial trial. Its companion
files contain the 10 GHz volume data. The corresponding boundary collection is under
`postpro/paraview/driven_boundary/`. Copy the whole `paraview/` tree when viewing locally.
