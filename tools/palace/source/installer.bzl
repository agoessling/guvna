"""Per-device launchers keep the CUDA toolkit out of CPU-only fetches."""
load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

def source_installer(device):
    data = [
        "compile.sh",
        "cuda.lock",
        "cuda.py",
        "deps/apply.sh",
        "deps/sources.lock.json",
        "deps/sources.py",
        "run.py",
        "sandbox.py",
        "sysroot.lock",
        "sysroot.py",
        "@guvna_build_sources//:ROOT",
        "@guvna_build_sources//:files",
        "@guvna_build_sysroot//:ROOT",
        "@guvna_build_sysroot//:files",
    ]
    args = [
        device,
        "$(rootpath :compile.sh)",
        "$(rootpath @guvna_build_sysroot//:ROOT)",
        "$(rootpath @guvna_build_sources//:ROOT)",
    ]
    if device == "gpu":
        data += ["@guvna_build_cuda//:ROOT", "@guvna_build_cuda//:files"]
        args += ["--cuda-marker", "$(rootpath @guvna_build_cuda//:ROOT)"]
    sh_binary(
        name = "install_" + device,
        srcs = ["install.py"],
        args = args,
        data = data,
        target_compatible_with = ["@platforms//cpu:x86_64", "@platforms//os:linux"],
    )
