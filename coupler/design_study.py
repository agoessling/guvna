#!/usr/bin/env python3
"""Screen longitudinal gap tapers in Palace and publish completed designs for inspection."""

import argparse
import csv
from dataclasses import asdict, dataclass, replace
import fcntl
import json
import math
import os
from pathlib import Path
import random
import re
from shutil import disk_usage
import signal
import subprocess
import time
from xml.etree import ElementTree

from solve import make_deck, write_json
from taper_mesh import GapMesh, shape_mesh


@dataclass(frozen=True)
class Design:
    width: float = 1.1
    gap: float = 0.22
    end_gap: float = 0.22
    power: float = 1
    cover_er: float = 1
    length: float = 100
    cells: int = 96
    end_width: float | None = None


def read_samples(run):
    samples = []
    with (run / "postpro/port-S.csv").open() as stream:
        for row in csv.DictReader(stream, skipinitialspace=True):
            f = float(row["f (GHz)"])
            ret, through, coupling, isolation = (
                -float(row[f"|S[{p}][1]| (dB)"]) for p in range(1, 5))
            if not all(map(math.isfinite, (f, ret, through, coupling, isolation))):
                raise ValueError("Incomplete port response")
            samples.append((f, coupling, isolation - coupling, ret, through))
    return samples


def measure(run, adaptive=True, frequencies=None):
    log = (run / "solver.log").read_text()
    trained = re.search(r"Adaptive sampling converged with (\d+) frequency samples", log)
    info = json.loads((run / "postpro/palace.json").read_text())
    converged = len(re.findall(r"^GMRES solver converged in", log, re.M))
    count = int(trained[1]) if trained else 0
    grid = frequencies or [0.5 + 11.5 * i / 99 for i in range(100)]
    expected = count if adaptive else len(grid)
    if not expected or info["LinearSolver"]["TotalSolves"] != expected or converged != expected:
        raise ValueError(f"Check linear and frequency sweep convergence in {run}")
    samples = read_samples(run)
    series = run / "postpro/paraview/driven/driven.pvd"
    saved = {}
    for frame in ElementTree.parse(series).iter("DataSet"):
        saved[float(frame.attrib["timestep"])] = series.parent / frame.attrib["file"]
    for f in (0.5, 12):
        header = saved[f]
        field_grid = ElementTree.parse(header)
        arrays = {a.get("Name") for a in field_grid.iter("PDataArray")}
        pieces = [header.parent / p.attrib["Source"] for p in field_grid.iter("Piece")]
        if not {"E_real", "E_imag"} <= arrays or not pieces or not all(p.is_file() for p in pieces):
            raise ValueError(f"Missing volume field at {f} GHz")
    if len(samples) != len(grid) or any(abs(row[0] - f) > 1e-6 for row, f in zip(samples, grid)):
        raise ValueError("Incomplete Palace frequency grid")
    low, high = min(s[1] for s in samples), max(s[1] for s in samples)
    worst = min(samples, key=lambda s: s[2])
    return dict(coupling_min=low, coupling_max=high, directivity_min=worst[2], worst_ghz=worst[0],
                return_loss_min=min(s[3] for s in samples),
                through_loss_max=max(s[4] for s in samples),
                score=max(abs(low - 20), abs(high - 20), 30 - worst[2]), trained=count,
                full_solves=expected)


def prepare(run, parent, reason, design, generator, adaptive, gap_refinement, env, gap_mesh=None):
    # Fix the enclosure half-width at 3.21 mm across every candidate.
    side = 3.21 - design.width - design.gap / 2
    if gap_mesh is None:
        gap_mesh = GapMesh.for_design(design, gap_refinement)
    args = [generator, "--output", run, "--refinement", "trace-edges", "--length",
            str(design.length), "--width", str(design.width), "--gap", str(design.gap),
            "--side-clearance", str(side), "--length-cells", str(design.cells),
            "--gap-cells", str(gap_mesh.intervals)]
    with (run / "mesh.log").open("w") as log:
        subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True, env=env)
    meta = json.loads((run / "geometry.json").read_text())
    shape_mesh(run, meta, design, gap_mesh)
    meta["properties"].update({"Parent design": parent, "Design change": reason})
    deck = make_deck(meta, [], [0.5, 12], 2, 1e-9)
    for port in deck["Boundaries"]["LumpedPort"]:
        port["Excitation"] = int(port["Index"] == 1)
    deck["Solver"].update(Device="GPU", Backend="/gpu/cuda/shared")
    if gap_refinement > 1 or not adaptive:
        # Smaller gap cells raise the aspect ratio. Limit Krylov storage while allowing restarts.
        deck["Solver"]["Linear"].update(MaxSize=96, MaxIts=600)
    deck["Solver"]["Driven"].update(
        Samples=[dict(Type="Linear", MinFreq=0.5, MaxFreq=12, NSample=100)])
    if adaptive:
        deck["Solver"]["Driven"].update(AdaptiveTol=1e-4, AdaptiveMaxSamples=60)
    if design.cover_er != 1:
        group = next(g for g in meta["physical_groups"] if g["name"] == "air")
        group["name"] = "cover"
        meta["materials"]["cover"] = meta["materials"].pop("air")
        mesh = run / "model.msh"
        mesh.write_text(mesh.read_text().replace('3 2 "air"', '3 2 "cover"'))
        for region in meta["regions"]:
            region["name"] = region["name"].replace("Air", "Cover")
    write_json(run / "geometry.json", meta)
    write_json(run / "palace.json", deck)
    return meta, deck


