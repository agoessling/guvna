#!/bin/bash
set -euo pipefail
marker=$(rlocation gmsh_runtime/ROOT)
runtime=$(dirname "$(realpath "$marker")")
script=$(rlocation _main/geometry/generate.py)
package_root=$(dirname "$(dirname "$(realpath "$script")")")
if [[ -n ${BUILD_WORKING_DIRECTORY:-} && "$PWD" == *.runfiles/_main ]]; then
    cd "$BUILD_WORKING_DIRECTORY"
fi
lib="$runtime/root/usr/lib/x86_64-linux-gnu"
exec env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
    PYTHONNOUSERSITE=1 PYTHONPATH="$package_root:$runtime/python" \
    PYTHONHOME="$runtime/root/usr" \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 LC_ALL=C \
    "$lib/ld-linux-x86-64.so.2" --inhibit-cache --library-path "$lib" \
    "$runtime/root/usr/bin/python3.13" -B -m geometry.generate "$@"
