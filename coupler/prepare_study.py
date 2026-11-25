"""Prepare Palace mesh and frequency adaptivity studies from a completed coupon."""

import argparse
import json
import math
import os
from pathlib import Path
from shutil import copyfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("destination", type=Path, help="new study directory")
    parser.add_argument("--field-ghz", type=float, default=10.525)
    parser.add_argument("--mesh-iterations", type=int, default=1)
    parser.add_argument("--adaptive-tol", type=float, default=1e-3)
    parser.add_argument("--sample-limit", type=int, default=24)
    parser.add_argument("--output-step-ghz", type=float, default=0.125)
    parser.add_argument("--band-ghz", nargs=2, type=float, metavar=("LOW", "HIGH"),
                        help="run the same linear frequency sweep at every adaptive mesh stage")
    parser.add_argument("--output-points", type=int, default=100)
    args = parser.parse_args()
    cwd = Path(os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd()))
    baseline = cwd / args.baseline
    destination = cwd / args.destination
    deck = json.loads((baseline / "palace.json").read_text())
    if args.mesh_iterations < 1 or args.sample_limit < 2:
        parser.error("use at least one refinement and two training samples")
    for value in (args.output_step_ghz, args.adaptive_tol):
        if not math.isfinite(value) or value <= 0:
            parser.error("frequency step and adaptive tolerance must be finite and positive")
    if args.band_ghz:
        low, high = args.band_ghz
        if not 0 < low < high or not math.isfinite(high) or args.output_points < 2:
            parser.error("choose an increasing positive finite band and at least two output points")
        cases = ("band",)
    else:
        samples = json.loads((baseline / "run.json").read_text())["frequency_ghz"]
        if args.field_ghz not in samples:
            parser.error("choose a saved baseline response frequency for --field-ghz")
        low, high = min(samples), max(samples)
        if low == high:
            parser.error("the baseline must span a frequency band")
        cases = ("mesh", "frequency")
    for port in deck["Boundaries"]["LumpedPort"]:
        port["Excitation"] = int(port["Index"] == 1)
    if not args.band_ghz:
        destination.mkdir(parents=True, exist_ok=False)
    for name in cases:
        case = destination if name == "band" else destination / name
        case.mkdir(parents=True, exist_ok=False)
        copyfile(baseline / deck["Model"]["Mesh"], case / "model.msh")
        copyfile(baseline / "geometry.json", case / "geometry.json")
        model = {**deck["Model"], "Mesh": "model.msh"}
        refinement = dict(model.get("Refinement", {}))
        model["Refinement"] = refinement
        solver = dict(deck["Solver"])
        driven = {"Save": [args.field_ghz]}
        solver["Driven"] = driven
        if name in ("mesh", "band"):
            mesh_tol = 0.01 if name == "band" else 1e-6
            refinement.update(MaxIts=args.mesh_iterations, Tol=mesh_tol, Nonconformal=True,
                              SaveAdaptIterations=True, SaveAdaptMesh=True)
            solver["Device"] = "CPU"
            solver.pop("Backend", None)
        else:
            refinement["MaxIts"] = 0
            solver.update(Device="GPU", Backend="/gpu/cuda/magma")
        if name in ("band", "frequency"):
            driven.update(AdaptiveTol=args.adaptive_tol, AdaptiveMaxSamples=args.sample_limit)
        if name == "band":
            driven["Samples"] = [{"Type": "Linear", "MinFreq": low, "MaxFreq": high,
                                  "NSample": args.output_points}]
            driven["Save"] = [low, high]
        elif name == "mesh":
            driven["Samples"] = [{"Type": "Point", "Freq": [args.field_ghz]}]
        else:
            count = math.floor((high - low) / args.output_step_ghz)
            grid = sorted(set(samples) | {low + i * args.output_step_ghz for i in range(count + 1)})
            driven["Samples"] = [{"Type": "Point", "Freq": grid}]
        config = {**deck, "Problem": {**deck["Problem"], "Output": "postpro"},
                  "Model": model, "Solver": solver}
        (case / "palace.json").write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    main()
