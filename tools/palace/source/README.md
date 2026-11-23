# Building Palace from source

These targets build Palace v0.19.0, its numerical libraries, and its CPU or NVIDIA backend.
They use the upstream CMake superbuild and the same Ubuntu 24.04 x86-64 userspace, GCC 13,
OpenMPI, OpenMP and OpenBLAS. The GPU build adds CUDA 12.9 and MAGMA for compute capability 8.9
(the RTX 4070 Ti). Both include SLEPc, SuperLU_DIST and STRUMPACK.

Compared with the v0.19.0 CMake defaults, both builds enable OpenMP, STRUMPACK, and shared
libraries, and explicitly select OpenBLAS. STRUMPACK is the coarse solver in the four-port
benchmark. Both use the upstream Release optimization level with no additional Palace CPU
architecture flag. The GPU build enables CUDA, fixes the GPU architecture at `89`, and uses
the upstream GPU defaults for MAGMA (on) and GPU-aware MPI (off).

## Build and run

Use Linux x86-64 with Bazelisk (as `bazel`), Python 3.11+, Bubblewrap with working user
namespaces, GNU tar and dpkg-deb with zstd support. The NVIDIA driver and device nodes on the
host are used when running a CUDA simulation. Compilers, MPI, CUDA headers, nvcc, and math
libraries come from digest-verified inputs. No root access or system package installation is
required by the installer.

A solver invocation builds its bundle as a Bazel action. To compile ahead of time, use
`bazel build` with the same label. The CPU target only fetches inputs for the CPU build.

```sh
bazel run //tools/palace -- --version
bazel run //tools/palace:palace_gpu -- --version
```

From a case directory inside the checkout, pass the deck name and optional MPI rank count.
The launcher preserves the calling directory so Palace can open relative mesh and output paths.

```sh
OMP_NUM_THREADS=1 bazel run //tools/palace -- -np 4 config.json
bazel run //tools/palace:palace_gpu -- config.json
```

Set `Solver.Device` to `GPU` in the GPU deck. The shared CUDA backend can be selected with
`Solver.Backend` set to `/gpu/cuda/shared`. The launcher passes through local NVIDIA device
nodes and the matching host driver libraries from the Debian/Ubuntu x86-64 library directory.
OpenMPI can print an ignored `mca_mtl_psm` warning while probing for an InfiniPath adapter.
Local MPI ranks communicate over shared memory.
The benchmark harness checks the complex S-parameters in the four-port example.

```sh
runs="$HOME/.local/state/guvna/runs"
bazel run //examples:benchmark -- cpw --ranks 4 --output "$runs/source-cpu-cpw"
bazel run //examples:benchmark_gpu -- cpw --backend /gpu/cuda/shared --output "$runs/source-gpu-cpw"
```

## Cold and cached builds

Bazel schedules one local CMake build action per requested variant. Each action uses up to eight
parallel build jobs. Its outputs are a tar archive and SHA-256 checksum. The compile includes
Palace and its numerical dependencies. A change to a build input rebuilds the affected bundle.
Changing a benchmark deck, solving another frequency, or editing the benchmark harness reuses
the same solver. Both the standalone solver target and its benchmark depend on the same artifact.

Build both variants with `bazel build //tools/palace //tools/palace:palace_gpu`.
Each build action requests eight CPU slots and 9 GiB of RAM from Bazel's scheduler. This is a
scheduling estimate. On kratos, Bazel reported 20 CPU slots and 21,339 MiB of schedulable RAM,
enough for both actions to start together. Simulation MPI ranks and OpenMP threads are separate
runtime settings.

On first use the launcher verifies and extracts the archive under
`${XDG_CACHE_HOME:-$HOME/.cache}/guvna/palace-bundles/`. Later runs with the same checksum reuse
that directory. Budget disk space for the Bazel archive and its expanded copy. Benchmark targets
run the solver's version check and complete extraction before starting the solve timer.

