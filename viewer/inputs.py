"""Resolve explicit Palace decks and generated run directories for read-only inspection."""
import argparse
from dataclasses import dataclass
import fcntl
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re


# Consume JSON strings before comments; URLs and escaped quotes are valid string contents.
_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|//[^\r\n]*|/\*.*?\*/', re.DOTALL)


def read_deck(path):
    """Read a JSON object, retaining line and column numbers through Palace-style comments."""
    path = Path(path)

    def strip(match):
        token = match.group()
        return token if token.startswith('"') else re.sub(r"[^\r\n]", " ", token)

    def reject_constant(value):
        raise ValueError(f"invalid JSON number {value}")

    try:
        value = json.loads(_TOKEN.sub(strip, path.read_text(encoding="utf-8")),
                           parse_constant=reject_constant)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _metadata_mesh(path):
    name = read_deck(path).get("mesh_file", "model.msh")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{path}: mesh_file must name a mesh file")
    return (path.parent / name).resolve()


@dataclass(frozen=True)
class SceneFiles:
    mesh: Path
    deck: Path | None
    metadata: Path | None

    def load(self):
        return (self.mesh, read_deck(self.deck) if self.deck else None,
                read_deck(self.metadata) if self.metadata else None)

    def version(self):
        # An editor or mesher may replace a file atomically while the inspector is running.
        return tuple((s.st_ino, s.st_mtime_ns, s.st_size) for s in
                     (p.stat() for p in (self.mesh, self.deck, self.metadata) if p))


@dataclass(frozen=True)
class Input:
    kind: str
    path: Path
    id: str
    name: str

    def files(self):
        deck = self.path if self.kind == "case" else self.path / "palace.json"
        if self.kind == "run" and not deck.exists():
            meta = self.path / "geometry.json"
            if not meta.is_file():
                raise ValueError(f"{self.path}: expected palace.json or geometry.json")
            mesh = _metadata_mesh(meta)
            if not mesh.is_file():
                raise ValueError(f"{meta}: mesh does not exist: {mesh}")
            return SceneFiles(mesh, None, meta)

        model = read_deck(deck).get("Model")
        mesh_name = model.get("Mesh") if isinstance(model, dict) else None
        if not isinstance(mesh_name, str) or not mesh_name.strip():
            raise ValueError(f"{deck}: Model.Mesh must name a mesh file")
        referenced = deck.parent / mesh_name
        mesh = referenced.resolve()
        if not mesh.is_file():
            raise ValueError(f"{deck}: Model.Mesh does not point to a file: {referenced}")

        # Each optional sidecar declares its own mesh; another deck can share the directory.
        for parent in dict.fromkeys((referenced.parent, mesh.parent, deck.parent)):
            meta = parent / "geometry.json"
            if meta.is_file():
                try:
                    applies = _metadata_mesh(meta) == mesh
                except (ValueError, OSError):
                    continue
                if applies:
                    return SceneFiles(mesh, deck, meta.resolve())
        return SceneFiles(mesh, deck, None)

    def summary(self):
        return {"id": self.id, "name": self.name, "kind": self.kind, "path": str(self.path)}


def resolve_inputs(entries, cwd):
    """Resolve (kind, path) pairs in CLI order. Repeated references to one input share its ID."""
    paths = {}
    for kind, given in entries:
        path = (Path(cwd) / given).resolve()
        if kind == "case" and not path.is_file():
            raise ValueError(f"--case expects an existing Palace deck: {path}")
        if kind == "run" and not path.is_dir():
            raise ValueError(f"--run expects an existing directory: {path}")
        if kind not in ("case", "run"):
            raise ValueError(f"Unknown input type: {kind}")
        paths[path] = kind

    result = []
    for path, kind in paths.items():
        depth = 1
        while any(q != path and q.parts[-depth:] == path.parts[-depth:] for q in paths):
            depth += 1
        label = str(Path(*path.parts[-depth:]))
        key = hashlib.sha256(os.fsencode(path)).hexdigest()
        source = Input(kind, path, key, label)
        source.files()  # Report bad paths and malformed decks before opening a listening socket.
        result.append(source)
    return result


@lru_cache(maxsize=2048)
def _published_run(path, version):
    source, = resolve_inputs([("run", path)], path.parent)
    return source, read_deck(path / "design.json")


def design_history(directory):
    """Read atomically published study runs. Ignore in-progress and unrelated directories."""
    published = []
    for record in directory.glob("*/design.json"):
        if record.parent.name.startswith("."):
            continue
        path = record.parent.resolve()
        if path.parent != directory:
            continue
        stat = record.stat()
        entry = _published_run(path, (stat.st_ino, stat.st_mtime_ns, stat.st_size))
        published.append(entry)

    def sequence(entry):
        name = entry[0].name
        number = name.partition("-")[0]
        return int(number) if number.isdigit() else float("inf"), name

    return sorted(published, key=sequence)


def study_activity(directory):
    """A live writer holds the advisory lock until it finishes or the process exits."""
    try:
        with (directory / ".study.lock").open() as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                candidates = (p for p in directory.iterdir()
                              if re.match(r"^\.(?:\d+-|cobyqa-)", p.name)
                              and ".interrupted-" not in p.name and p.is_dir())
                active = max(candidates, key=lambda p: p.stat().st_mtime_ns, default=None)
                status = "Solving " + active.name[1:] if active else "Preparing next design"
                pause = directory / "PAUSE"
                if pause.is_file() and pause.read_text().strip() == "COBYQA queued":
                    status += " · COBYQA queued"
                return status
    except FileNotFoundError:
        return ""
    return "Paused" if (directory / "PAUSE").exists() else "Worker stopped"


class InputArgument(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        entries = getattr(namespace, self.dest, None)
        if entries is None:
            entries = []
            setattr(namespace, self.dest, entries)
        entries.append((option_string[2:], values))


def arguments(argv=None):
    parser = argparse.ArgumentParser(description="Inspect meshes from Palace decks or run folders.")
    parser.add_argument("--case", metavar="DECK", dest="inputs", action=InputArgument, type=Path,
                        help="Palace JSON deck; may be repeated")
    parser.add_argument("--run", metavar="DIR", dest="inputs", action=InputArgument, type=Path,
                        help="Palace or generated-geometry directory; may be repeated")
    parser.add_argument("--port", type=int, default=8765, help="loopback HTTP port (default 8765)")
    parser.add_argument("--history", metavar="DIR", type=Path,
                        help="discover completed design runs whenever the catalog is opened")
    args = parser.parse_args(argv)
    if not args.inputs and not args.history:
        parser.print_usage()
        print("  bazel run //viewer:serve -- --case path/to/model.json")
        return [], None, args.port
    try:
        cwd = os.environ.get("BUILD_WORKING_DIRECTORY", ".")
        history = (Path(cwd) / args.history).resolve() if args.history else None
        if history and not history.is_dir():
            raise ValueError(f"--history expects an existing directory: {history}")
        return resolve_inputs(args.inputs or [], cwd), history, args.port
    except (ValueError, OSError) as error:
        parser.error(str(error))
