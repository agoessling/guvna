#!/usr/bin/env python3
"""Build Palace from locked inputs in an isolated userspace and install a relocatable directory."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

COMMON = ("compile.sh", "sandbox.py", "sysroot.py", "sysroot.lock", "run.py",
          "deps/sources.py", "deps/sources.lock.json", "deps/apply.sh")


def atomic_tree(destination, create):
    if destination.is_dir():
        return
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        stage = Path(tmp) / "tree"
        create(stage)
        stage.rename(destination)


def install(args):
    from sandbox import compile_variant
    import sysroot

    variant = args.device
    recipe = args.recipe.parent
    files = list(COMMON)
    if variant == "gpu":
        files.extend(["cuda.py", "cuda.lock"])
    fingerprint = hashlib.sha256()
    for file in sorted(files):
        fingerprint.update(file.encode() + b"\0" + (recipe / file).read_bytes())
    fingerprint.update(Path(__file__).read_bytes())
    manifest = {"palace": "v0.19.0", "device": variant, "recipe_sha256": fingerprint.hexdigest()}
    prefix = args.prefix
    if prefix is None:
        data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        prefix = data / "guvna" / ("palace-v0.19.0-" + variant)
    prefix = (Path(os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd())) / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    scratch = prefix.parent / f".{prefix.name}.build-{fingerprint.hexdigest()[:12]}"
    with (prefix.parent / f".{prefix.name}.install.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        if prefix.exists():
            record = prefix / "manifest.json"
            if record.is_file() and json.loads(record.read_text()) == manifest:
                print(prefix / "bin/palace")
                return
            sys.exit(f"Choose an unused install prefix. Existing directory: {prefix}")
        scratch.mkdir(exist_ok=True)
        bundle = scratch / "bundle"
        bundle.mkdir(exist_ok=True)
        # Copy declared recipe inputs so Bazel runfile symlinks resolve even inside bwrap.
        isolated_recipe = scratch / "recipe"
        for file in files:
            dst = isolated_recipe / file
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(recipe / file, dst)
        print("Extracting verified toolchain packages", flush=True)
        atomic_tree(bundle / "root", lambda dest: sysroot.install(
            args.sysroot.parent, dest, recipe / "sysroot.lock"))
        cuda_dir = None
        if args.cuda_marker:
            import cuda
            cuda_dir = bundle / "cuda"
            atomic_tree(cuda_dir, lambda dest: cuda.install(
                args.cuda_marker.parent, dest, recipe / "cuda.lock"))

        def extract_palace(dest):
            dest.mkdir()
            subprocess.run(["tar", "-xzf", args.sources.parent / "palace.tar.gz",
                            "--strip-components=1", "--no-same-owner", "-C", dest], check=True)

        atomic_tree(scratch / "src", extract_palace)
        build = scratch / "build"
        build.mkdir(exist_ok=True)
        solver = bundle / "solver"
        solver.mkdir(exist_ok=True)
        log_path = scratch / "compile.log"
        print(f"Building {variant} offline with {args.jobs} jobs. Follow {log_path}", flush=True)
        with log_path.open("ab") as log:
            compile_variant(bundle / "root", scratch / "src", args.sources.parent, isolated_recipe,
                            build, solver, cuda_dir, args.jobs, log)
        launcher = bundle / "bin/palace"
        launcher.parent.mkdir(exist_ok=True)
        shutil.copy2(recipe / "run.py", launcher)
        launcher.chmod(0o755)
        if not os.access(solver / "bin/palace-x86_64.bin", os.X_OK):
            raise RuntimeError(f"Palace executable missing after compilation in {solver}")
        (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        shutil.copyfile(log_path, bundle / "compile.log")
        bundle.rename(prefix)
        shutil.rmtree(scratch)
    print(prefix / "bin/palace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", choices=["cpu", "gpu"])
    parser.add_argument("recipe", type=Path)
    parser.add_argument("sysroot", type=Path)
    parser.add_argument("sources", type=Path)
    parser.add_argument("--cuda-marker", type=Path)
    parser.add_argument("--prefix", type=Path, help="new directory for the standalone installation")
    parser.add_argument("--jobs", type=int, default=min(6, len(os.sched_getaffinity(0))))
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    # Resolve the marker's actual external repository, containing all pinned input files.
    args.recipe = args.recipe.absolute()
    args.sysroot = args.sysroot.resolve(strict=True)
    args.sources = args.sources.resolve(strict=True)
    if args.cuda_marker:
        args.cuda_marker = args.cuda_marker.resolve(strict=True)
    sys.path.insert(0, str(args.recipe.parent))
    install(args)


if __name__ == "__main__":
    main()
