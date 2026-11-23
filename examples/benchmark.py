#!/usr/bin/env python3
"""Run and validate a pinned Palace example on Linux."""
import argparse
import cmath
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


# (deck, mesh, upstream regression directory, number of primary solves)
CASES = {
    "coaxial": ("coaxial_lumped_wave.json", "coaxial.msh", "coaxial/lumped_wave", 6),
    "cpw": ("cpw_lumped_uniform.json", "cpw_lumped_0.msh", "cpw/lumped_uniform", 8),
    "spheres": ("spheres.json", "spheres.msh", "spheres", 2),
    "transmon": ("transmon_amr.json", "transmon.msh2", "transmon/transmon_amr", None),
}
CPW_GHZ = (2.0, 8.0, 14.0, 20.0)


def rows(path):
    with path.open() as stream:
        reader = csv.reader(stream)
        header = [field.strip() for field in next(reader)]
        values = [[float(value) for value in row] for row in reader]
    if not all(math.isfinite(value) for row in values for value in row):
        raise ValueError(f"Nonfinite output in {path}")
    return header, values


def validate(case, reference, result, refined=False):
    header, expected = rows(reference)
    if case == "cpw":
        expected = [row for row in expected if row[0] in CPW_GHZ]
        if tuple(row[0] for row in expected) != CPW_GHZ:
            raise ValueError(f"Missing CPW comparison frequencies in {reference}")
    labels, actual = rows(result)
    if labels != header or len(actual) != len(expected):
        raise ValueError(f"Wrong columns or row count in {result}")
    for row, ref in zip(actual, expected):
        if len(row) != len(header) or row[0] != ref[0]:
            raise ValueError(f"Unexpected shape or sample index in {result}")

    if case == "spheres":
        errors = [abs(x / y - 1) for row, ref in zip(actual, expected)
                  for x, y in zip(row[1:], ref[1:])]
        analytical_pf = [1.230518, -0.4945668, -0.4945668, 2.431543]
        calculated_pf = [x * 1e12 for row in actual for x in row[1:]]
        physical_error = max(abs(x / y - 1) for x, y in zip(calculated_pf, analytical_pf))
        # A different mesh changes the discretized solution and its regression value.
        if (not refined and max(errors) > 1e-5) or physical_error > 0.04:
            raise ValueError(f"Capacitance regression failed: {max(errors)=}, {physical_error=}")
        return {"max_relative_C_error_vs_upstream": max(errors),
                "max_relative_C_error_vs_analytic": physical_error}

    def phasor(row, index):
        return cmath.rect(10 ** (row[index] / 20), math.radians(row[index + 1]))

    error = max(abs(phasor(row, i) - phasor(ref, i)) for i in range(1, len(header), 2)
                for row, ref in zip(actual, expected))
    if error > 5e-4:
        raise ValueError(f"Maximum absolute complex S error {error} exceeds 0.0005")
    metrics = {"max_absolute_complex_S_error_vs_upstream": error}
    if case == "cpw":
        # Test even the weak pickups near -60 dB, where an absolute tolerance alone is too loose.
        relative = max(abs(phasor(row, i) / phasor(ref, i) - 1) for i in range(1, len(header), 2)
                       for row, ref in zip(actual, expected))
        if relative > 0.01:
            raise ValueError(f"Maximum relative complex S error {relative} exceeds 1%")
        metrics["max_relative_complex_S_error_vs_upstream"] = relative
    return metrics


