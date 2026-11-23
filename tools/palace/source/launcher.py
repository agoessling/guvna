#!/usr/bin/env python3
"""Launch the source-built Palace bundle supplied in this target's runfiles."""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def bundle_files():
    launcher = Path(__file__).absolute()
    roots = [Path(str(launcher) + ".runfiles")]
    roots.extend(parent for parent in launcher.parents if parent.name.endswith(".runfiles"))
    if os.environ.get("RUNFILES_DIR"):
        roots.append(Path(os.environ["RUNFILES_DIR"]))
    roots.append(Path(str(launcher.resolve()) + ".runfiles"))
    for root in roots:
        archive, checksum = root / "@ARCHIVE@", root / "@CHECKSUM@"
        if checksum.is_file() and archive.is_file():
            return archive, checksum
    sys.exit(f"Cannot locate the Palace @DEVICE@ archive and checksum in runfiles for {launcher}")


def extract(archive, checksum):
    match = re.match(r"^([0-9a-f]{64})(?:\s|$)", checksum.read_text())
    if match is None:
        sys.exit(f"Invalid SHA-256 in {checksum}")
    digest = match[1]
    cache_home = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    cache = cache_home / "guvna/palace-bundles/@DEVICE@"
    cache.mkdir(parents=True, exist_ok=True)
    bundle = cache / digest
    executable = bundle / "bin/palace"
    with (cache / (digest + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not executable.is_file():
            with archive.open("rb") as stream, tempfile.TemporaryDirectory(dir=cache) as work:
                sha = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    sha.update(block)
                if sha.hexdigest() != digest:
                    sys.exit(f"SHA-256 mismatch for {archive}")
                stream.seek(0)
                staged = Path(work) / "bundle"
                staged.mkdir()
                subprocess.run(["tar", "-xf", "-", "--no-same-owner", "-C", staged],
                               stdin=stream, check=True)
                if not os.access(staged / "bin/palace", os.X_OK):
                    sys.exit(f"Missing executable bin/palace in {archive}")
                staged.rename(bundle)
    return executable.absolute()


def main():
    executable = extract(*bundle_files())
    if os.environ.get("BUILD_WORKING_DIRECTORY"):
        os.chdir(os.environ["BUILD_WORKING_DIRECTORY"])
    os.execv(executable, [str(executable), *sys.argv[1:]])


if __name__ == "__main__":
    main()
