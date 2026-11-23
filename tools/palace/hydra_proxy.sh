#!/bin/sh
# Installed next to MPICH's mpiexec, which locates its proxy through argv[0].
set -eu
runtime=${0%/palace_solver/bin/hydra_pmi_proxy}
syslib="$runtime/sysroot/usr/lib/x86_64-linux-gnu"
exec "$syslib/ld-linux-x86-64.so.2" --inhibit-cache \
    --library-path "$runtime/palace_solver.libs:$syslib" "$0.bin" "$@"
