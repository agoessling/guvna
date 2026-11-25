"""Regression coverage for explicit model selection and mesh-to-metadata association."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from viewer.inputs import arguments, design_history, read_deck, resolve_inputs


class InputsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def deck(self, parent, name="palace.json", mesh="model.msh"):
        folder = self.root / parent
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text(json.dumps({"Model": {"Mesh": mesh}}))
        (folder / mesh).touch()
        return path

    def test_cli_order_names_and_ids(self):
        a = self.deck("first/repeat")
        b = self.deck("second/repeat")
        run = self.root / "middle"
        run.mkdir()
        (run / "geometry.json").write_text("{}")
        (run / "model.msh").touch()
        alias = self.root / "alias"
        alias.symlink_to(a)
        with patch.dict(os.environ, BUILD_WORKING_DIRECTORY=str(self.root)):
            items, _, _ = arguments(["--case", str(a), "--run", "middle", "--case", str(b),
                                  "--case", "alias"])
        self.assertEqual([i.path for i in items], [a, run, b])
        self.assertEqual([i.name for i in items], ["first/repeat/palace.json", "middle",
                                                   "second/repeat/palace.json"])
        reordered = resolve_inputs([("case", b), ("case", alias)], cwd=self.root)
        self.assertEqual([i.id for i in reordered], [items[2].id, items[0].id])
        self.assertEqual(items[1].files().load(), (run / "model.msh", None, {}))

    def test_json_comments_and_sidecar(self):
        deck = self.deck("run")
        deck.write_text('''{
          "Model": {"Mesh":"model.msh"}, /* block
          comment */ "url": "https://example.com/\\"/*literal*/" // line
        }''')
        self.assertEqual(read_deck(deck)["url"], 'https://example.com/"/*literal*/')
        meta = deck.parent / "geometry.json"
        meta.write_text('{"units":"mm"}')
        source, = resolve_inputs([("run", deck.parent)], cwd=self.root)
        original = source.files()
        self.assertEqual(original.load(), (deck.parent / "model.msh", read_deck(deck),
                                           {"units": "mm"}))
        self.deck("run", mesh="other.msh")
        self.assertIsNone(source.files().metadata)
        self.assertEqual(original.mesh.name, "model.msh")

    def test_relative_external_mesh_and_errors(self):
        path = self.deck("meshes", mesh="model.msh")
        (path.parent / "geometry.json").write_text("{}")
        elsewhere = self.root / "input.json"
        elsewhere.write_text('{"Model":{"Mesh":"meshes/model.msh"}}')
        source, = resolve_inputs([("case", elsewhere)], cwd=self.root)
        self.assertEqual(source.files().metadata, path.parent / "geometry.json")
        elsewhere.write_text('{"Model":{"Mesh":"gone.msh"}}')
        with self.assertRaisesRegex(ValueError, "input.json.*gone.msh"):
            source.files()
        elsewhere.write_text('{"Model": [}')
        with self.assertRaisesRegex(ValueError, "input.json.*line 1"):
            read_deck(elsewhere)
        (self.root / "empty").mkdir()
        with self.assertRaisesRegex(ValueError, "palace.json or geometry.json"):
            resolve_inputs([("run", "empty")], cwd=self.root)
        with self.assertRaisesRegex(ValueError, "existing Palace deck"):
            resolve_inputs([("case", "missing")], cwd=self.root)

    def test_explicit_mesh_file_and_unrelated_or_malformed_sidecar(self):
        sub = self.root / "meshes"
        sub.mkdir()
        mesh = sub / "coil.msh"
        mesh.touch()
        meta = self.root / "geometry.json"
        meta.write_text('{"mesh_file":"meshes/coil.msh","units":"mm"}')
        [run] = resolve_inputs([("run", self.root)], cwd=self.root)
        self.assertEqual(run.files().load(), (mesh, None, read_deck(meta)))
        case = self.root / "palace.json"
        case.write_text('{"Model":{"Mesh":"meshes/coil.msh"}}')
        self.assertEqual(run.files().metadata, meta)
        [src] = resolve_inputs([("case", case)], cwd=self.root)
        self.assertEqual(src.files().metadata, meta)
        meta.write_text('{"mesh_file":"other.msh"}')
        self.assertIsNone(src.files().metadata)
        meta.write_text('{"invalid"')
        self.assertEqual(run.files().load(), (mesh, read_deck(case), None))
        case.unlink()
        with self.assertRaisesRegex(ValueError, "geometry.json.*line 1"):
            run.files()

    def test_history_only_and_late_publication(self):
        sources, history, _ = arguments(["--history", str(self.root)])
        self.assertEqual(sources, [])
        folder = self.deck(".working").parent
        (folder / "design.json").write_text('{"name":"one"}')
        self.assertEqual(list(design_history(history)), [])
        folder.rename(self.root / "one")
        [(entry, record)] = design_history(history)
        self.assertEqual((entry.name, record["name"]), ("one", "one"))

    def test_no_input_prints_usage_only(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(arguments([]), ([], None, 8765))
        self.assertIn("--case DECK", output.getvalue())
        self.assertIn("--run DIR", output.getvalue())
        self.assertIn("bazel run //viewer:serve -- --case", output.getvalue())


if __name__ == "__main__":
    unittest.main()
