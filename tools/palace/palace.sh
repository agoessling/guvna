#!/bin/bash
set -euo pipefail

solver=$(rlocation palace_cpu/palace_solver/bin/palace-real)
loader=$(rlocation palace_cpu/sysroot/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2)
wheel_libs="${solver%/palace_solver/bin/palace-real}/palace_solver.libs"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
# The wheel's single-rank MUMPS path can deadlock with nested BLAS threads.
export OPENBLAS_NUM_THREADS=1
unset LD_PRELOAD LD_AUDIT LD_LIBRARY_PATH
# Bazel starts a top-level run in its runfiles tree. Preserve an explicit subprocess cwd.
if [[ -n "${BUILD_WORKING_DIRECTORY:-}" && "$PWD" == *.runfiles/_main ]]; then
    cd "$BUILD_WORKING_DIRECTORY"
fi
ranks=1
if [[ ${1:-} == -np || ${1:-} == --np ]]; then
    ranks=${2:-}
    if [[ ! "$ranks" =~ ^[1-9][0-9]*$ ]]; then
        echo 'Expected a positive MPI rank count after -np.' >&2
        exit 2
    fi
    shift 2
fi

load=("$loader" --inhibit-cache --library-path "$wheel_libs:${loader%/*}")
if [[ "$ranks" != 1 ]]; then
    mpiexec="${solver%/*}/mpiexec"
    exec "${load[@]}" "$mpiexec" -launcher fork -bind-to none -n "$ranks" \
        "${load[@]}" "$solver" "$@"
fi
exec "${load[@]}" "$solver" "$@"