To create a standalone directory outside Bazel, the optional `install_cpu` and `install_gpu`
targets run the same build recipe in an explicit prefix. They accept `--prefix` and `--jobs`.
Their output includes the toolchain, launcher, manifest, and build log.

## What is pinned

Bazel's repository cache holds the SHA-256-locked Debian packages, CUDA developer packages,
Palace source, superbuild sources, and upstream patches.
The package list comes from the signed Ubuntu Noble archive as of May 1, 2026. The CUDA packages
come from NVIDIA's Ubuntu 24.04 repository. CMake reads local sources for each dependency,
including nested fetches. The build shell has a read-only toolchain root, an empty home, and
a fixed environment. Bubblewrap isolates its network and hides the host GPU. The source worktree,
build directory, install destination, and temporary files are writable. The kernel and CPU come
from the host.

Palace and Umpire share one build of fmt 12.2.0. The build order prevents Umpire's bundled
headers from overwriting that installation. A pinned upstream fix supplies the bitwise
complement operator that fmt's 128-bit fallback needs when compiled by nvcc.
[fmt fix](https://github.com/fmtlib/fmt/pull/4813)

For an offline build, populate a portable Bazel repository cache while connected.

```sh
cache="$HOME/.cache/guvna/bazel-repository"
bazel fetch --repository_cache="$cache" \
  //examples:benchmark //examples:benchmark_gpu
```

On the offline machine, provide that cache, the checkout, the pinned Bazel executable, and the
host prerequisites above. Set `cache` to the copied directory and select the target to build.

```sh
bazel run --repository_cache="$cache" --repository_disable_download \
  //tools/palace:palace_gpu -- --version
```

## Verification on kratos, November 22, 2026

Both installers ran from an isolated Git clone with an empty home and Bazel output directory.
Bazel read the prefetched inputs with downloads disabled. CMake ran inside the pinned userspace.
On the i5-13600K, the concurrent builds took 18 min 17 s for CPU (5 jobs) and 23 min 1 s for GPU
(12 jobs). The installed bundles used 1.3 GiB and 7.7 GiB respectively. The GPU build targeted
`sm_89`. The runtime check used the RTX 4070 Ti with NVIDIA driver 595.99.02.

After relocating both installs, the four-port CPW benchmark ran sequentially with CPUs 0, 2, 4,
and 6 available and one OpenMP thread per MPI rank. At 2, 8, 14, and 20 GHz it compared both
driven columns to the upstream complex S-parameters. Each run converged in 23 to 37 iterations
for each of its eight solves. The times below are single trials.

| Device and libCEED backend | MPI ranks | Wall time | Largest absolute complex S error |
| --- | ---: | ---: | ---: |
| CPU, `/cpu/self/xsmm/blocked` | 4 | 32.47 s | 6.24e-8 |
| GPU, `/gpu/cuda/magma` (default) | 1 | 23.55 s | 6.21e-8 |
| GPU, `/gpu/cuda/shared` | 1 | 25.87 s | 6.21e-8 |

The subsequent Bazel action test used eight jobs per variant, with dependencies already
downloaded. The CPU action took 7 min 53 s and the GPU action took 25 min 54 s of execution.
A second CPU build overlapped part of the GPU build and took 10 min 46 s. Two-second samples of
proportional set size (PSS) for the compiler process trees peaked at 6.1 GiB for CPU, 7.7 GiB
for GPU, and 9.5 GiB combined. Their individual peaks occurred at different times.
Sampling started partway through the GPU build and covered the entire overlapping CPU build.
These measurements cover compilation and packaging on this host.

Both Bazel benchmark targets passed all eight CPW solves using their declared solver. The CPU
trial took 32.87 s with four MPI ranks and the MAGMA trial took 22.63 s with one. The largest
absolute complex S errors were 6.24e-8 and 6.21e-8 respectively. A repeat build of both solver
targets reported 0.044 s elapsed in Bazel and reused both compiled bundles.
