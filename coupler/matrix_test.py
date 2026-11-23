#!/usr/bin/env python3
"""A reciprocal coupon alone cannot detect a swapped Touchstone row and column."""

import csv
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from results import max_singular_value, read_matrices, write_touchstone


class MatrixTest(unittest.TestCase):
    def test_asymmetric_export(self):
        # Palace writes consecutive excitations (columns); four-port Touchstone writes rows.
        data = {"f (GHz)": 2.0}
        for drive in range(1, 5):
            for receive in range(1, 5):
                magnitude = (10 * receive + drive) / 100
                data[f"|S[{receive}][{drive}]| (dB)"] = 20 * math.log10(magnitude)
                data[f"arg(S[{receive}][{drive}]) (deg.)"] = 90
        with TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "port-S.csv"
            with csv_path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(data))
                writer.writeheader()
                writer.writerow(data)
            matrices = read_matrices(csv_path, [2.0])
            output = Path(tmp) / "model.s4p"
            write_touchstone(output, [2.0], matrices)
            rows = [s.split() for s in output.read_text().splitlines() if s[0] not in "!#"]
        self.assertEqual(float(rows[0].pop(0)), 2.0)
        self.assertEqual(len(rows), 4)
        for receive, row in enumerate(rows, 1):
            self.assertEqual(len(row), 8)
            for drive in range(1, 5):
                re, im = map(float, row[2 * drive - 2:2 * drive])
                self.assertAlmostEqual(re, 0.0)
                self.assertAlmostEqual(im, (10 * receive + drive) / 100)

    def test_coherent_passivity(self):
        # Unit output norm per column still allows a gain of two for equal-phase inputs.
        self.assertAlmostEqual(max_singular_value([[0.5j] * 4 for _ in range(4)]), 2.0)
        identity = [[float(i == j) for j in range(4)] for i in range(4)]
        self.assertAlmostEqual(max_singular_value(identity), 1.0)


if __name__ == "__main__":
    unittest.main()
