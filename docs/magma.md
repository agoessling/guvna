# Diagnosing the CUDA MAGMA result on kratos

The refined spheres case on the RTX 4070 Ti exposed a shared-memory limit **per thread block**.
The first failed CUDA launch was `magma_interp_nontensor_t`. It requested **147,456 bytes** for
one block. The driver's `cuDeviceGetAttribute` reported an opt-in maximum of **101,376 bytes**
per block on the card. The ordinary per-block limit was 49,152 bytes.

## Evidence from the unmodified solver

The pinned image contains Palace `v0.19.0-541-gbe4b5d36f`, libCEED 1.0.0, and MAGMA 2.10.0.
The trial used one CPU thread, one MPI rank, cubic elements, one uniform refinement, 524,261
unknowns and both terminal excitations. The GPU build and archive are described in the
[CUDA setup guide](palace-gpu.md).

- Repeating the original case with CUDA launches made synchronous and a diagnostic library
  logging CUDA and libCEED errors reported `CUDA_ERROR_INVALID_VALUE` for grid `(150,1,1)`,
  block `(1,128,1)`, and 147,456 dynamic shared bytes.
- The next errors were libCEED failures to obtain vector access. At the final abort, the input
  vector had one outstanding reader. Its acquisition stack included `CeedElemRestrictionApply`,
  Palace's `ParOperator::EliminateRHS` and `LaplaceOperator::GetExcitationVector`. The printed
  `CeedVectorTakeArray` error is secondary. The failed run provides no complete capacitance matrix.
- The same image and deck with `Solver.Backend = "/gpu/cuda/shared"` completed both terminal
  excitations in eight iterations each. The largest relative capacitance difference from CPU was
  8.1e-13. This checks the numerical result obtained with the alternate backend.

libCEED's MAGMA backend selects its A100 tuning table on devices with SM 80 through SM 89.
The selected tile width controls both the compiled non-tensor basis kernel and the dynamic shared
memory requested at launch. For transposed interpolation the scratch allocation in doubles is
the larger of `P * Q` and `thread_columns * Q * tile_width`. libCEED multiplies by eight to obtain
the requested bytes. The launch path requests the opt-in shared-memory size before launching.
The driver rejected the oversized block. See the release sources in
[libCEED's MAGMA backend][backend] and [CUDA launcher][launch].

[backend]: https://github.com/CEED/libCEED/tree/v1.0.0/backends/magma
[launch]: https://github.com/CEED/libCEED/tree/v1.0.0/backends/cuda

## Controlled tile-width change

A diagnostic library adjusted one entry of libCEED's A100 transpose tuning table in this process,
immediately before `CeedInit`. This was equivalent to the following edit to the `drtc_t_a100`
table in the [libCEED 1.0.0 tuning data][table]. The numerical configuration and mesh matched the
failed refined run. The production image retains its original table.

```diff
-    {10, 14, 102400,  1, 6 },
+    {10, 14, 102400,  1, 3 },
```

[table]: https://github.com/CEED/libCEED/blob/v1.0.0/backends/magma/tuning/a100_rtc.h#L294

The table stores nearby benchmark shapes. The selected row serves the actual shape P=1, Q=24 for
114,896 elements. At 128 thread columns, changing the tile width from six to three cut the request
from 147,456 to 73,728 bytes. The host emitted 300 blocks in the grid to cover the same work that
previously required 150. Both launches of `magma_interp_nontensor_t` then returned CUDA success.
The refined MAGMA run completed in 32.63 s with 8 CG iterations per terminal. Its four capacitance
entries matched the shared CUDA result at the saved CSV precision, and agreed with the same-image
CPU result within 8.1e-13 relative.

This test isolates a resource-selection defect in libCEED's MAGMA backend for this device and
shape. For an upstream fix, the tile selector could bound scratch memory using the actual device's
per-block limit before compiling the kernel. The diagnostic changed a tuning entry shared by
multiple shapes and GPU models. Performance on those other combinations is unmeasured. For normal
GuVNA runs, the standard shared CUDA backend already handles this refined case.

## Does the MAGMA backend save time on a case that succeeds?

For the original 66,328-unknown spheres case, both backends passed the benchmark's analytical and
regression checks and converged in 9 and 9 CG iterations. Runs used the same CUDA image and default
field exports. The order was shared, MAGMA, MAGMA, shared, shared, MAGMA. One MPI rank used logical
CPU 10. Wall time includes startup and field export. The desktop and other CPU work shared the host,
and the CUDA JIT cache persisted between runs.

| libCEED backend | Wall time, three trials (s) | Median (s) |
| --- | --- | ---: |
| `/gpu/cuda/magma` | 9.57, 9.61, 13.20 | 9.61 |
| `/gpu/cuda/shared` | 14.22, 12.49, 14.31 | 14.22 |

The median runtime ratio was 1.48 in favor of MAGMA for this small workload. The overlapping ranges
show why this ratio alone is a poor predictor for another geometry or another mesh size.

```sh
runs="$HOME/.local/state/guvna/magma-check"
taskset -c 10 bazel run //examples:benchmark_prebuilt -- spheres --device GPU \
  --backend /gpu/cuda/magma --output "$runs/coarse-magma"
taskset -c 10 bazel run //examples:benchmark_prebuilt -- spheres --device GPU \
  --backend /gpu/cuda/shared --output "$runs/coarse-shared"
```

Add `--refine-spheres` and use fresh output directories to reproduce the refined failure and the
shared-backend control. Raw logs, the diagnostic source, and measured results from this host are in
`~/.local/share/guvna/benchmarks/2026-11-22/magma/`. The error trace is in
`refined-magma-trace/solver.log`. The intervention, its compiled hook and its run log are in
`refined-magma-tile/`.
