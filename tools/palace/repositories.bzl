"""Pinned Linux x86-64 Palace runtime and its ELF userspace dependencies."""

_WHEEL = (
    "https://files.pythonhosted.org/packages/23/2f/" +
    "0dcbb2a3ee13ac19ead989d43243d7da399b9e050849352139145b116b3c/" +
    "palace_solver-0.19.0-py3-none-manylinux_2_28_x86_64.whl"
)
_WHEEL_HASH = "05b8ef647e2c21b37cd14e4f64672f3986b8c7cc81c334e86c4289373ca9d8ce"

# Debian 13 main packages supplying the manylinux wheel's external shared libraries.
_DEBS = [
    (
        "g/glibc/libc6_2.41-12+deb13u5_amd64.deb",
        "b59b0625cd1a791375d40dab23a4d5d3d0641e3d0a773501becdc3725b7f99cf",
    ),
    (
        "g/gcc-14/libstdc++6_14.2.0-19_amd64.deb",
        "ab1fa05837aa7a92aae748fd07a18a35f7d18bb4a71c4724fe2bbf0e32089de0",
    ),
    (
        "g/gcc-14/libgcc-s1_14.2.0-19_amd64.deb",
        "3c71917b490d1a17aed43196a2787a256ecf060526cdb20216a74bedc061b150",
    ),
    (
        "g/gcc-14/libatomic1_14.2.0-19_amd64.deb",
        "212b399aae2f7299203d261a57e49372e09565a9a5ea971905f94a3960366c05",
    ),
    (
        "z/zlib/zlib1g_1.3.dfsg+really1.3.1-1+deb13u1_amd64.deb",
        "8c27c342230503b73dfde629642c3b352e87b554e06d60cf58772f236a305ceb",
    ),
]

def _cpu_runtime(ctx):
    ctx.download_and_extract(_WHEEL, sha256 = _WHEEL_HASH, type = "zip")
    # Hydra executes a sibling helper. Use the pinned loader for that process as well.
    proxy = "palace_solver/bin/hydra_pmi_proxy"
    ctx.rename(proxy, proxy + ".bin")
    ctx.template(proxy, Label("//tools/palace:hydra_proxy.sh"))
    for path, digest in _DEBS:
        urls = [
            "https://deb.debian.org/debian/pool/main/" + path,
            "https://snapshot.debian.org/archive/debian/20261122T000000Z/pool/main/" + path,
        ]
        ctx.download_and_extract(urls, "deb", sha256 = digest, type = "deb")
        ctx.extract("deb/data.tar.xz", "sysroot")
        ctx.delete("deb")
    ctx.file("BUILD.bazel", """
filegroup(
    name = "runtime",
    srcs = glob([
        "palace_solver/bin/palace-real",
        "palace_solver/bin/mpiexec",
        "palace_solver/bin/hydra_pmi_proxy*",
        "palace_solver.libs/**/*",
        "sysroot/usr/lib/x86_64-linux-gnu/*.so*",
    ]),
    visibility = ["//visibility:public"],
)
""")

cpu_runtime = repository_rule(implementation = _cpu_runtime)
