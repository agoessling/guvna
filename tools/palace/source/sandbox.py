"""Run the Palace build with only the pinned inputs and a loopback-only network."""
from pathlib import Path
import subprocess
import sys


def compile_variant(root, sources, dependencies, recipe, build, install, cuda, jobs, log=None):
    args = ["bwrap", "--die-with-parent", "--unshare-all", "--uid", "0", "--gid", "0",
            "--hostname", "palace-build", "--ro-bind", root, "/", "--proc", "/proc",
            "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/tmp/home",
            "--ro-bind", recipe, "/recipe", "--ro-bind", dependencies, "/src/deps",
            "--bind", sources, "/src/palace", "--bind", build, "/build",
            "--bind", install, "/opt/palace", "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp/home",
            "--setenv", "LC_ALL", "C", "--setenv", "TZ", "UTC",
            "--setenv", "OMPI_ALLOW_RUN_AS_ROOT", "1",
            "--setenv", "OMPI_ALLOW_RUN_AS_ROOT_CONFIRM", "1",
            "--setenv", "OMPI_MCA_plm", "isolated", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            "--chdir", "/build"]
    if cuda:
        args.extend(["--ro-bind", cuda, "/usr/local/cuda-12.9"])
    args.extend(["/bin/bash", "/recipe/compile.sh", "gpu" if cuda else "cpu", str(jobs)])
    subprocess.run(args, check=True, stdout=log, stderr=subprocess.STDOUT)


if __name__ == "__main__":
    # Convenience entry for the same isolated build, using prepared inputs.
    base, work, variant, jobs = sys.argv[1:]
    base, work = Path(base).resolve(), Path(work).resolve()
    compile_variant(base / "root", work / "src", base / "deps", Path(__file__).resolve().parent,
                    work / "build", work / "install", base / "cuda" if variant == "gpu" else None,
                    jobs)
