#!/bin/bash
# Runs inside the pinned build root with a writable source copy for each variant.
set -euo pipefail

if [[ $# != 2 || ! "$2" =~ ^[1-9][0-9]*$ ]]; then
    echo 'Usage: compile.sh cpu|gpu JOBS' >&2
    exit 2
fi
variant=$1
jobs=$2
prepare=(python3 /recipe/deps/sources.py prepare /src/deps /src/palace /build)
case "$variant" in
    cpu)
        device_flags=(-DPALACE_WITH_CUDA=OFF -DPALACE_WITH_MAGMA=OFF)
        ;;
    gpu)
        cuda=/usr/local/cuda-12.9
        export PATH="$cuda/bin:$PATH"
        # HYPRE compiles C sources with nvcc, bypassing the MPI wrapper's include paths.
        mpi_includes=$(mpicxx --showme:incdirs)
        export CPATH="${mpi_includes// /:}"
        device_flags=(
            -DPALACE_WITH_CUDA=ON
            -DPALACE_WITH_MAGMA=ON
            -DCMAKE_CUDA_ARCHITECTURES=89
            "-DCMAKE_CUDA_COMPILER=$cuda/bin/nvcc"
            "-DCUDAToolkit_ROOT=$cuda"
            -DPALACE_WITH_GPU_AWARE_MPI=OFF
        )
        prepare+=(--cuda)
        ;;
    *)
        echo "Unknown device: $variant" >&2
        exit 2
        ;;
esac

"${prepare[@]}"
export PKG_CONFIG_PATH=/opt/palace/lib/pkgconfig
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
# The superbuild invokes GNU make directly for PETSc, SLEPc, LIBXSMM, libCEED and GSLIB.
cmake -G 'Unix Makefiles' -S /src/palace -B /build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/opt/palace \
    -DCMAKE_C_COMPILER=/usr/bin/mpicc \
    -DCMAKE_CXX_COMPILER=/usr/bin/mpicxx \
    -DCMAKE_Fortran_COMPILER=/usr/bin/mpifort \
    -DBLA_VENDOR=OpenBLAS \
    -DBUILD_SHARED_LIBS=ON \
    -DPALACE_GIT_COMMIT_ID=v0.19.0 \
    "-DPALACE_BUILD_ID=guvna-source-$variant" \
    -DPALACE_WITH_OPENMP=ON \
    -DPALACE_WITH_SUPERLU=ON \
    -DPALACE_WITH_STRUMPACK=ON \
    -DPALACE_WITH_SLEPC=ON \
    -DPALACE_WITH_LIBXSMM=ON \
    -DPALACE_WITH_SUNDIALS=ON \
    -DPALACE_WITH_GSLIB=ON \
    "${device_flags[@]}"
cmake --build /build --parallel "$jobs" --target palace