def validate_transmon(reference, postpro, git_tag):
    # Refinement indicators changed between the packaged release and the pinned CUDA build.
    revision = git_tag.split("-g")[-1]
    with reference.open() as stream:
        refs = {(int(row["level"]), int(row["mode"])): row for row in csv.DictReader(stream)
                if row["revision"] == revision}
    if len(refs) != 6:
        raise ValueError(f"Missing three-level transmon reference for Palace {git_tag}")

    levels = []
    max_error = 0
    for level, subdir in enumerate(("iteration1", "iteration2", "."), start=1):
        stage = postpro / subdir
        metadata = json.loads((stage / "palace.json").read_text())
        problem = metadata["Problem"]
        labels, eig = rows(stage / "eig.csv")
        required = ["m", "Re{f} (GHz)", "Im{f} (GHz)", "Q", "Error (Bkwd.)", "Error (Abs.)"]
        # Palace can report additional converged eigenpairs beyond the two requested.
        if labels != required or [row[0] for row in eig[:2]] != [1, 2]:
            raise ValueError(f"Expected two ordered eigenmodes in {stage}")
        labels, indicators = rows(stage / "error-indicators.csv")
        if len(indicators) != 1 or labels[0] != "Norm":
            raise ValueError(f"Missing error-indicator norm in {stage}")
        norm = indicators[0][0]
        ndof = problem["DegreesOfFreedom"]
        if levels and (ndof <= levels[-1]["dof"] or norm >= levels[-1]["indicator_norm"]):
            raise ValueError(f"Expected higher mesh DOF and a lower indicator norm in {stage}")

        modes = []
        for mode, frequency, imaginary, q, backward, _ in eig[:2]:
            ref = refs[level, int(mode)]
            values = {"frequency_GHz": frequency, "imaginary_GHz": imaginary, "Q": q,
                      "indicator_norm": norm}
            error = max(abs(value / float(ref[key]) - 1) for key, value in values.items())
            if error > 0.01 or not 0 <= backward <= 1e-8:
                raise ValueError(f"Transmon level {level} mode {mode:g}: {error=}, {backward=}")
            max_error = max(max_error, error)
            modes.append({"frequency_GHz": frequency, "imaginary_GHz": imaginary, "Q": q,
                          "backward_error": backward})
        levels.append({
            "level": level, "elements": problem["MeshElements"], "dof": ndof,
            "cumulative_wall_s": metadata["ElapsedTime"]["Durations"]["Total"],
            "peak_host_mib_to_date": metadata["PeakNodeMemoryMegabytes"]["Max"],
            "indicator_norm": norm, "modes": modes,
        })
    return {"amr_levels": levels, "max_relative_error_vs_transmon_reference": max_error}


