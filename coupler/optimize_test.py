"""Exercise the real optimizer, history publication and restart on a cheap known response."""

from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from optimize import Design, dimensions, study
from results import write_json


class OptimizerTest(unittest.TestCase):
    def test_restart_budget_parent_and_common_validation_grid(self):
        with TemporaryDirectory() as path:
            root = Path(path)
            d = Design(width=1.1, end_gap=2.2)
            args = SimpleNamespace(mesh="standard", budget=18, reserve_gib=1,
                                   generator=None, solver=None)
            radii = np.linspace(0, 1, 100)

            def response(design):
                gap, end, mean, delta = dimensions(design)
                err = (mean - 0.9)**2 + (gap - 0.4)**2 + (end - 2.1)**2 + (delta - 0.2)**2
                return 20 + err * radii, 29 - 10 * err * (1 - radii)

            def sample(path):
                design = Design(**json.loads((path / "design.json").read_text())["design"])
                c, direct = response(design)
                return list(zip(0.5 + 11.5 * radii, c, direct, radii, radii))

            def publish(root, name, parent, reason, design, gen, solver, adaptive, refinement,
                        details=None, frequencies=None, gap_mesh=None):
                dest = root / name
                dest.mkdir()
                c, direct = response(design)
                score = float(max(max(abs(c - 20)), max(30 - direct)))
                r = dict(name=name, parent=parent, design=asdict(design), metrics=dict(score=score),
                         gap_refinement=refinement, wall_s=1, **(details or {}))
                if frequencies:
                    r["spot_ghz"] = frequencies
                write_json(dest / "design.json", r)
                return r

            seed = publish(root, "06-seed", "", "", d, None, None, True, 1)
            with patch("optimize.read_samples", sample), patch("optimize.simulate", publish):
                study(root, args)
            result = json.loads((root / "cobyqa-result.json").read_text())
            self.assertEqual(result["evaluations"], args.budget)
            self.assertEqual(len(result["validation"]), 2)
            best, depth = seed, 0
            for i in range(1, args.budget + 1):
                r = json.loads((root / f"cobyqa-{i:03}/design.json").read_text())
                self.assertEqual(r["parent"], best["name"])
                self.assertEqual(r["optimizer"]["generation"], depth + 1)
                if r["metrics"]["score"] < best["metrics"]["score"]:
                    best, depth = r, depth + 1
            self.assertEqual(result["winner"], best["name"])
            self.assertLess(best["metrics"]["score"], seed["metrics"]["score"])
            for name in result["validation"]:
                r = json.loads((root / name / "design.json").read_text())
                self.assertEqual(r["spot_ghz"], result["validation_ghz"])
                self.assertEqual(r["gap_refinement"], 2)
            with patch("optimize.read_samples", sample), patch("optimize.simulate") as solver:
                study(root, args)
                solver.assert_not_called()
            self.assertEqual(json.loads((root / "cobyqa-result.json").read_text()), result)
            args.mesh = "gap8"
            with patch("optimize.read_samples", sample), patch("optimize.simulate", publish):
                study(root, args)
            fast = json.loads((root / "cobyqa-gap8-result.json").read_text())
            self.assertEqual(fast["seed"], "cobyqa-gap8-seed")
            first = json.loads((root / "cobyqa-gap8-001/design.json").read_text())
            self.assertEqual(first["parent"], fast["seed"])
            self.assertEqual(len(first["half_gap_caps_mm"]), 4)


if __name__ == "__main__":
    unittest.main()
