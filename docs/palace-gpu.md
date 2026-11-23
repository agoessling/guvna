# Palace GPU runtime on Linux

The CUDA trial uses the upstream Palace main-branch image for x86-64-v3 CPUs. It includes compute
capability 8.9 for the RTX 4070 Ti. The Palace revision is
`be4b5d36ffe77933d4dbf86209d2bf21a2059fe3`. The image contains the solver, MPI, CUDA toolkit
runtime, and numerical libraries. The host supplies its kernel, NVIDIA driver and devices,
Bazel, Bubblewrap, Python 3, and unsquashfs. Installation is per-user.

From the project root, provision once before timing a solve.

```sh
bazel run //tools:install_palace_gpu
```

Bazel's `http_archive` fetches and verifies the 1.5 GiB ZIP, caches it in the repository cache,
and exposes the SIF it contains. The install target uses unsquashfs to unpack the 2.6 GiB runtime
under `$XDG_CACHE_HOME/guvna` (default `~/.cache/guvna`). The GPU launcher provisions it on first
use. The CPU benchmark target can run without fetching the CUDA image.

The GitHub API listed the upstream artifact expiration as 2026-11-23 03:01:55 UTC. Bazel can
restore the SIF from a populated repository cache after expiry. A machine with an empty cache
can seed it with the original ZIP using `--distdir` and the filename below. Kratos retains the
original download in `~/.local/share/guvna`. The launcher also accepts an existing local ZIP via
`GUVNA_PALACE_GPU_ARCHIVE` for compatibility.

- Archive filename `palace-x86_64_v3_cuda-be4b5d3-sif.zip`
- SHA-256 `413897111b8d13ae47a779bc55ddc094a16937e51b04860d4b72d97a0f849135`
- [Upstream CI run](https://github.com/awslabs/palace/actions/runs/44967638698)
- Upstream artifact ID `14737250411`

For a second machine with SSH access to kratos, the retained archive supplies the same image
after the CI download expires. From a GuVNA checkout on that machine, run

```sh
archive=palace-x86_64_v3_cuda-be4b5d3-sif.zip
scp "kratos:.local/share/guvna/$archive" "/tmp/$archive"
bazel run --distdir=/tmp //tools:install_palace_gpu
```

For a direct solve, change to the run directory containing the input JSON and mesh and invoke
`/path/to/guvna/tools/palace_gpu config.json`. This directory is writable inside the image. The
JSON `Solver.Device` field selects `GPU` or `CPU`. Use the benchmark harness for the upstream
example inputs, timing, and numerical checks.

For example, run the release-tagged case through the GPU image from the project root.

```sh
runs="$HOME/.local/state/guvna/runs"
bazel run //examples:benchmark_prebuilt -- spheres --device GPU --output "$runs/spheres-gpu-1"
```

For a same-build CPU control, add `--device CPU --palace "$PWD/tools/palace_gpu"` and use a new
output directory. This upstream image was built without OpenMP. The default is one MPI rank.
Use `--ranks 2` to compare two ranks on one card. See the [MPI results](mpi.md).
A persistent per-image CUDA JIT cache amortizes compilation across trials. Keep the mesh, save
options and linear solver fixed when comparing the devices.

For the refined spheres trial select the shared-memory CUDA backend explicitly. On the pinned image
the default MAGMA backend aborted inside `CeedVectorTakeArray` before the second terminal solve.
Both terminal solves converged with `/gpu/cuda/shared` using the same discretization.

```sh
bazel run //examples:benchmark_prebuilt -- spheres --device GPU --refine-spheres \
  --backend /gpu/cuda/shared --output "$runs/spheres-refined-gpu-1"
```