def run_case(args, palace, source, output):
    print(f"Writing {args.case} results to {output}", flush=True)
    output.mkdir(parents=True, exist_ok=False)

    deck, mesh_name, _, _ = CASES[args.case]
    mesh = f"mesh/{mesh_name}"
    case_path = source / "examples" / args.case
    (output / "mesh").mkdir()
    shutil.copyfile(case_path / mesh, output / mesh)
    # These pinned upstream inputs use // line comments in otherwise standard JSON.
    config = json.loads(re.sub(r"//[^\n]*", "", (case_path / deck).read_text()))
    if args.refine_spheres:
        config["Model"]["Refinement"] = {"UniformLevels": 1}
        config["Solver"]["Electrostatic"]["Save"] = 0
    if args.case == "cpw":
        # Compare a bounded multiport sweep with identical coarse solvers on both builds.
        config["Solver"]["Driven"] = {"Samples": [{"Type": "Point", "Freq": CPW_GHZ}]}
        config["Solver"]["Linear"]["Type"] = "STRUMPACK"
    if args.backend:
        config["Solver"]["Backend"] = args.backend
    config["Problem"]["Output"] = "postpro"
    config["Solver"]["Device"] = args.device
    (output / deck).write_text(json.dumps(config, indent=2) + "\n")

    env = dict(os.environ, OMP_NUM_THREADS=str(args.threads), OPENBLAS_NUM_THREADS="1")
    if "BUILD_WORKING_DIRECTORY" in env:
        env["BUILD_WORKING_DIRECTORY"] = str(output)
        env.setdefault("RUNFILES_DIR", str(Path.cwd().parent))
    if args.unpack_launcher and not args.palace:
        # First use extracts the Bazel-built bundle. Exclude that one-time cost from solve time.
        with (output / "solver-version.log").open("w") as version:
            subprocess.run([str(palace), "--version"], cwd=output, env=env, check=True,
                           stdout=version, stderr=subprocess.STDOUT)
    started = time.monotonic()
    logfile = output / "solver.log"
    with logfile.open("w") as log:
        command = [str(palace)]
        if args.ranks > 1:
            command.extend(["-np", str(args.ranks)])
        subprocess.run([*command, deck], cwd=output, env=env, check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    return time.monotonic() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--source-marker", type=Path, required=True,
                        help="path to examples/spheres/spheres.json in the pinned Palace source")
    parser.add_argument("--transmon-reference", type=Path, help=argparse.SUPPRESS,
                        default=Path(__file__).with_name("transmon_reference.csv"))
    parser.add_argument("--check-existing", action="store_true",
                        help="read and validate a completed run directory without rerunning")
    parser.add_argument("--unpack-launcher", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cpu-launcher", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--gpu-launcher", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--palace", type=Path, help="override the device's default Palace launcher")
    parser.add_argument("--output", type=Path, required=True, help="new run directory")
    parser.add_argument("--device", choices=("CPU", "GPU"), default="CPU")
    parser.add_argument("--threads", type=int, default=1, help="OpenMP threads per MPI rank")
    parser.add_argument("--ranks", type=int, default=1, help="MPI ranks")
    parser.add_argument("--backend", help="set libCEED backend, e.g. /gpu/cuda/shared")
    parser.add_argument("--refine-spheres", action="store_true",
                        help="uniformly refine spheres once and skip field files for scaling tests")
    args = parser.parse_args()
    if args.refine_spheres and args.case != "spheres":
        parser.error("--refine-spheres applies only to the spheres case")
    if args.ranks < 1:
        parser.error("--ranks must be positive")
    if args.threads < 1:
        parser.error("--threads must be positive")

    # Keep the Bazel executable path in its runfiles tree so its launcher can find its dependencies.
    default_launcher = args.gpu_launcher if args.device == "GPU" else args.cpu_launcher
    working = Path(os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd()))
    if args.palace:
        palace = (working / args.palace).absolute()
    elif default_launcher:
        palace = default_launcher.absolute()
    elif args.check_existing:
        palace = None
    elif args.device == "GPU" and args.cpu_launcher:
        parser.error("use //examples:benchmark_gpu for a source-built CUDA solver")
    else:
        parser.error("supply the path to a solver executable with --palace")
    source = args.source_marker.absolute().parents[2]
    output = (working / args.output).resolve()
    elapsed = None if args.check_existing else run_case(args, palace, source, output)
    logfile = output / "solver.log"
    postpro = output / "postpro"
    meta = json.loads((postpro / "palace.json").read_text())
    log_text = logfile.read_text()
    iterations = [int(n) for n in re.findall(r"(?:PCG|GMRES) solver converged in (\d+)", log_text)]
    _, _, reference_dir, solve_count = CASES[args.case]
    if solve_count is not None and len(iterations) != solve_count:
        raise ValueError(f"Missing explicit linear convergence reports in {logfile}")
    device = re.search(r"^Device configuration: (.+)$", log_text, re.MULTILINE)
    if not device or ("cuda" in device[1].lower()) != (args.device == "GPU"):
        raise ValueError(f"Unexpected MFEM device for requested {args.device}; see {logfile}")
    backend = re.search(r"^libCEED backend: (.+)$", log_text, re.MULTILINE)
    family = "/gpu/cuda" if args.device == "GPU" else "/cpu"
    if not backend or not (backend[1] == family or backend[1].startswith(family + "/")):
        raise ValueError(f"Expected a {family} libCEED backend in {logfile}")
    if args.backend and backend[1] != args.backend:
        raise ValueError(f"Expected libCEED backend {args.backend!r}, got {backend[1]!r}")
    # Palace omits OpenMPThreads for builds compiled without OpenMP.
    omp_threads = meta["Problem"].get("OpenMPThreads")
    if (omp_threads or 1) != args.threads or meta["Problem"]["MPISize"] != args.ranks:
        raise ValueError(f"Unexpected MPI rank or OpenMP thread count in {logfile}")
    if args.case == "transmon":
        if "Completed 2 iterations of adaptive mesh refinement" not in log_text:
            raise ValueError(f"Missing the two completed refinement steps in {logfile}")
        metrics = validate_transmon(args.transmon_reference, postpro, meta["GitTag"])
    else:
        csv_name = "terminal-C.csv" if args.case == "spheres" else "port-S.csv"
        reference = source / "test/data/regression/ref" / reference_dir / csv_name
        if args.case == "spheres":
            resolved = json.loads((postpro / "spheres_resolved.json").read_text())
            levels = resolved["Model"]["Refinement"]["UniformLevels"]
            if levels != int(args.refine_spheres):
                raise ValueError(f"Expected {int(args.refine_spheres)} uniform refinements, "
                                 f"but Palace recorded {levels} in {postpro}")
        metrics = validate(args.case, reference, postpro / csv_name, refined=args.refine_spheres)
    summary = {
        "case": args.case, "uniform_refinements": int(args.refine_spheres),
        "device": device[1], "backend": backend[1], "palace_git": meta["GitTag"],
        "omp_threads": omp_threads, "mpi_ranks": meta["Problem"]["MPISize"],
        "dof": meta["Problem"]["DegreesOfFreedom"], "elements": meta["Problem"]["MeshElements"],
        "elapsed_wall_s": elapsed, "palace_total_s": meta["ElapsedTime"]["Durations"]["Total"],
        "peak_host_mib": meta["PeakNodeMemoryMegabytes"]["Max"], "krylov_iterations": iterations,
        **metrics,
    }
    report = json.dumps(summary, indent=2)
    if not args.check_existing:
        (output / "summary.json").write_text(report + "\n")
    print(report)


if __name__ == "__main__":
    main()
