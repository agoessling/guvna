#!/usr/bin/env python3
"""Compile a Palace variant in private Bazel action storage and archive its runtime."""
import argparse
import collections
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def show_failure(work):
    for path in work.glob(".*.build-*/compile.log"):
        with path.open(errors="replace") as log:
            tail = collections.deque(maxlen=60)
            errors = 0
            for line in log:
                if errors < 20 and any(k in line for k in ("error:", "CMake Error", "Error ")):
                    print(line.rstrip(), file=sys.stderr)
                    errors += 1
                tail.append(line)
        sys.stderr.writelines(tail)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", choices=("cpu", "gpu"))
    parser.add_argument("installer", type=Path)
    parser.add_argument("recipe", type=Path)
    parser.add_argument("sysroot", type=Path)
    parser.add_argument("sources", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("digest", type=Path)
    parser.add_argument("--cuda-marker", type=Path)
    args = parser.parse_args()

    # Put the build on the output filesystem. CUDA and its objects may exceed a tmpfs.
    with tempfile.TemporaryDirectory(dir=args.archive.parent, prefix=args.archive.stem + "-") as td:
        work = Path(td).resolve()
        bundle = work / "bundle"
        command = [sys.executable, args.installer, args.device, args.recipe, args.sysroot,
                   args.sources, "--prefix", bundle, "--jobs", "8"]
        if args.cuda_marker:
            command.extend(["--cuda-marker", args.cuda_marker])
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            subprocess.run(command, env=env, check=True)
        except subprocess.CalledProcessError:
            show_failure(work)
            raise

        # GNU tar preserves sysroot symlinks and hard links. All member names are relative.
        archive = work / "bundle.tar"
        subprocess.run(["tar", "--sort=name", "--format=gnu", "--mtime=@0", "--owner=0",
                        "--group=0", "--numeric-owner", "-cf", archive, "-C", bundle, "."],
                       env=env, check=True)
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        checksum = work / "bundle.sha256"
        checksum.write_text(digest + "\n", encoding="ascii")
        os.replace(archive, args.archive)
        os.replace(checksum, args.digest)


if __name__ == "__main__":
    main()
