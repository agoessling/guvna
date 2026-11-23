"""Exercise a curved, mixed-port upstream model through the ordinary viewer input path."""

from pathlib import Path
import unittest

from python.runfiles import runfiles
from viewer.inputs import resolve_inputs
from viewer.scene import load_scene


class CoaxialTest(unittest.TestCase):
    def test_explicit_deck_and_tagged_mesh(self):
        src = "palace_examples/examples/coaxial/coaxial_lumped_wave.json"
        path = Path(runfiles.Create().Rlocation(src, source_repo=""))
        source, = resolve_inputs([("case", path)], cwd=path.parent)
        scene = load_scene(*source.files().load())
        model = scene["geometry"]
        self.assertTrue(model["mesh"]["corner_preview"])
        self.assertAlmostEqual(model["bounds_mm"][1][2] - model["bounds_mm"][0][2], 40)
        self.assertEqual(scene["regions"], [])
        ports = {c["type"]: c["settings"] for g in scene["groups"]
                 for c in g.get("conditions", []) if c["type"].endswith("Port")}
        self.assertEqual(ports["LumpedPort"]["R"], 100)
        self.assertEqual(ports["WavePort"]["Index"], 2)


if __name__ == "__main__":
    unittest.main()
