"""Serve a read-only inspector for the meshes selected on the command line."""
from functools import lru_cache
import csv
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlsplit
from xml.etree.ElementTree import ParseError

from meshio import ReadError
from python.runfiles import runfiles
from viewer.inputs import arguments
from viewer.fields import section, snapshots, surface
from viewer.scene import load_scene
from viewer.sweep import sweep


def encode(data):
    return json.dumps(data, separators=(",", ":"), allow_nan=False).encode()


def handler_for(sources, rf):
    assets = ("index.html", "style.css", "main.js", "cad.js", "section.js", "inspector.js",
              "field-layer.js", "results.js", "results.css", "eye.svg")
    files = {"/" + name: Path(rf.Rlocation("_main/viewer/ui/" + name)) for name in assets}
    files["/"] = files["/index.html"]
    vendor = ("build/three.core.min.js", "build/three.module.min.js", "LICENSE",
              "examples/jsm/controls/OrbitControls.js",
              "examples/jsm/environments/RoomEnvironment.js")
    for name in vendor:
        path = rf.Rlocation("cad_three/" + name, source_repo="")
        files["/lib/" + Path(name).name] = Path(path)

    cases = {source.id: source for source in sources}
    catalog = encode([source.summary() for source in sources])
    field_lock = Lock()

    @lru_cache(maxsize=16)
    def field_series(key):
        return snapshots(cases[key])

    @lru_cache(maxsize=4)
    def model(scene_files, version):
        try:
            return encode(load_scene(*scene_files.load()))
        except SystemExit as error:
            # meshio can exit after its format reader rejects a malformed mesh.
            raise ValueError(f"Gmsh reader rejected {scene_files.mesh}") from error

    class Handler(BaseHTTPRequestHandler):
        def reply(self, body, mime="application/json", status=200):
            if not isinstance(body, bytes):
                body = encode(body)
            zipped = len(body) > 2048 and "gzip" in self.headers.get("Accept-Encoding", "")
            if zipped:
                body = gzip.compress(body, compresslevel=3)
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Vary", "Accept-Encoding")
            if zipped:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            path = urlsplit(self.path)
            if path.path == "/api/cases":
                self.reply(catalog)
            elif path.path in ("/api/fields", "/api/field-cut", "/api/field-surface"):
                query = parse_qs(path.query)
                try:
                    frames, scale = field_series(query["case"][0])
                    if path.path == "/api/fields":
                        return self.reply([dict(id=i, excitation=f.excitation, ghz=f.frequency,
                                                current=f.current)
                                           for i, f in enumerate(frames)])
                    index = int(query["frame"][0])
                    if not 0 <= index < len(frames):
                        raise ValueError("Unknown field sample")
                    component = query.get("component", ["magnitude"])[0]
                    with field_lock:
                        if path.path == "/api/field-surface":
                            domain = int(query["domain"][0]) if "domain" in query else None
                            data = surface(frames[index], scale, query["quantity"][0], domain,
                                           component)
                        else:
                            data = section(frames[index], scale, int(query["axis"][0]),
                                           float(query["mm"][0]), query["keep"][0] == "upper",
                                           component)
                    self.reply(data)
                except (ValueError, OSError, LookupError, ParseError, RuntimeError) as error:
                    self.reply({"error": f"Could not read saved fields: {error}"}, status=400)
            elif path.path == "/api/sweep":
                key = parse_qs(path.query).get("case", [""])[0]
                if key not in cases:
                    return self.reply({"error": "Unknown input"}, status=404)
                try:
                    self.reply(sweep(cases[key]))
                except (ValueError, OSError, TypeError, csv.Error) as error:
                    self.reply({"error": f"Could not read port response: {error}"}, status=400)
            elif path.path == "/api/model":
                query = parse_qs(path.query, keep_blank_values=True)
                key = query.get("case", [sources[0].id])[0]
                if key not in cases:
                    return self.reply({"error": f"Unknown input: {key}"}, status=404)
                source = cases[key]
                try:
                    selected = source.files()
                    self.reply(model(selected, selected.version()))
                except (ValueError, OSError, LookupError, TypeError, RuntimeError,
                        ReadError) as error:
                    self.reply({"error": f"Could not inspect {source.path}: {error}"}, status=400)
            elif path.path in files:
                file = files[path.path]
                mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                try:
                    self.reply(file.read_bytes(), mime)
                except OSError as error:
                    self.reply({"error": str(error)}, status=404)
            else:
                self.reply({"error": "Unknown resource"}, status=404)

    return Handler


def main():
    sources, port = arguments()
    if not sources:
        return
    try:
        handler = handler_for(sources, runfiles.Create())
        with ThreadingHTTPServer(("127.0.0.1", port), handler) as srv:
            print(f"Serving {len(sources)} input(s) at http://127.0.0.1:{srv.server_port}",
                  flush=True)
            srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
