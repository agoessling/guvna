"""Download the build inputs into Bazel's checksum-addressed repository cache."""

_INPUTS_BUILD = """
package(default_visibility = ["//visibility:public"])
exports_files(["ROOT"])
filegroup(
    name = "files",
    srcs = [
%s
    ],
)
"""

def _locked_inputs_impl(ctx):
    raw = ctx.read(ctx.attr.lock)
    inputs = {}
    if ctx.attr.deb_base:
        lines = raw.strip().splitlines()
        if len(lines) % 2:
            fail("Incomplete path, checksum pair in " + str(ctx.attr.lock))
        for i in range(0, len(lines), 2):
            path = lines[i]
            name = path.split("/")[-1]
            if name in inputs:
                fail("Duplicate archive basename in lock: " + name)
            inputs[name] = (ctx.attr.deb_base + path.replace("+", "%2B"), lines[i + 1])
    else:
        for name, spec in json.decode(raw).items():
            inputs[name] = ("".join(spec["url"]), spec["sha256"])

    # Keep a bounded number of remote objects in flight even with a completely cold cache.
    names = sorted(inputs)
    for offset in range(0, len(names), 8):
        requests = []
        for name in names[offset:offset + 8]:
            url, sha = inputs[name]
            requests.append(ctx.download(url = url, output = name, sha256 = sha, block = False))
        for request in requests:
            request.wait()
    ctx.file("ROOT", "", executable = False)
    labels = "\n".join(["        %s," % repr(name) for name in names])
    ctx.file("BUILD.bazel", _INPUTS_BUILD % labels, executable = False)

locked_inputs = repository_rule(
    implementation = _locked_inputs_impl,
    attrs = {
        "lock": attr.label(mandatory = True, allow_single_file = True),
        "deb_base": attr.string(),
    },
)
