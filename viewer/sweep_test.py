from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from viewer.inputs import Input
from viewer.sweep import sweep


class SweepTest(unittest.TestCase):
    def test_native_columns_and_partial_samples(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = Input("run", root, "test", "test")
            self.assertEqual(sweep(run), [])
            (root / "palace.json").write_text('{"Problem":{"Output":"archive"}}')
            output = root / "archive"
            output.mkdir()
            self.assertEqual(sweep(run), [])
            (output / "port-S.csv").write_text(
                " f (GHz), |S[10][2]| (dB), arg(S[10][2]) (deg.), |S[1][5]| (dB)\n"
                "2.0, -9.125, -137.7, \n"
                "0.1, -inf, nan, -4\n")
            self.assertEqual(sweep(run), [
                dict(port=10, drive=2, samples=[[0.1, "-inf", None], [2.0, -9.125, -137.7]]),
                dict(port=1, drive=5, samples=[[0.1, -4.0, None]]),
            ])
            self.assertEqual(sweep(Input("case", root / "palace.json", "deck", "deck")), [])


if __name__ == "__main__":
    unittest.main()
