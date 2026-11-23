"""Expose a source-built Palace bundle as a Bazel executable."""

def _runfile(ctx, file):
    if file.short_path.startswith("../"):
        return file.short_path[3:]
    return ctx.workspace_name + "/" + file.short_path

def _palace_solver_impl(ctx):
    files = ctx.files.bundle
    archives = [f for f in files if f.basename.endswith(".tar")]
    sums = [f for f in files if f.basename.endswith(".sha256")]
    if len(archives) != 1 or len(sums) != 1:
        fail("bundle must provide one .tar and one .sha256")

    launcher = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.expand_template(
        template = ctx.file._template,
        output = launcher,
        substitutions = {
            "@ARCHIVE@": _runfile(ctx, archives[0]),
            "@CHECKSUM@": _runfile(ctx, sums[0]),
            "@DEVICE@": ctx.attr.device,
        },
        is_executable = True,
    )
    return [DefaultInfo(
        executable = launcher,
        runfiles = ctx.runfiles(files = archives + sums),
    )]

palace_solver = rule(
    implementation = _palace_solver_impl,
    attrs = {
        "bundle": attr.label(mandatory = True, allow_files = True),
        "device": attr.string(mandatory = True, values = ["cpu", "gpu"]),
        "_template": attr.label(default = Label(":launcher.py"), allow_single_file = True),
    },
    executable = True,
)
