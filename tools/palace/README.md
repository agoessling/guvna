# Prebuilt Palace CPU reference

The normal CPU and GPU targets build Palace from source. See the
[source build guide](source/README.md) for solver and benchmark commands.

For comparisons with the published wheel, use the following target on Linux x86-64.

```sh
bazel run //tools/palace:palace_prebuilt -- --version
```

Bazelisk selects the version in `.bazelversion`. Bazel fetches the third-party
[palace-solver wheel](https://pypi.org/project/palace-solver/0.19.0/) and Debian 13 runtime
packages into its cache. The repository rule pins each artifact by SHA-256 and extracts it without
root, pip, or a system MPI installation. The launcher invokes the bundled native solver using the
pinned ELF loader, C and C++ runtime libraries, MPI, linear algebra libraries, and zlib. The Linux
kernel, CPU instruction set, Bazel bootstrap, shell, and shell utilities come from the host.
Bazel generates its local module lockfile. Direct Bazel module versions are in `MODULE.bazel`.

To use an existing case outside the checkout, build the executable and invoke it from the case
directory. Palace resolves relative mesh and output paths against the process working directory.

```sh
bazel build //tools/palace:palace_prebuilt
solver="$(bazel info bazel-bin)/tools/palace/palace_prebuilt"
(cd /path/to/case && "$solver" config.json)
```

The default is one MPI rank and one OpenMP thread. Put `-np N` before the solver arguments to
launch N local ranks with the wheel's MPICH Hydra and process-management proxy. Set
`OMP_NUM_THREADS` to select the OpenMP threads per rank. OpenBLAS stays single-threaded to avoid
nested parallelism in direct solvers. The launcher preserves the caller's CPU affinity.

```sh
(cd /path/to/case && OMP_NUM_THREADS=2 "$solver" -np 2 config.json)
```

See the [MPI and OpenMP comparison](../../docs/mpi.md) for verified rank counts and timings.

After the build has populated the cache, verify the same runtime with downloads disabled:

```sh
bazel run --repository_disable_download //tools/palace:palace_prebuilt -- --version
```
