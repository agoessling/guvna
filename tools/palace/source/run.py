#!/usr/bin/env python3
"""Run the locally built Palace bundle with its own MPI and userspace."""
import os
from pathlib import Path
import sys


def main():
    bundle = Path(__file__).resolve().parents[1]
    args = ["bwrap", "--die-with-parent", "--unshare-pid", "--ro-bind", bundle / "root", "/",
            "--ro-bind", bundle / "solver", "/opt/palace", "--dev", "/dev", "--proc", "/proc",
            "--ro-bind", "/sys", "/sys", "--tmpfs", "/tmp", "--dir", "/tmp/home",
            "--bind", Path.cwd(), "/work", "--chdir", "/work", "--clearenv",
            "--setenv", "HOME", "/tmp/home", "--setenv", "PATH", "/opt/palace/bin:/usr/bin:/bin",
            "--setenv", "OPENBLAS_NUM_THREADS", "1",
            "--setenv", "OMP_NUM_THREADS", os.environ.get("OMP_NUM_THREADS", "1"),
            "--setenv", "OMPI_MCA_plm", "isolated", "--setenv", "OMPI_MCA_btl", "self,vader,tcp",
            "--setenv", "OMPI_MCA_btl_base_warn_component_unused", "0"]
    libpath = "/opt/palace/lib:/opt/palace/lib64"
    if (bundle / "cuda").is_dir():
        args.extend(["--ro-bind", bundle / "cuda", "/usr/local/cuda-12.9", "--dir", "/tmp/driver"])
        jit = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "guvna/palace-cuda"
        jit.mkdir(parents=True, exist_ok=True)
        args.extend(["--bind", jit, "/tmp/cuda-cache", "--setenv", "CUDA_CACHE_PATH",
                     "/tmp/cuda-cache"])
        for dev in sorted(Path("/dev").glob("nvidia*")):
            args.extend(["--dev-bind", dev, dev])
        libdir = Path("/usr/lib/x86_64-linux-gnu")
        for pattern in ("libcuda.so*", "libnvidia-ptxjitcompiler.so*", "libnvidia-gpucomp.so*",
                        "libnvidia-nvvm*.so*"):
            for lib in sorted(libdir.glob(pattern)):
                args.extend(["--ro-bind", lib.resolve(), "/tmp/driver/" + lib.name])
        libpath += ":/tmp/driver:/usr/local/cuda-12.9/lib64"
    args.extend(["--setenv", "LD_LIBRARY_PATH", libpath])
    cli = sys.argv[1:]
    if cli[:1] in (["-np"], ["--np"]):
        if len(cli) < 2 or not cli[1].isdigit() or int(cli[1]) < 1:
            sys.exit("Expected a positive MPI rank count after -np")
        if int(cli[1]) > 1:
            args.extend(["/usr/bin/mpiexec", "--allow-run-as-root", "--bind-to", "none",
                         "-np", cli[1]])
        cli = cli[2:]
    args.extend(["/opt/palace/bin/palace-x86_64.bin", *cli])
    os.execvp("bwrap", args)


if __name__ == "__main__":
    main()
