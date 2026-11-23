"""Build a relocatable Palace archive as a cacheable, offline Bazel action."""

def _resources(_os, _input_count):
    return {"cpu": 8, "memory": 9216}

def _bundle_impl(ctx):
    archive = ctx.actions.declare_file(ctx.label.name + ".tar")
    checksum = ctx.actions.declare_file(ctx.label.name + ".sha256")
    args = ctx.actions.args()
    args.add(ctx.attr.device)
    args.add(ctx.file._installer)
    args.add(ctx.file._compile)
    args.add(ctx.file._sysroot)
    args.add(ctx.file._sources)
    args.add(archive)
    args.add(checksum)
    inputs = [ctx.file._installer, ctx.file._compile, ctx.file._sysroot, ctx.file._sources]
    inputs.extend(ctx.files.recipe)
    archives = [ctx.attr._debs.files, ctx.attr._archives.files]
    if ctx.attr.device == "gpu":
        args.add("--cuda-marker", ctx.file.cuda_marker)
        inputs.append(ctx.file.cuda_marker)
        archives.append(ctx.attr.cuda_debs.files)
    ctx.actions.run(
        executable = ctx.file._helper,
        arguments = [args],
        inputs = depset(inputs, transitive = archives),
        outputs = [archive, checksum],
        mnemonic = "PalaceSourceBuild",
        progress_message = "Compiling and packaging Palace v0.19.0 (%s)" % ctx.attr.device,
        resource_set = _resources,
        env = {"PATH": "/usr/bin:/bin"},
        execution_requirements = {"no-sandbox": "1", "no-remote-exec": "1"},
    )
    return [DefaultInfo(files = depset([archive, checksum]))]

_palace_bundle = rule(
    implementation = _bundle_impl,
    attrs = {
        "device": attr.string(mandatory = True, values = ["cpu", "gpu"]),
        "recipe": attr.label_list(allow_files = True),
        "cuda_marker": attr.label(allow_single_file = True),
        "cuda_debs": attr.label(),
        "_helper": attr.label(default = ":build_bundle.py", allow_single_file = True),
        "_installer": attr.label(default = ":install.py", allow_single_file = True),
        "_compile": attr.label(default = ":compile.sh", allow_single_file = True),
        "_sysroot": attr.label(default = "@guvna_build_sysroot//:ROOT", allow_single_file = True),
        "_sources": attr.label(default = "@guvna_build_sources//:ROOT", allow_single_file = True),
        "_debs": attr.label(default = "@guvna_build_sysroot//:files"),
        "_archives": attr.label(default = "@guvna_build_sources//:files"),
    },
)

def palace_bundle(name, device):
    """Declare a CPU or CUDA archive. Select CUDA inputs only for GPU builds."""
    recipe = [
        ":deps/apply.sh",
        ":deps/sources.lock.json",
        ":deps/sources.py",
        ":run.py",
        ":sandbox.py",
        ":sysroot.lock",
        ":sysroot.py",
    ]
    cuda = {}
    if device == "gpu":
        recipe.extend([":cuda.lock", ":cuda.py"])
        cuda = {
            "cuda_marker": "@guvna_build_cuda//:ROOT",
            "cuda_debs": "@guvna_build_cuda//:files",
        }
    _palace_bundle(
        name = name,
        device = device,
        recipe = recipe,
        target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
        **cuda
    )
