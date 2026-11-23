import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import meshio
from geometry import CoupledMicrostrip
from geometry.annotations import annotate_coupon
from viewer.scene import load_scene


class SceneTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "arbitrary.msh2"
        self.points = [
            [0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.],
            [0., 0., 1.], [1., 0., 1.], [1., 1., 1.], [0., 1., 1.],
        ]
        self.cells = [("hexahedron", [list(range(8))]), ("quad", [[4, 5, 6, 7]])]

    def write_mesh(self, tags, names=None):
        meshio.write_points_cells(
            self.path, self.points, self.cells, file_format="gmsh22",
            cell_data={"gmsh:physical": [[tags[0]], [tags[1]]], "gmsh:geometrical": [[87], [88]]},
            field_data=names or {},
        )

    def test_arbitrary_names_dimensions_materials_and_multiple_conditions(self):
        self.write_mesh([5, 5], {"Fused silica": [5, 3], "Terminal A": [5, 2]})
        deck = {"Model": {"Mesh": self.path.name, "L0": .01},
                "Boundaries": {"LumpedPort": [{"Index": 8, "R": 75, "Elements":
                               [{"Attributes": [5], "Direction": "+Z"}]}],
                               "Periodic": [{"DonorAttributes": [5], "ReceiverAttributes": [12]}]},
                "Domains": {"Materials": [{"Attributes": [5], "Permittivity": [4, 4, 4.2],
                                           "LossTan": .001}]}}
        scene = load_scene(self.path, deck)
        volume, port = scene["groups"]
        self.assertNotEqual(volume["key"], port["key"])
        self.assertEqual((volume["tag"], port["tag"]), (5, 5))
        self.assertEqual((volume["name"], port["name"]), ("Fused silica", "P8 · Terminal A"))
        self.assertEqual(volume["properties"], {"Permittivity": "[4, 4, 4.2]", "LossTan": "0.001"})
        self.assertEqual(port["category"], "Ports")
        self.assertEqual(port["conditions"], [
            {"type": "LumpedPort", "settings": {"Index": 8, "R": 75, "Attributes": [5],
                                                "Direction": "+Z"}},
            {"type": "Periodic", "settings": {"DonorAttributes": [5], "ReceiverAttributes": [12]}},
        ])
        self.assertEqual(scene["geometry"]["bounds_mm"][1], [10., 10., 10.])
        self.assertEqual(scene["geometry"]["mesh"]["nodes"], 8)
        self.assertEqual(scene["geometry"]["mesh"]["cells"], 1)

    def test_archive_matches_new_producer_annotations(self):
        self.write_mesh([1, 11])
        model = CoupledMicrostrip()
        archive = model.metadata()
        archive["mesh"] = {"x_intervals": 12, "y_intervals": [5, 4, 6, 4, 5],
                           "z_intervals": [3, 5]}
        original = copy.deepcopy(archive)
        legacy = load_scene(self.path, metadata=archive)
        modern = load_scene(self.path, metadata=annotate_coupon(archive, model))
        self.assertEqual(legacy, modern)
        self.assertEqual(archive, original)
        self.assertEqual([g["name"] for g in modern["groups"]], ["Substrate", "Main trace"])
        self.assertTrue(modern["groups"][1]["metallic"])
        self.assertTrue(modern["groups"][1]["visible"])
        self.assertEqual(modern["points"], self.points)
        self.assertEqual(modern["groups"][1]["cells"], [[4, 5, 6, 7]])
        self.assertEqual(modern["geometry"]["properties"]["Gap"], "0.22 mm")
        self.assertEqual(modern["groups"][0]["properties"], {"Permittivity": "3.48"})
        gap = modern["regions"][0]
        self.assertEqual((gap["axis"], gap["intervals"], gap["rule"]), ("Y", 6, "Transfinite"))
        left, right = gap["boxes"][0][1::3]
        self.assertAlmostEqual(right - left, archive["dimensions_mm"]["gap"])

    def test_unassigned_cells_do_not_inherit_elementary_tags(self):
        self.write_mesh([0, 0])
        deck = {"Model": {"Mesh": self.path.name}, "Boundaries": {"PEC": {"Attributes": [88]}},
                "Domains": {"Materials": [{"Attributes": [87], "Permittivity": 77}]}}
        scene = load_scene(self.path, deck)
        self.assertEqual(scene["geometry"]["bounds_mm"][1], [.001, .001, .001])
        vol, surf = scene["groups"]
        self.assertEqual((vol["tag"], surf["tag"]), (None, None))
        self.assertNotIn("Permittivity", vol["properties"])
        self.assertEqual(surf["conditions"], [])

    def test_material_in_the_deck_takes_precedence(self):
        self.write_mesh([8, 23], {"core": [8, 3]})
        meta = {"materials": {"core": {"relative_permittivity": 8.2, "loss_tangent": .02}}}
        deck = {"Domains": {"Materials": [{"Attributes": [8], "Permittivity": 3.3}]}}
        model = load_scene(self.path, deck, meta)
        self.assertEqual(model["groups"][0]["properties"], {"Permittivity": "3.3"})
        model = load_scene(self.path, {}, meta)
        self.assertEqual(model["groups"][0]["properties"], {})

    def test_quadratic_preview_uses_corner_indices(self):
        self.points = [
            [0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.],
            [.5, 0., 0.], [.5, .5, 0.], [0., .5, 0.],
            [0., 0., .5], [.5, 0., .5], [0., .5, .5],
        ]
        self.cells = [("tetra10", [list(range(10))]), ("triangle6", [[0, 1, 2, 4, 5, 6]])]
        self.write_mesh([91, 37])
        model = load_scene(self.path)
        self.assertTrue(model["geometry"]["mesh"]["corner_preview"])
        self.assertEqual(model["groups"][0]["cells"], [[0, 1, 2, 3]])
        self.assertEqual(model["groups"][1]["cells"], [[0, 1, 2]])

    def test_generic_annotations_survive_without_coupon_data(self):
        self.write_mesh([908, 43])
        metadata = {"model": "Window", "units": "cm", "properties": {"Series": "A"},
                    "regions": [{"name": "Inset", "axis": "X", "intervals": 5,
                                 "boxes": [[0, 0, 0, 2, 1, 1]], "rule": "Uniform"}],
                    "physical_groups": [{"tag": 43, "dimension": 2, "name": "front",
                                         "display_name": "Front window", "visible": True,
                                         "color": "#aabba0", "category": "Window",
                                         "properties": {"Finish": "Polished"}}]}
        scene = load_scene(self.path, metadata=metadata)
        self.assertEqual(scene["regions"], metadata["regions"])
        self.assertEqual(scene["geometry"]["properties"], metadata["properties"])
        self.assertEqual(scene["geometry"]["bounds_mm"][1], [10, 10, 10])
        front = scene["groups"][1]
        self.assertEqual((front["name"], front["category"]), ("Front window", "Window"))
        self.assertEqual(front["properties"], {"Finish": "Polished"})
        self.assertNotIn("conditions", front)


if __name__ == "__main__":
    unittest.main()
