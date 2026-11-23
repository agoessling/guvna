#!/usr/bin/env python3
"""Generate and solve a four-port coupled-microstrip coupon with the source-built CPU Palace."""

import argparse
import json
import math
import os
import platform
import subprocess
import time
from pathlib import Path

from results import DIRECTIVITY_PORTS, PORTS, ROLES, field_files, read_matrices, sample_diagnostics
from results import validate_solver, write_json, write_touchstone


PARAMETERS = ("length", "width", "gap", "substrate-height", "lid-clearance", "side-clearance",
              "relative-permittivity")
CELLS = ("gap-cells", "length-cells", "substrate-cells", "strip-cells", "air-cells", "side-cells")
DEFAULT_GHZ = [0.5, 0.9, 2, 4, 6, 8, 10, 10.525, 11, 12]


def make_deck(geometry, frequencies, saved, order, tol):
    indices = [p["index"] for p in geometry["ports"]]
    roles = tuple(p["role"] for p in geometry["ports"])
    legacy_roles = ("input", "through", "forward-coupled", "isolated")
    if geometry["units"] != "mm" or indices != list(PORTS) or roles not in (ROLES, legacy_roles):
        raise ValueError("Expected a mesh in mm and the documented four-port ordering")
    groups = {(g["dimension"], g["name"]): g["tag"] for g in geometry["physical_groups"]}
    ports = [{"Index": p["index"], "Excitation": p["index"], "R": 50,
              "Attributes": [p["tag"]], "Direction": p["direction"]} for p in geometry["ports"]]
    materials = []
    for name in ("substrate", "air"):
        tag = groups[3, name]
        er = geometry["materials"][name]["relative_permittivity"]
        materials.append({"Attributes": [tag], "Permittivity": er,
                          "Permeability": 1.0, "LossTan": 0.0})
    pec = [groups[2, name] for name in ("enclosure_pec", "main_trace_pec", "pickup_trace_pec")]
    return {
        "Problem": {"Type": "Driven", "Verbose": 2, "Output": "postpro"},
        "Model": {"Mesh": "model.msh", "L0": 1e-3},
        "Domains": {"Materials": materials},
        "Boundaries": {"PEC": {"Attributes": pec}, "LumpedPort": ports},
        "Solver": {
            "Order": order, "Device": "CPU",
            "Driven": {"Samples": [{"Type": "Point", "Freq": frequencies}], "Save": saved},
            "Linear": {"Type": "STRUMPACK", "KSPType": "GMRES", "Tol": tol, "MaxIts": 200},
        },
    }


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator", type=Path, required=True, help=argparse.SUPPRESS)
    parser.add_argument("--palace", type=Path, required=True, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, required=True, help="new directory for this run")
    parser.add_argument("--refinement", type=int, choices=[0, 1], default=0)
    parser.add_argument("--ranks", type=int, default=4)
    parser.add_argument("--order", type=int, choices=[1, 2, 3], default=2)
    parser.add_argument("--tolerance", type=float, default=1e-9, help="GMRES relative tolerance")
    parser.add_argument("--frequencies-ghz", type=float, nargs="+", default=DEFAULT_GHZ)
    parser.add_argument("--save-ghz", type=float, nargs="+", default=[6, 10.525])
    for parameter in PARAMETERS:
        parser.add_argument("--" + parameter, type=float, help="override the geometry model input")
    for feature in CELLS:
        parser.add_argument("--" + feature, type=int, help="override the preset mesh cell count")
    args = parser.parse_args()
    if args.ranks < 1 or not 0 < args.tolerance < 1:
        parser.error("positive MPI rank count and tolerance between 0 and 1 required")
    for values in (args.frequencies_ghz, args.save_ghz):
        if len(set(values)) != len(values) or not all(math.isfinite(f) and f > 0 for f in values):
            parser.error("frequencies must be unique, positive and finite")
        values.sort()
    if not set(args.save_ghz) <= set(args.frequencies_ghz):
        parser.error("--save-ghz must be a subset of --frequencies-ghz")
    return args


def main():
    args = arguments()
    generator, palace = args.generator.absolute(), args.palace.absolute()
    starting_dir = Path(os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd()))
    run = (starting_dir / args.output).resolve()
    run.mkdir(parents=True, exist_ok=False)
    print(f"Preparing mesh in {run}", flush=True)
    begin = time.monotonic()
    env = dict(os.environ, BUILD_WORKING_DIRECTORY=str(run), OPENBLAS_NUM_THREADS="1",
               OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
    env.setdefault("RUNFILES_DIR", str(Path.cwd().parent))
    mesh_args = [generator, "--output", str(run), "--refinement", str(args.refinement)]
    for parameter in PARAMETERS + CELLS:
        value = getattr(args, parameter.replace("-", "_"))
        if value is not None:
            mesh_args.extend(["--" + parameter, str(value)])
    with (run / "mesh.log").open("w") as log:
        subprocess.run(mesh_args,
                       cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    geometry = json.loads((run / "geometry.json").read_text())
    data = make_deck(geometry, args.frequencies_ghz, args.save_ghz, args.order, args.tolerance)
    write_json(run / "palace.json", data)
    with (run / "version.log").open("w") as log:
        subprocess.run([palace, "--version"], cwd=run, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    command = [palace, "-np", str(args.ranks), "palace.json"]
    print(f"Solving {4 * len(args.frequencies_ghz)} systems; follow {run}/solver.log", flush=True)
    start = time.monotonic()
    with (run / "solver.log").open("w") as log:
        subprocess.run(command, cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    wall_s = time.monotonic() - start
    diagnostics = validate_solver(run, args.frequencies_ghz, args.ranks)
    matrices = read_matrices(run / "postpro/port-S.csv", args.frequencies_ghz)
    diagnostics["directivity_ports"] = DIRECTIVITY_PORTS
    diagnostics["samples"] = [sample_diagnostics(f, s) for f, s in zip(args.frequencies_ghz,
                                                                       matrices, strict=True)]
    fields = field_files(run, args.save_ghz, args.ranks)
    write_touchstone(run / "coupler.s4p", args.frequencies_ghz, matrices)
    ports = [{"number": p["index"], "role": role, "reference_ohm": 50,
              "center_mm": p["center_mm"], "direction": p["direction"]}
             for p, role in zip(geometry["ports"], ROLES, strict=True)]
    result = {
        "schema_version": 1, "name": "Edge-coupled microstrip coupon",
        "geometry": "geometry.json", "mesh": "model.msh", "touchstone": "coupler.s4p",
        "ports": ports, "frequency_ghz": args.frequencies_ghz,
        "s": [[[[z.real, z.imag] for z in row] for row in matrix] for matrix in matrices],
        "fields": fields, "diagnostics": diagnostics,
        "run": {"host": platform.node(), "ranks": args.ranks, "threads_per_rank": 1,
                "refinement": args.refinement, "order": args.order, "tolerance": args.tolerance,
                "solve_wall_s": wall_s, "workflow_wall_s": time.monotonic() - begin},
    }
    write_json(run / "run.json", result)
    print(f"Wrote {run}/run.json; Palace time {wall_s:.2f} s", flush=True)


if __name__ == "__main__":
    main()