def simulate(root, name, parent, reason, design, generator, solver, adaptive, gap_refinement,
             details=None, frequencies=None, gap_mesh=None):
    final = root / name
    run = root / ("." + name)
    run.mkdir()
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               BUILD_WORKING_DIRECTORY=str(run))
    print(f"{name}: {reason}", flush=True)
    started = time.monotonic()
    meta, deck = prepare(run, parent, reason, design, generator, adaptive, gap_refinement, env,
                         gap_mesh=gap_mesh)

    if details:
        linear = deck["Solver"]["Linear"]
        linear.setdefault("MaxSize", linear["MaxIts"])
        linear["MaxIts"] = max(600, linear["MaxIts"])
    if frequencies:
        deck["Solver"]["Driven"]["Samples"] = [dict(Type="Point", Freq=frequencies)]
    if details or frequencies:
        write_json(run / "palace.json", deck)

    def archive_attempt(label):
        archived = run / label
        archived.mkdir()
        for filename in ("postpro", "palace.json", "solver.log"):
            path = run / filename
            if path.exists():
                path.rename(archived / filename)

    def launch():
        ranks = "4" if deck["Solver"]["Device"] == "CPU" else "1"
        with (run / "solver.log").open("w") as log:
            subprocess.run([solver, "-np", ranks, "palace.json"], cwd=run, env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True)

    def solve():
        try:
            launch()
        except subprocess.CalledProcessError as error:
            if not details or deck["Solver"]["Device"] != "GPU":
                raise
            log = (run / "solver.log").read_text()
            if "CeedVector has no borrowed device array" in log:
                reason = "libCEED device-array abort"
            elif frequencies and error.returncode in (-signal.SIGFPE, 128 + signal.SIGFPE):
                reason = "GPU validation arithmetic exception"
            else:
                raise
            archive_attempt("gpu-attempt")
            deck["Solver"]["Device"] = "CPU"
            deck["Solver"].pop("Backend")
            write_json(run / "palace.json", deck)
            print(f"{name}: retrying {reason} on four CPU ranks", flush=True)
            launch()

    solve()
    if adaptive and "Adaptive sampling reached maximum" in (run / "solver.log").read_text():
        archive_attempt("adaptive-attempt")
        driven = deck["Solver"]["Driven"]
        del driven["AdaptiveTol"], driven["AdaptiveMaxSamples"]
        write_json(run / "palace.json", deck)
        adaptive = False
        solve()
    stats = measure(run, adaptive, frequencies)
    record = dict(name=name, parent=parent, reason=reason, design=asdict(design), metrics=stats,
                  gap_refinement=gap_refinement, wall_s=round(time.monotonic() - started, 1))
    if details:
        record.update(details, device=deck["Solver"]["Device"])
    if frequencies:
        record["spot_ghz"] = frequencies
    write_json(run / "design.json", record)
    meta["properties"].update({
        "Coupling loss range": f'{stats["coupling_min"]:.2f} to {stats["coupling_max"]:.2f} dB',
        "Minimum directivity": f'{stats["directivity_min"]:.2f} dB at {stats["worst_ghz"]} GHz',
        "Minimum return loss": f'{stats["return_loss_min"]:.2f} dB',
        "Maximum through loss": f'{stats["through_loss_max"]:.2f} dB',
    })
    write_json(run / "geometry.json", meta)
    run.rename(final)
    print(f"Published {name}: {stats}", flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--continuous", action="store_true",
                        help="continue exploring new designs after the initial coordinate sweep")
    parser.add_argument("--reserve-gib", type=int, default=24,
                        help="pause between runs below this much free disk space")
    args = parser.parse_args()
    if args.reserve_gib < 1:
        parser.error("--reserve-gib must be positive")
    root = (Path(os.environ.get("BUILD_WORKING_DIRECTORY", ".")) / args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / ".study.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    records = []

    legacy = []
    for file in root.glob("[0-9]*-*/design.json"):
        result = json.loads(file.read_text())
        if "gap_refinement" not in result:
            legacy.append(result)
    first_index = 1 + max((int(r["name"].partition("-")[0]) for r in legacy), default=-1)

    def trial(label, parent, why, design, adaptive=True, gap_refinement=1):
        name = f"{first_index + len(records):02d}-{label}"
        archive = root / name / "design.json"
        if archive.is_file():
            record = json.loads(archive.read_text())
            if (Design(**record["design"]) != design or record["parent"] != parent
                    or record["gap_refinement"] != gap_refinement):
                raise ValueError(f"Existing design differs: {archive}")
        else:
            if (root / "PAUSE").exists() or disk_usage(root).free < args.reserve_gib * 1024**3:
                print("Paused between designs. Check PAUSE and available disk space.", flush=True)
                raise SystemExit(0)
            stale = root / ("." + name)
            if stale.exists():
                stale.rename(root / f".{name}.interrupted-{time.time_ns()}")
            record = simulate(root, name, parent, why, design,
                              args.generator.resolve(), args.solver.resolve(), adaptive,
                              gap_refinement)
        records.append(record)
        return name

    def incumbent():
        return min((r for r in records if not r["name"].endswith("-mesh-check")),
                   key=lambda r: r["metrics"]["score"])

    if legacy:
        old = min((r for r in legacy if not r["name"].endswith("-mesh-check")),
                  key=lambda r: r["metrics"]["score"])
        seed = Design(**old["design"])
        first = trial("facing-edges", old["name"], "Resolve both facing trace edges.", seed)
        trial("gap-mesh-check", first, "Halve the lateral pitch caps across the gap.", seed,
              gap_refinement=2)
    else:
        uniform = Design()
        base = trial("uniform", "None", "Uniform 100 mm reference.", uniform)
        taper = replace(uniform, end_gap=2.2)
        first = trial("linear-gap", base, "Open the gap linearly toward the far end.", taper)
        embedded = replace(taper, cover_er=3.48)
        covered = trial("dielectric-cover", first, "Equalize the upper and lower permittivity.",
                        embedded)
        narrow = replace(embedded, width=0.75)
        trial("narrower-traces", covered, "Narrow both embedded traces to improve the match.",
              narrow)
    # Older archives may already contain coordinate-search results past the initial seeds.
    # Continue their numbering and retain the measured geometry when branching the new study.
    existing = sorted(root.glob("[0-9]*-*/design.json"),
                      key=lambda p: int(p.parent.name.partition("-")[0]))
    for path in existing:
        idx = int(path.parent.name.partition("-")[0])
        if idx < first_index + len(records):
            continue
        record = json.loads(path.read_text())
        if "end_width" in record["design"] or idx != first_index + len(records):
            break
        records.append(record)

    base = incumbent()
    profile = Design(**base["design"])
    trial("width-taper", base["name"], "Widen both traces from 0.725 to 0.855 mm with the gap.",
          replace(profile, width=0.725, end_width=0.855))
    trial("width-control", base["name"], "Hold both traces at the taper's mean width, 0.790 mm.",
          replace(profile, width=0.790, end_width=None))
    for label, attribute, values in (
            ("gap-in", "gap", (0.12, 0.4, 0.65)),
            ("profile", "power", (0.65, 1.5, 2.0)),
            ("width", "width", (0.65, 0.85, 0.95)),
            ("length", "length", (80, 90, 110))):
        best = incumbent()
        parent = Design(**best["design"])
        for value in values:
            d = replace(parent, **{attribute: value})
            if attribute == "length":
                d = replace(d, cells=math.ceil(value * 0.96))
            if any(Design(**r["design"]) == d for r in records):
                continue
            trial(f"{label}-{value:g}", best["name"], f"Change {attribute} to {value:g}.", d)
    best = incumbent()
    winner = Design(**best["design"])
    trial("mesh-check", best["name"], "Double the longitudinal resolution and solve directly.",
          replace(winner, cells=2 * winner.cells), adaptive=False)

    # Alternate a local perturbation of the incumbent with periodic wider exploration.
    # Seed by iteration so interrupted jobs replay the same sequence from saved results.
    step = 0
    while args.continuous:
        step += 1
        best = incumbent()
        parent = Design(**best["design"])
        rng = random.Random(step)
        bounds = dict(gap=(0.10, 0.8), end_gap=(1.4, 3.4), width=(0.50, 1.15),
                      power=(0.6, 2.2), length=(65, 125), end_width=(0.50, 1.15))
        keys = list(bounds) if step % 4 == 0 else rng.sample(list(bounds), k=2)
        changes = {}
        for key in keys:
            low, high = bounds[key]
            value = getattr(parent, key)
            center = max(low, min(high, parent.width if value is None else value))
            radius = (high - low) / 4
            if step % 4:
                low, high = max(low, center - radius), min(high, center + radius)
            changes[key] = round(rng.uniform(low, high), 3)
        if step % 4 == 0:
            changes["cover_er"] = rng.choice([1.0, 2.2, 3.0, 3.48, 4.0])
        d = replace(parent, **changes)
        d = replace(d, cells=math.ceil(d.length * 0.96))
        if any(Design(**r["design"]) == d for r in records):
            continue
        why = ", ".join(f"{k}={v:g}" for k, v in changes.items())
        trial("taper-search", best["name"], why, d)


if __name__ == "__main__":
    main()
