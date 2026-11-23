"""Validate the exported first-order hexahedral mesh and its solver-facing tags."""
from collections import Counter
from math import isclose, prod

from .model import GROUPS


def validate(path, model):
    rows = path.read_text().splitlines()

    def section(name):
        start = rows.index("$" + name)
        return rows[start + 2:rows.index("$End" + name)]

    labels = {tuple(row.split(maxsplit=2)) for row in section("PhysicalNames")}
    expected = {(str(dim), str(tag), '"' + name + '"') for dim, tag, name in GROUPS}
    if labels != expected or rows[1] != "2.2 0 8":
        raise ValueError("Unexpected MSH format or physical groups")
    nodes = {}
    for row in section("Nodes"):
        index, *point = row.split()
        nodes[int(index)] = tuple(map(float, point))
    # Face node order follows the Gmsh first-order hexahedron convention.
    faces = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
    adjacency = Counter()
    surfaces = {}
    ports = {sheet.tag: sheet for sheet in model.port_sheets}
    counts = Counter()
    measure = Counter()
    for row in section("Elements"):
        _, kind, ntags, tag, *rest = map(int, row.split())
        dim = 3 if tag in (1, 2) else 2
        if kind != (5 if dim == 3 else 3):
            raise ValueError(f"Nonlinear or unexpected element type {kind} for tag {tag}")
        corners = rest[ntags - 1:]
        pts = [nodes[i] for i in corners]
        spans = [max(axis) - min(axis) for axis in zip(*pts)]
        if sum(delta > 0 for delta in spans) != dim or len(set(pts)) != 2**dim:
            raise ValueError(f"Degenerate or non-axis-aligned element for tag {tag}")
        if dim == 3:
            a, b, c = [tuple(v - u for u, v in zip(pts[0], pts[i])) for i in (1, 3, 4)]
            det = (a[0] * (b[1]*c[2] - b[2]*c[1]) + a[1] * (b[2]*c[0] - b[0]*c[2])
                   + a[2] * (b[0]*c[1] - b[1]*c[0]))
            if det <= 0:
                raise ValueError(f"Hexahedron has nonpositive oriented volume {det}")
            for face in faces:
                adjacency[tuple(sorted(corners[i] for i in face))] += 1
        else:
            face = tuple(sorted(corners))
            if face in surfaces:
                raise ValueError(f"Duplicate boundary quad for tag {tag}")
            surfaces[face] = tag
            if tag in ports:
                if any(not ports[tag].contains(*pt, tolerance=1e-8) for pt in pts):
                    raise ValueError(f"Port quad outside expected rectangle for tag {tag}")
        measure[tag] += prod(delta for delta in spans if delta > 0)
        counts[tag] += 1
    for face, tag in surfaces.items():
        if adjacency[face] != (2 if tag in (11, 12) else 1):
            raise ValueError(f"Incorrect adjacent volume count for surface tag {tag}")
    if any(n > 2 or (n == 1 and f not in surfaces) for f, n in adjacency.items()):
        raise ValueError("Nonmanifold mesh or untagged exterior face")
    d = model.dimensions
    width = model.y_edges[-1] - model.y_edges[0]
    height = model.z_edges[-1]
    sheet = d.width * d.substrate_height
    targets = {
        1: width * d.length * d.substrate_height,
        2: width * d.length * d.lid_clearance,
        10: 2 * d.length * (width + height),
        11: d.length * d.width, 12: d.length * d.width,
        13: 2 * (width * height - 2 * sheet),
        21: sheet, 22: sheet, 23: sheet, 24: sheet,
    }
    for tag, target in targets.items():
        if not isclose(measure[tag], target, rel_tol=1e-8):
            raise ValueError(f"Physical tag {tag} measures {measure[tag]}, expected {target}")
    return {"nodes": len(nodes), "hexes": counts[1] + counts[2],
            "elements_per_tag": dict(sorted(counts.items()))}
