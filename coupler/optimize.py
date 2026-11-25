"""Run and replay a bounded COBYQA experiment on the archived taper family."""

import argparse
from dataclasses import replace
import fcntl
import json
import os
from pathlib import Path
from shutil import disk_usage
import time

import numpy as np
import scipy
from scipy.optimize import NonlinearConstraint, minimize

from design_study import Design, read_samples, simulate
from results import write_json
from taper_mesh import GapMesh


# Start gap, end gap, mean width, end width minus start width (mm).
LOW = np.array([0.10, 1.4, 0.60, -0.4])
HIGH = np.array([0.80, 3.4, 1.15, 0.4])


class BudgetReached(Exception):
    pass


def dimensions(d):
    end = d.width if d.end_width is None else d.end_width
    return np.array([d.gap, d.end_gap, (end + d.width) / 2, end - d.width])


def with_dimensions(base, values):
    a, b, mean, change = values
    return replace(base, gap=round(a, 8), end_gap=round(b, 8), width=round(mean - change / 2, 8),
                   end_width=round(mean + change / 2, 8))


def solve_search(base, seed_score, response, budget):
    def constraints(x):
        # All three frequency-dependent inequalities share one physical simulation.
        c, d = response(with_dimensions(base, LOW + x[:4] * (HIGH - LOW)))
        t = x[4] * 10
        return np.concatenate((t - (c - 20), t + (c - 20), t + d - 30))

    normalized = (dimensions(base) - LOW) / (HIGH - LOW)
    start = np.append(normalized, seed_score / 10)
    try:
        result = minimize(lambda x: 10 * x[4], start, method="COBYQA",
                          bounds=[(0, 1)] * 4 + [(0, np.inf)],
                          constraints=NonlinearConstraint(constraints, 0, np.inf),
                          options=dict(initial_tr_radius=0.12, final_tr_radius=0.002,
                                       maxfev=4 * budget + 20))
    except BudgetReached:
        return "Geometry budget reached"
    return str(result.message)


def validation_grid(*curves):
    # Include both designs' limiting samples and one adjacent sample on either side.
    freqs = {0.5, 12.0}
    for curve in curves:
        c, d = np.array(curve)[:, 1:3].T
        for i in (c.argmin(), c.argmax(), d.argmin()):
            for j in range(max(i - 1, 0), min(i + 2, len(curve))):
                freqs.add(curve[j][0])
    return sorted(freqs)


def atomic_json(path, data):
    temp = path.with_suffix(".tmp")
    write_json(temp, data)
    temp.replace(path)


