import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import meshio
import numpy as np

from viewer.fields import Snapshot, surface
from viewer.inputs import resolve_inputs
from viewer.stages import Stage, read_stage, stages


class MeshStagesTest(unittest.TestCase):
    def test_restart_order_keeps_local_iteration_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "palace.json").write_text('{"Model":{"Mesh":"model.msh"}}')
            (root / "model.msh").touch()
            names = ["first", "restart"]
            (root / "mesh-stages.json").write_text(json.dumps({"outputs": names}))
            for name, cells in zip(names, (10, 20)):
                output = root / name
                (output / "paraview" / "driven").mkdir(parents=True)
                stats = dict(Iteration=2, MeshElements=cells, DegreesOfFreedom=4 * cells)
                (output / "palace.json").write_text(json.dumps({"Problem": stats}))
            source, = resolve_inputs([("run", root)], root)
            with patch("viewer.stages.pieces", return_value=(Path("example.vtu"),)):
                result = stages(source)
            self.assertEqual([(i, s.directory.name, s.cells) for i, s in result.items()],
                             [(1, "first", 10), (2, "restart", 20)])

    def test_hanging_face_across_pieces_and_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "palace.json").write_text('{"Model":{"Mesh":"input.msh","L0":0.01}}')
            (root / "input.msh").touch()
            source, = resolve_inputs([("run", root)], root)

            def brick(name, x0, x1, y0, y1):
                points = [[x, y, z] for z in (0., 1.) for x, y in
                          ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
                path = root / name
                meshio.write_points_cells(path, np.array(points), [("hexahedron", [range(8)])],
                                          point_data={"E_real": np.ones((8, 3)),
                                                      "E_imag": np.zeros((8, 3))},
                                          cell_data={"attribute": [np.array([7])]})
                return path

            parts = (brick("left.vtu", 0, 1, 0, 1), brick("bottom.vtu", 1, 2, 0, .5),
                     brick("top.vtu", 1, 2, .5, 1))
            stage = Stage(2, root, 3, 30, None, parts, ())
            mesh = read_stage(stage, source)
            group, = mesh["groups"]
            self.assertEqual(len(group["cells"]), 3)
            self.assertEqual(group["tag"], 7)
            self.assertEqual(len(group["skin"]), 13)
            xyz = np.array(mesh["points"])
            for face in group["skin"]:
                self.assertFalse(np.all(xyz[list(face), 0] == 10))
            np.testing.assert_allclose(xyz.max(axis=0), [20, 10, 10])

            coating = surface(Snapshot(1, 1., parts), 10., "E", domain=7)
            triangles = np.array(coating["points"])[coating["faces"]]
            self.assertEqual(len(triangles), 26)
            self.assertFalse(np.any(np.all(triangles[:, :, 0] == 10., axis=1)))


if __name__ == "__main__":
    unittest.main()
