#!/usr/bin/env python3
"""Check a tapered mesh against its uniform seed at every longitudinal layer."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from design_study import Design
from taper_mesh import GapMesh, shape_mesh


def layers(path):
    rows = path.read_text().splitlines()
    nodes = rows[rows.index("$Nodes") + 2:rows.index("$EndNodes")]
    result = {}
    for line in nodes:
        _, x, y, z = map(float, line.split())
        result.setdefault((round(x, 9), round(z, 9)), []).append(y)
    return {k: sorted(v) for k, v in result.items()}


class TaperTest(unittest.TestCase):
    def test_gap_width_walls_ports_and_monotonicity(self):
        d = Design(length=8, end_gap=2.2, end_width=1.35, power=1.5)
        with tempfile.TemporaryDirectory() as name:
            run = Path(name)
            policy = GapMesh.for_design(d)
            subprocess.run([GENERATOR, "--output", name, "--refinement", "trace-edges",
                            "--gap-cells", str(policy.intervals)],
                           check=True, stdout=subprocess.DEVNULL)
            meta = json.loads((run / "geometry.json").read_text())
            mesh = run / "model.msh"
            before = layers(mesh)
            shape_mesh(run, meta, d, policy)
            after = layers(mesh)
            for (x, z), old in before.items():
                new = after[x, z]
                self.assertEqual(len(old), len(new))
                self.assertTrue(all(a < b for a, b in zip(new, new[1:])))
                for a, b in zip(old, new):
                    if x == 0 or abs(a) == max(old):
                        self.assertAlmostEqual(a, b)
                    if abs(abs(a) - d.gap / 2) < 1e-8:
                        gap = d.gap + (d.end_gap - d.gap) * (x / d.length) ** d.power
                        self.assertAlmostEqual(abs(b), gap / 2)
                    if abs(abs(a) - (d.gap / 2 + d.width)) < 1e-8:
                        gap = d.gap + (d.end_gap - d.gap) * (x / d.length) ** d.power
                        width = d.width + (d.end_width - d.width) * (x / d.length) ** d.power
                        self.assertAlmostEqual(abs(b), gap / 2 + width)
            facing = next(r for r in meta["regions"] if r["name"] == "Facing trace edges")
            self.assertEqual(len(facing["sweeps"]), 2)
            for sweep in facing["sweeps"]:
                for x, lo, hi in sweep["sections"]:
                    row = after[round(x, 9), 0.508]
                    nodes = [y for y in row if lo - 1e-8 <= y <= hi + 1e-8]
                    self.assertEqual(len(nodes), policy.edge_cells + 1)
                    self.assertAlmostEqual(lo, nodes[0])
                    self.assertAlmostEqual(hi, nodes[-1])
                    pitches = [b - a for a, b in zip(nodes, nodes[1:])]
                    self.assertLessEqual(max(pitches), 0.055 + 1e-8)
            for port in meta["ports"]:
                gap = d.end_gap if port["index"] in (2, 4) else d.gap
                width = d.end_width if port["index"] in (2, 4) else d.width
                self.assertAlmostEqual(abs(port["center_mm"][1]), (gap + width) / 2)

    def test_eight_cells_follow_taper_without_exceeding_edge_cap(self):
        for ends in ((0.12, 2.2), (3.4, 0.1)):
            policy = GapMesh.eight_cells(Design(gap=ends[0], end_gap=ends[1]))
            self.assertEqual(policy.intervals, 8)
            for gap in ends:
                distances = policy.distances(gap / 2)
                self.assertAlmostEqual(distances[-1], gap / 2)
                self.assertLessEqual(distances[1], 0.11)
                self.assertTrue(all(b > a for a, b in zip(distances, distances[1:])))

    def test_reversed_taper_and_pitch_scaling(self):
        for factor in (1, 2):
            d = Design(gap=2.2, end_gap=0.12)
            policy = GapMesh.for_design(d, factor)
            for gap in (d.gap, 1, d.end_gap):
                distances = policy.distances(gap / 2)
                widths = [b - a for a, b in zip(distances, distances[1:])]
                self.assertAlmostEqual(sum(widths), gap / 2)
                self.assertGreater(min(widths), 0)
                self.assertLessEqual(max(widths), 0.22 / factor + 1e-9)
                self.assertLessEqual(max(widths[:policy.edge_cells]), 0.055 / factor + 1e-9)
                self.assertTrue(all(b <= 1.5*a + 1e-9 for a, b in zip(widths, widths[1:])))


if __name__ == "__main__":
    GENERATOR = str(Path(sys.argv.pop(1)).resolve())
    unittest.main()