def study(root, args):
    fast = args.mesh == "gap8"
    prefix = "cobyqa-gap8" if fast else "cobyqa"
    plan_path = root / f"{prefix}-plan.json"
    settings = dict(method="COBYQA", version=1, scipy=scipy.__version__, budget=args.budget,
                    lower_mm=LOW.tolist(), upper_mm=HIGH.tolist())
    if fast:
        settings["mesh"] = "gap8"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        if plan != dict(settings, seed=plan["seed"]):
            raise ValueError(f"Settings differ from {plan_path}")
    else:
        pool = []
        for path in root.glob("[0-9]*-*/design.json"):
            r = json.loads(path.read_text())
            x = dimensions(Design(**r["design"]))
            if (r.get("gap_refinement") == 1 and not r.get("spot_ghz")
                    and not r["name"].endswith("-mesh-check")
                    and np.all((LOW <= x) & (x <= HIGH))):
                pool.append(r)
        if not pool:
            raise ValueError("Run a full-band, facing-edge mesh baseline in the study first")
        plan = dict(settings, seed=min(pool, key=lambda r: r["metrics"]["score"])["name"])
        atomic_json(plan_path, plan)

    seed = json.loads((root / plan["seed"] / "design.json").read_text())
    base = Design(**seed["design"])
    count = 0
    seconds = 0
    cache = {}

    def publish(name, parent, reason, design, info, frequencies=None):
        path = root / name / "design.json"
        if path.exists():
            record = json.loads(path.read_text())
            if (Design(**record["design"]) != design or record["parent"] != parent
                    or record.get("optimizer") != info or record.get("spot_ghz") != frequencies):
                raise ValueError(f"Replay differs from {path}")
            return record
        if (root / "PAUSE").exists() or disk_usage(root).free < args.reserve_gib * 1024**3:
            raise SystemExit("Paused between designs. Resume with the same command.")
        temp = root / ("." + name)
        if temp.exists():
            temp.rename(root / f".{name}.interrupted-{time.time_ns()}")
        details = {"optimizer": info}
        mesh = None
        if fast and frequencies is None:
            mesh = GapMesh.eight_cells(design)
            details.update(gap_mesh_label="8 graded gap cells", half_gap_caps_mm=mesh.caps)
        return simulate(root, name, parent, reason, design, args.generator, args.solver,
                        frequencies is None, 1 if frequencies is None else 2,
                        details=details, frequencies=frequencies, gap_mesh=mesh)

    def values(name):
        return np.array(read_samples(root / name))[:, 1:3].T

    if fast:
        original = seed["name"]
        seed = publish(prefix + "-seed", original, "Re-evaluate the seed on eight gap cells.",
                       base, dict(method="COBYQA", phase="seed", generation=0, seed=original))
    best = seed
    cache[with_dimensions(base, dimensions(base))] = values(seed["name"])

    def response(design):
        nonlocal best, count, seconds
        if design in cache:
            return cache[design]
        if count >= args.budget:
            raise BudgetReached()
        count += 1
        generation = best.get("optimizer", {}).get("generation", 0) + 1
        name = f"{prefix}-{count:03}"
        reason = (f"Gap {design.gap:.4f} → {design.end_gap:.4f} mm, "
                  f"width {design.width:.4f} → {design.end_width:.4f} mm.")
        info = dict(method="COBYQA", phase="screen", evaluation=count, generation=generation,
                    seed=seed["name"], budget=args.budget)
        record = publish(name, best["name"], reason, design, info)
        seconds += record["wall_s"]
        if record["metrics"]["score"] < best["metrics"]["score"]:
            best = record
        cache[design] = values(name)
        return cache[design]

    stop = solve_search(base, seed["metrics"]["score"], response, args.budget)
    grid = validation_grid(read_samples(root / seed["name"]), read_samples(root / best["name"]))
    checks = []
    scores = []
    for role, source in (("seed", seed), ("winner", best)):
        if role == "winner" and source == seed:
            break
        info = dict(method="COBYQA", phase="validation", seed=seed["name"])
        record = publish(prefix + "-check-" + role, source["name"],
                         "Direct solves near both designs' extrema, halved gap pitch.",
                         Design(**source["design"]), info, grid)
        checks.append(record["name"])
        scores.append(record["metrics"]["score"])
    summary = dict(seed=seed["name"], winner=best["name"], stop=stop, evaluations=count,
                   screen_wall_s=seconds, validation=checks, validation_ghz=grid,
                   band_gain_db=seed["metrics"]["score"] - best["metrics"]["score"],
                   validation_gain_db=scores[0] - scores[-1])
    atomic_json(root / f"{prefix}-result.json", summary)
    print(summary, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mesh", choices=("standard", "gap8"), default="standard")
    parser.add_argument("--budget", type=int, default=30)
    parser.add_argument("--reserve-gib", type=int, default=24)
    parser.add_argument("--generator", required=True, type=Path)
    parser.add_argument("--solver", required=True, type=Path)
    args = parser.parse_args()
    if min(args.budget, args.reserve_gib) < 1:
        parser.error("budget and reserve must be positive")
    root = (Path(os.environ.get("BUILD_WORKING_DIRECTORY", ".")) / args.output).resolve()
    args.generator = args.generator.absolute()
    args.solver = args.solver.absolute()
    with (root / ".study.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        study(root, args)


if __name__ == "__main__":
    main()
