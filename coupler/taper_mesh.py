"""Structured, edge-graded meshes and inspection regions for an edge-coupled pair."""

from dataclasses import dataclass
from functools import lru_cache
from itertools import accumulate, pairwise
import math


@dataclass(frozen=True)
class GapMesh:
    """One symmetric half-gap, ordered from the copper edge toward the symmetry plane."""

    edge_cells: int
    caps: tuple

    @classmethod
    def for_design(cls, design, refinement=1):
        if type(refinement) is not int or refinement < 1:
            raise ValueError("Gap refinement must be a positive integer")
        edge_pitch = 0.055 / refinement
        edge_cells = 2 * refinement
        caps = [edge_pitch] * edge_cells
        while len(caps) == edge_cells or sum(caps) < max(design.gap, design.end_gap) / 2:
            caps.append(min(caps[-1] * 1.5, 0.22 / refinement))
        return cls(edge_cells, tuple(caps))

    @classmethod
    def eight_cells(cls, design):
        # Keep one 0.11 mm edge band; distribute wider outlet gaps across interior cells.
        interior = max(0.11, (max(design.gap, design.end_gap) / 2 - 0.11) / 9)
        return cls(1, (0.11, 2 * interior, 3 * interior, 4 * interior))

    @property
    def intervals(self):
        return 2 * len(self.caps)

    def distances(self, half_gap):
        # Distribute spare width evenly among remaining cells, up to each physical pitch cap.
        remaining = half_gap
        widths = []
        for i, cap in enumerate(self.caps):
            width = min(cap, remaining / (len(self.caps) - i))
            widths.append(width)
            remaining -= width
        return tuple(accumulate(widths, initial=0.0))


def shape_mesh(run, meta, design, gap_mesh):
    """Map the uniform seed onto the taper. Emit overlays from the same coordinate map."""
    d = design
    wall = meta["bounds_mm"][1][1]
    inner = d.gap / 2
    outer = inner + d.width
    end_width = d.width if d.end_width is None else d.end_width
    if (not math.isfinite(end_width) or min(inner, d.end_gap / 2, d.width, end_width, d.power) <= 0
            or max(outer, d.end_gap / 2 + end_width) >= wall):
        raise ValueError("Gap and width must leave positive clearance to the enclosure")
    gap_region = next(r for r in meta["regions"] if r["name"] == "Coupling gap")
    if gap_region["intervals"] != gap_mesh.intervals:
        raise ValueError("Seed gap count differs from the requested taper mesh")

    @lru_cache(maxsize=None)
    def section(x):
        t = (x / d.length) ** d.power
        h = inner + (d.end_gap / 2 - inner) * t
        width = d.width + (end_width - d.width) * t
        return h, width, gap_mesh.distances(h)

    def mapped(x, y):
        h, width, distances = section(x)
        r = abs(y)
        if r < inner:
            # Each seed interval in the gap corresponds to one interval of the graded mesh.
            t = (1 - r / inner) * (len(distances) - 1)
            i = min(int(t), len(distances) - 2)
            offset = distances[i] + (t - i) * (distances[i + 1] - distances[i])
            dest = max(0, h - offset)
        elif r <= outer:
            dest = h + (r - inner) * width / d.width
        else:
            dest = r + (h + width - outer) * (wall - r) / (wall - outer)
        return math.copysign(dest, y)

    mesh = run / "model.msh"
    lines = mesh.read_text().splitlines()
    start = lines.index("$Nodes") + 2
    xs, ys = set(), set()
    for i in range(start, lines.index("$EndNodes", start)):
        node, xstr, ystr, zstr = lines[i].split()
        x, y = float(xstr), float(ystr)
        xs.add(round(x, 10))
        if abs(x) < 1e-9 and abs(float(zstr)) < 1e-9:
            ys.add(round(y, 10))
        lines[i] = f"{node} {xstr} {mapped(x, y):.16g} {zstr}"
    mesh.write_text("\n".join(lines) + "\n")

    _, lo, z, end, hi, top = gap_region["boxes"][0]
    band = d.gap * gap_mesh.edge_cells / gap_mesh.intervals
    edge_region = dict(name="Facing trace edges", axis="Y", intervals=gap_mesh.edge_cells,
                       rule="Edge pitch limited", boxes=[[0, lo, z, end, lo + band, top],
                                                         [0, hi - band, z, end, hi, top]])
    gap_region.update(name="Gap interior", rule="Graded toward facing edges",
                      intervals=gap_mesh.intervals - 2 * gap_mesh.edge_cells,
                      boxes=[[0, lo + band, z, end, hi - band, top]])
    meta["regions"].insert(meta["regions"].index(gap_region), edge_region)
    stations = sorted(xs)
    for r in meta["regions"]:
        if r["axis"] != "Y":
            continue
        r["sweeps"] = []
        smallest, largest = math.inf, 0.0
        for _, low, z, _, high, top in r.pop("boxes"):
            row = sorted(v for v in ys if low - 1e-8 <= v <= high + 1e-8)
            if len(row) != r["intervals"] + 1:
                raise ValueError(f"Region boundaries do not match seed nodes: {r['name']}")
            sections = []
            for x in stations:
                coords = [mapped(x, v) for v in row]
                steps = [b - a for a, b in pairwise(coords)]
                smallest, largest = min(smallest, min(steps)), max(largest, max(steps))
                sections.append([x, coords[0], coords[-1]])
            r["sweeps"].append(dict(z=[z, top], sections=sections))
        r["spacing_mm"] = [smallest, largest]

    for port in meta["ports"]:
        if port["index"] in (2, 4):
            center = port["center_mm"]
            center[1] = math.copysign((end_width + d.end_gap) / 2, center[1])
            group = next(g for g in meta["physical_groups"] if g["tag"] == port["tag"])
            group["properties"]["Center (mm)"] = ", ".join(f"{v:g}" for v in center)

    meta["model"] = "Edge-coupled PCB design study"
    meta["materials"]["air"]["relative_permittivity"] = d.cover_er
    if d.cover_er != 1:
        cover = next(g for g in meta["physical_groups"] if g["name"] == "air")
        cover["display_name"] = "Upper dielectric"
    props = meta["properties"]
    props.pop("Trace width")
    props.update({"Width at input": f"{d.width:g} mm", "Width at output": f"{end_width:g} mm"})
    meta["dimensions_mm"].update(end_width=end_width, end_gap=d.end_gap)
    props.pop("Gap")
    props.pop("Side clearance")
    props.update({"Gap at input": f"{d.gap:g} mm", "Gap at output": f"{d.end_gap:g} mm",
                  "Gap exponent": d.power, "Upper relative permittivity": d.cover_er,
                  "Gap intervals": gap_mesh.intervals})
