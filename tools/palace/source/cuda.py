"""Extract the locked CUDA 12.9 developer packages, including nvcc and the sm_89 libraries."""
import subprocess
import tempfile
from pathlib import Path


def install(packages, toolkit, lock):
    with tempfile.TemporaryDirectory(dir=toolkit.parent) as tmp:
        for name in lock.read_text().splitlines()[::2]:
            subprocess.run(["dpkg-deb", "--threads-max=2", "-x", packages / name, tmp], check=True)
        (Path(tmp) / "usr/local/cuda-12.9").rename(toolkit)
