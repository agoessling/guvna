"""Materialize the locked Ubuntu Noble compiler, OpenMPI, BLAS and standard utilities."""
from pathlib import Path
import subprocess


def install(packages, root, lock):
    names = lock.read_text().splitlines()[::2]
    root.mkdir()
    for name in names:
        subprocess.run(["dpkg-deb", "--threads-max=2", "-x", packages / Path(name).name, root],
                       check=True)

    for name in ("dev", "proc", "sys", "tmp", "etc", "root", "opt/palace", "build", "src/deps",
                 "src/palace", "recipe", "work", "usr/local/cuda-12.9"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "usr/local/cuda").symlink_to("cuda-12.9")
    # The tar payloads omit alternatives normally selected by Debian's maintainer scripts.
    bindir = root / "usr/bin"
    aliases = {"cc": "gcc", "c++": "g++", "f77": "gfortran", "f95": "gfortran",
               "awk": "mawk", "sh": "dash", "which": "which.debianutils",
               "mpicc": "opal_wrapper", "mpicxx": "opal_wrapper", "mpic++": "opal_wrapper",
               "mpifort": "opal_wrapper", "mpif90": "opal_wrapper", "mpiexec": "orterun",
               "mpirun": "orterun", "pkg-config": "pkgconf"}
    for alias, target in aliases.items():
        if not (bindir / alias).is_symlink() and not (bindir / alias).exists():
            (bindir / alias).symlink_to(target)
    libdir = root / "usr/lib/x86_64-linux-gnu"
    for lib in ("libopenblas.so", "libopenblas.so.0", "libblas.so", "libblas.so.3",
                "liblapack.so", "liblapack.so.3"):
        (libdir / lib).symlink_to("openblas-pthread/" + lib)
    (libdir / "libmpi.so").symlink_to("openmpi/lib/libmpi.so")
    (libdir / "pkgconfig/openblas.pc").symlink_to("../openblas-pthread/pkgconfig/openblas.pc")
    (root / "etc/passwd").write_text("root:x:0:0:root:/root:/bin/sh\n")
    (root / "etc/group").write_text("root:x:0:\n")
    (root / "etc/hosts").write_text("127.0.0.1 localhost palace-build\n")
    (root / "etc/nsswitch.conf").write_text("hosts: files dns\n")
