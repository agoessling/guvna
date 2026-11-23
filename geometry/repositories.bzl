"""Headless Gmsh Python API with a pinned Linux x86-64 interpreter and ELF runtime."""

def _gmsh_impl(ctx):
    wheel = "gmsh-4.15.2-py2.py3-none-manylinux_2_24_x86_64.whl"
    base = "https://files.pythonhosted.org/packages/ab/d4/"
    path = "336becb1488ac4fbab205043987128839c8c62d54e2036b7e887bd009040/"
    ctx.download_and_extract(
        base + path + wheel,
        "wheel",
        type = "zip",
        sha256 = "4076a948ce22625330d1413d4982e22b5c69fc2f0f7951f5df64c778cf54108c",
    )
    ctx.rename("wheel/gmsh.py", "python/gmsh.py")
    ctx.rename("wheel/gmsh-4.15.2.data/data/lib/libgmsh.so.4.15", "python/libgmsh.so.4.15")
    lines = ctx.read(ctx.attr.lock).strip().splitlines()
    for i in range(0, len(lines), 2):
        key = lines[i].replace("+", "%2B")
        urls = [
            "https://deb.debian.org/debian/" + key,
            "https://snapshot.debian.org/archive/debian/20261122T000000Z/" + key,
        ]
        ctx.download_and_extract(urls, "deb", sha256 = lines[i + 1], type = "deb")
        ctx.extract("deb/data.tar.xz", "root")
        ctx.delete("deb")

    ctx.file("ROOT", "", executable = False)
    ctx.file("BUILD.bazel", """
package(default_visibility = ["//visibility:public"])
filegroup(
    name = "runtime",
    srcs = ["ROOT"] + glob([
        "python/*",
        "root/usr/bin/python3.13",
        "root/usr/lib/python3.13/**/*.py",
        "root/usr/lib/python3.13/lib-dynload/*.so",
        "root/usr/lib/x86_64-linux-gnu/*.so*",
    ]),
)
""")

gmsh_runtime = repository_rule(
    implementation = _gmsh_impl,
    attrs = {"lock": attr.label(allow_single_file = True, mandatory = True)},
)
