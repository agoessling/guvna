import tempfile
import unittest
from pathlib import Path

import meshio
import numpy as np

from viewer.fields import Snapshot, section


class FieldSectionTest(unittest.TestCase):
    def test_complex_components_interpolated_before_magnitude(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "part.vtu"
            points = np.array([[0., 0, 0], [1., 0, 0], [0., 1, 0], [0., 0, 1]])
            real = np.zeros((4, 3))
            real[:, 1] = 1 - 2 * points[:, 0]
            imag = np.zeros_like(real)
            imag[:, 2] = 0.25
            meshio.write_points_cells(
                path, points, [("tetra", np.array([[0, 1, 2, 3]]))],
                point_data={"E_real": real, "E_imag": imag},
                cell_data={"attribute": [np.array([7])]},
            )
            result = section(Snapshot(1, 8., (path,)), 1000, 0, 500, False)
            self.assertTrue(result["faces"])
            self.assertEqual(set(result["materials"]), {7})
            np.testing.assert_allclose(result["values"], 0.25)
            np.testing.assert_allclose(np.array(result["points"])[:, 0], 500)
            signed = section(Snapshot(1, 8., (path,)), 1000, 0, 500, False, "z")
            pairs = np.array(signed["values"])
            np.testing.assert_allclose(pairs[:, 0], 0)
            np.testing.assert_allclose(pairs[:, 1], 0.25)

    def test_surface_traces_and_shared_partition_face(self):
        from viewer.fields import surface

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = [[0., 0, 0], [1., 0, 0], [0., 1, 0]]

            def write(name, points, cells, tag, quantity, value):
                field = np.tile([value, 0., 0.], (len(points), 1))
                path = root / name
                meshio.write_points_cells(
                    path, np.array(points), cells,
                    point_data={quantity + "_real": field, quantity + "_imag": field * 0},
                    cell_data={"attribute": [np.array([tag])]},
                )
                return path

            tetra = [("tetra", [[0, 1, 2, 3]])]
            lower = write("lower.vtu", base + [[0., 0, -1]], tetra, 1, "E", 2.)
            upper = write("upper.vtu", base + [[0., 0, 1]], tetra, 2, "E", 5.)
            wall = write("boundary.vtu", base, [("triangle", [[0, 1, 2]])], 9, "J_s", 3.)
            snapshot = Snapshot(1, 8., (lower, upper), (wall,), True)
            for side, amplitude in [(1, 2.), (2, 5.)]:
                result = surface(snapshot, 1., "E", side)
                self.assertEqual(len(result["faces"]), 4)
                self.assertEqual(result["materials"].count(9), 1)
                np.testing.assert_allclose(result["values"], amplitude)
            signed = surface(snapshot, 1., "E", 2, "x")
            pairs = np.array(signed["values"])
            np.testing.assert_allclose(pairs[:, 0], 5.)
            np.testing.assert_allclose(pairs[:, 1], 0.)
            result = surface(snapshot, 1., "J_s")
            self.assertEqual(result["materials"], [9])
            np.testing.assert_allclose(result["values"], 3.)

            # A face shared by MPI pieces of the same material is internal to its skin.
            joined = write("joined.vtu", base + [[0., 0, 1]], tetra, 1, "E", 2.)
            result = surface(Snapshot(1, 8., (lower, joined)), 1., "E", 1)
            self.assertEqual(len(result["faces"]), 6)


if __name__ == "__main__":
    unittest.main()
