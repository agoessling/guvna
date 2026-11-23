"""Fetch pinned superbuild inputs, then configure a writable Palace v0.19.0 tree for offline use."""

import argparse
import concurrent.futures
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


LOCK = json.loads(Path(__file__).with_name("sources.lock.json").read_text())
ARCHIVES = {name.split(".")[0].upper(): name for name in LOCK if ".tar." in name or ".zip" in name}


def verify(path, expected):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        actual = digest.hexdigest()
        raise ValueError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")


def fetch_one(cache, name):
    spec = LOCK[name]
    target = cache / name
    if target.is_file():
        verify(target, spec["sha256"])
        return
    request = urllib.request.Request("".join(spec["url"]), headers={"User-Agent": "GuVNA-source"})
    for attempt in range(3):
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as stream:
            partial = Path(stream.name)
        try:
            with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as out:
                shutil.copyfileobj(response, out)
            verify(partial, spec["sha256"])
            partial.chmod(0o644)
            partial.replace(target)
            return
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
        finally:
            partial.unlink(missing_ok=True)


def local_url(cache, name):
    return f'URL "{cache / name}"\n  URL_HASH SHA256={LOCK[name]["sha256"]}'


GIT_SOURCE = re.compile(
    r'GIT_REPOSITORY\s+\$\{EXTERN_(\w+)_URL\}\n\s*GIT_TAG\s+\$\{EXTERN_\1_GIT_TAG\}'
    r'(?:\n\s*GIT_SUBMODULES[^\n]*)?'
)
URL_SOURCE = re.compile(r'\bURL\s+\$\{EXTERN_(\w+)_URL\}')


def update_file(path, transform):
    before = path.read_text()
    after = transform(before)
    if before != after:
        path.write_text(after)


def localize_module(contents, cache):
    def replace(match):
        archive = ARCHIVES.get(match[1])
        if archive:
            return local_url(cache, archive)
        return match[0]  # A solver disabled in both build variants.

    contents = URL_SOURCE.sub(replace, GIT_SOURCE.sub(replace, contents))
    contents = contents.replace("git reset --hard &&\n    git clean -fd &&\n    ", "")
    return contents.replace('git apply ', 'sh ${CMAKE_SOURCE_DIR}/cmake/guvna-apply.sh ')


def fast_float(cache, build, palace):
    # scnlib v4.0.1 configures its private fast_float dependency with FetchContent.
    sha = LOCK["fast_float.tar.gz"]["sha256"]
    build.mkdir(parents=True, exist_ok=True)
    directory = build / ("fast_float-" + sha)
    if not directory.is_dir():
        with tempfile.TemporaryDirectory(dir=build) as tmp:
            stage = Path(tmp) / "source"
            stage.mkdir()
            subprocess.run(
                ["tar", "xf", cache / "fast_float.tar.gz", "--strip-components=1", "-C", stage],
                check=True,
            )
            stage.rename(directory)

    option = f'"-DFETCHCONTENT_SOURCE_DIR_FAST_FLOAT={directory}"'
    path = palace / "cmake/ExternalScn.cmake"
    anchor = '"-DSCN_REGEX_BACKEND=std"'
    update_file(path, lambda s: s if option in s else s.replace(anchor, anchor + "\n  " + option))


def prepare(cache, palace, build):
    for name, spec in LOCK.items():
        verify(cache / name, spec["sha256"])

    fast_float(cache, build, palace)
    # Keep the upstream package configuration and point its fetches at local archives.
    for cmake in (palace / "cmake").glob("External*.cmake"):
        update_file(cmake, lambda s: localize_module(s, cache))
    # Umpire otherwise installs its bundled fmt headers over Palace's, in build-order-dependent
    # fashion. Both projects use Palace's fmt plus the upstream fix for nvcc (fmtlib/fmt#4813).
    fmt_module = palace / "cmake/ExternalFmt.cmake"
    fmt_project = "ExternalProject_Add(fmt\n"
    apply = "${CMAKE_SOURCE_DIR}/cmake/guvna-apply.sh"
    patch = f"  PATCH_COMMAND sh {apply} {cache}/fmt-uint128.patch"
    update_file(fmt_module, lambda s: s if patch in s else s.replace(
        fmt_project, fmt_project + patch + "\n"))
    umpire = palace / "cmake/ExternalUmpire.cmake"
    options = "set(UMPIRE_OPTIONS ${PALACE_SUPERBUILD_DEFAULT_ARGS}"
    update_file(umpire, lambda s: s.replace(
        options + ")", options + ' "-Dfmt_DIR=${CMAKE_INSTALL_PREFIX}/lib/cmake/fmt")'))
    extern = palace / "extern/CMakeLists.txt"
    fmt = "include(ExternalFmt)"
    dependency = "  ExternalProject_Add_StepDependencies(umpire configure fmt)"
    update_file(extern, lambda s: s if dependency in s else s.replace(
        fmt, fmt + "\nif(TARGET umpire)\n" + dependency + "\nendif()"))
    # CAMP requires an explicit host compiler when Palace itself imports Umpire. Set it on
    # this child only so that MFEM can select the MPI C++ wrapper for its CUDA link step.
    child = palace / "cmake/ExternalPalace.cmake"
    nvcc = '"-DCMAKE_CUDA_COMPILER=${CMAKE_CUDA_COMPILER}"'
    host = '"-DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++"'
    update_file(child, lambda s: s if host in s else s.replace(nvcc, nvcc + "\n    " + host))
    # file(DOWNLOAD) rechecks the original upstream SHA even for the local file URI.
    helper = palace / "cmake/PatchHelpers.cmake"
    update_file(helper, lambda s: s.replace('"${URL}"', f'"{cache.as_uri()}/${{FILENAME}}"'))

    unit = palace / "test/unit/CMakeLists.txt"
    upstream = "GIT_REPOSITORY https://github.com/catchorg/Catch2.git\n    GIT_TAG        v3.8.1"
    update_file(unit, lambda s: s.replace(upstream, local_url(cache, "catch2.tar.gz")))

    dst = palace / "cmake/guvna-apply.sh"
    data = Path(__file__).with_name("apply.sh").read_bytes()
    if not dst.exists() or dst.read_bytes() != data:
        dst.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="populate or verify a shareable source directory")
    fetch.add_argument("cache", type=Path)
    offline = commands.add_parser("prepare", help="localize fetches in a writable release tree")
    offline.add_argument("cache", type=Path)
    offline.add_argument("palace", type=Path)
    offline.add_argument("build", type=Path, help="build directory used by the caller")
    offline.add_argument("--cuda", action="store_true", help="also prepared by default")
    args = parser.parse_args()
    cache = args.cache.resolve()
    if args.command == "fetch":
        cache.mkdir(parents=True, exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda name: fetch_one(cache, name), LOCK))
    else:
        prepare(cache, args.palace, args.build.resolve())


if __name__ == "__main__":
    main()
