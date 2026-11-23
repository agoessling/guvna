"""Mesh a coupled microstrip cross section and extrude it along its propagation axis."""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile

import gmsh

from .annotations import annotate_coupon
from .mesh_policy import MeshPolicy
from .model import CoupledMicrostrip, Dimensions, GROUPS
from .validate import validate


def cross_section(model, policy):
    """Shared points and curves make all adjacent volumes and internal strip sheets conforming."""
    geo = gmsh.model.geo
    y, z = model.y_edges, model.z_edges
    # Interval counts, first along y and then along z; keep all four port planes identical.
    ny, nz, nx = policy.y_intervals, policy.z_intervals, policy.length_cells
    points = [[geo.addPoint(0, yi, zi) for yi in y] for zi in z]
    across = []
    for row in points:
        edges = []
        for j, count in enumerate(ny):
            line = geo.addLine(row[j], row[j + 1])
            # Cluster exterior y cells toward the nearest trace edge.
            ratio = 1 / 1.32 if j == 0 else 1.32 if j == len(ny) - 1 else 1.0
            geo.mesh.setTransfiniteCurve(line, count + 1, "Progression", ratio)
            edges.append(line)
        across.append(edges)
    up = []
    for k, count in enumerate(nz):
        edges = []
        for j in range(len(y)):
            line = geo.addLine(points[k][j], points[k + 1][j])
            geo.mesh.setTransfiniteCurve(line, count + 1, "Progression", 1.35 if k else 1.0)
            edges.append(line)
        up.append(edges)
    rectangles = []
    for k in range(len(nz)):
        for j in range(len(ny)):
            loop = geo.addCurveLoop([across[k][j], up[k][j + 1], -across[k + 1][j], -up[k][j]])
            face = geo.addPlaneSurface([loop])
            geo.mesh.setTransfiniteSurface(face)
            geo.mesh.setRecombine(2, face)
            rectangles.append((2, face))
    geo.extrude(rectangles, model.dimensions.length, 0, 0, [nx], [], True)
    geo.synchronize()
    return {"x_intervals": nx, "y_intervals": ny, "z_intervals": nz}


def classify(model, dim, entity):
    x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(dim, entity)
    d = model.dimensions
    y, z = model.y_edges, model.z_edges
    # Geometric entities are identified from their middles, away from the CAD tolerance.
    eps = 1e-7
    ym = (y0 + y1) / 2
    zm = (z0 + z1) / 2
    if dim == 3:
        return 1 if zm < d.substrate_height else 2
    main = y[1] < ym < y[2]
    pickup = y[3] < ym < y[4]
    if abs(x1 - x0) < eps:
        for sheet in model.port_sheets:
            if sheet.contains((x0 + x1) / 2, ym, zm, eps):
                return sheet.tag
        return 13
    if any(abs(ym - wall) < eps for wall in (y[0], y[-1])):
        return 10
    if any(abs(zm - wall) < eps for wall in (z[0], z[-1])):
        return 10
    if abs(zm - d.substrate_height) < eps and abs(z1 - z0) < eps:
        if main:
            return 11
        if pickup:
            return 12
    return None


def generate(model, level, destination, policy=None):
    default = MeshPolicy.preset(level)
    if policy is None:
        policy = default
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination) as name:
        tmp = Path(name)
        gmsh.initialize([], readConfigFiles=False)
        try:
            gmsh.option.setNumber("General.NumThreads", 1)
            gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
            gmsh.option.setNumber("Mesh.Binary", 0)
            gmsh.option.setNumber("Mesh.ElementOrder", 1)
            gmsh.model.add("coupled_microstrip")
            mesh = cross_section(model, policy)
            groups = {}
            for dim in (2, 3):
                for _, entity in gmsh.model.getEntities(dim):
                    tag = classify(model, dim, entity)
                    groups.setdefault(tag, []).append(entity)
            for dim, tag, label in GROUPS:
                gmsh.model.addPhysicalGroup(dim, groups[tag], tag, label)
            gmsh.model.mesh.generate(3)
            gmsh.write(str(tmp / "model.msh"))
        finally:
            gmsh.finalize()
        mesh.update(validate(tmp / "model.msh", model))
        mesh.update({"refinement": level, "gmsh_version": gmsh.__version__, "format": "MSH 2.2"})
        if policy != default:
            mesh["overrides"] = {
                k: v for k, v in asdict(policy).items() if v != getattr(default, k)
            }
        metadata = model.metadata()
        metadata["mesh_file"] = "model.msh"
        metadata["mesh"] = mesh
        metadata = annotate_coupon(metadata, model)
        (tmp / "geometry.json").write_text(json.dumps(metadata, indent=2) + "\n")
        for filename in ("model.msh", "geometry.json"):
            (tmp / filename).replace(destination / filename)


def main():
    defaults = Dimensions()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refinement", type=int, choices=(0, 1), default=0)
    for key in asdict(MeshPolicy()):
        parser.add_argument("--" + key.replace("_", "-"), type=int, metavar="N",
                            help="Override the preset interval count for this feature")
    for key, value in asdict(defaults).items():
        parser.add_argument("--" + key.replace("_", "-"), type=float, default=value, help="mm")
    parser.add_argument("--relative-permittivity", type=float, default=3.48)
    args = parser.parse_args()
    dimensions = Dimensions(**{key: getattr(args, key) for key in asdict(defaults)})
    model = CoupledMicrostrip(dimensions, args.relative_permittivity)
    policy = MeshPolicy.preset(args.refinement)
    overrides = {k: getattr(args, k) for k in asdict(policy) if getattr(args, k) is not None}
    try:
        policy = replace(policy, **overrides)
    except ValueError as error:
        parser.error(str(error))
    generate(model, args.refinement, args.output, policy)


if __name__ == "__main__":
    main()
