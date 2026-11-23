"""Read a 3D Gmsh mesh and attach optional Palace assignments and producer annotations."""
import json
import math
from pathlib import Path

import meshio

from geometry.annotations import upgrade_archived_coupon


CORNERS = {"hexahedron": 8, "tetra": 4, "pyramid": 5, "wedge": 6, "triangle": 3, "quad": 4}
PORT_TYPES = {"WavePort", "LumpedPort", "FloquetPort"}


def boundary_assignments(deck):
    by_tag = {}
    for kind, entries in deck.get("Boundaries", {}).items():
        if kind == "Postprocessing":
            continue
        for entry in entries if isinstance(entries, list) else [entries]:
            if not isinstance(entry, dict):
                continue
            for element in entry.get("Elements", [entry]):
                settings = {**entry, **element}
                settings.pop("Elements", None)
                for selector in ("Attributes", "DonorAttributes", "ReceiverAttributes"):
                    for tag in element.get(selector, []):
                        by_tag.setdefault(tag, []).append({"type": kind, "settings": settings})
    return by_tag


def mm_per_unit(deck, meta):
    if deck is not None and "Model" in deck:
        scale = float(deck["Model"].get("L0", 1e-6)) * 1000  # Palace's default mesh unit is µm.
    else:
        scales = {"m": 1000, "cm": 10, "mm": 1, "µm": 0.001, "μm": 0.001, "um": 0.001,
                  "nm": 1e-6}
        unit = meta.get("units", "mm")
        if unit not in scales:
            raise ValueError(f"Unsupported mesh coordinate unit {unit!r}")
        scale = scales[unit]
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Mesh length scale must be finite and positive")
    return scale


def read_cells(mesh):
    """Combine physical groups across entity blocks, keeping dimension and Gmsh tag separate."""
    by_group = {}
    shapes = set()
    physical = mesh.cell_data.get("gmsh:physical", [None] * len(mesh.cells))
    for block, tags in zip(mesh.cells, physical, strict=True):
        if block.dim < 2:
            continue
        shape = block.type.rstrip("0123456789")
        if shape not in CORNERS:
            raise ValueError(f"Unsupported preview element {block.type}")
        if block.dim == 3:
            shapes.add(block.type)
        corners = block.data[:, :CORNERS[shape]]
        if tags is None:
            by_group.setdefault((block.dim, None), []).extend(corners.tolist())
            continue
        for raw_tag in sorted(set(tags)):
            # In particular an elementary entity ID is not a physical group assignment.
            tag = int(raw_tag) if raw_tag > 0 else None
            by_group.setdefault((block.dim, tag), []).extend(corners[tags == raw_tag].tolist())
    if not shapes:
        raise ValueError("The 3D scene preview needs volume cells")
    return by_group, shapes


def property_value(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def load_scene(mesh_path, deck=None, metadata=None):
    """Return mesh coordinates in mm. Read physical attributes only from the mesh connectivity."""
    mesh_path = Path(mesh_path)
    if mesh_path.suffix.lower() not in {".msh", ".msh2"}:
        raise ValueError("The case preview supports Gmsh .msh and .msh2 files")
    meta = upgrade_archived_coupon(metadata or {})
    mesh = meshio.gmsh.read(mesh_path)
    xyz = mesh.points * mm_per_unit(deck, meta)
    cells, shapes = read_cells(mesh)
    names = {(int(dim), int(tag)): name for name, (tag, dim) in mesh.field_data.items()}
    annotations = {(g["dimension"], g["tag"]): g for g in meta.get("physical_groups", [])}
    boundaries = boundary_assignments(deck or {})
    materials = {tag: material for material in (deck or {}).get("Domains", {}).get("Materials", [])
                 for tag in material["Attributes"]}

    groups = []
    # Assign deterministic numeric UI keys even when a surface and a volume share their tag.
    for dim, tag in sorted(cells, key=lambda k: (-k[0], k[1] or 0)):
        annotation = annotations.get((dim, tag), {}) if tag is not None else {}
        name = annotation.get("name") or names.get((dim, tag)) or f"Attribute {tag}"
        props = dict(annotation.get("properties", {}))
        if tag is None:
            name = "Untagged volume" if dim == 3 else "Untagged surface"
            props["Physical assignment"] = "None in Gmsh mesh"
        if dim == 3:
            category, color = "Materials", "#759188"
            aliases = {"relative_permittivity": "Permittivity",
                       "relative_permeability": "Permeability", "loss_tangent": "LossTan"}
            if deck is None:
                declared = meta.get("materials", {}).get(name, {})
            else:
                declared = materials.get(tag, {})
            values = {aliases.get(k, k): v for k, v in declared.items()}
            for k, v in values.items():
                if k != "Attributes":
                    props[k] = property_value(v)
        else:
            category, color = "Boundary conditions", "#8198a8"
            conditions = boundaries.get(tag, [])
            port = next((c for c in conditions if c["type"] in PORT_TYPES), None)
            if port is not None:
                category, color = "Ports", "#488cb1"
                name = f'P{port["settings"]["Index"]} · {name}'
        group = {
            "key": len(groups) + 1, "dimension": dim, "tag": tag, "cells": cells[dim, tag],
            "name": annotation.get("display_name", name),
            "category": annotation.get("category", category),
            "color": annotation.get("color", color),
            "visible": annotation.get("visible", dim == 3 or category == "Ports"),
            "translucent": annotation.get("translucent", category == "Boundary conditions"),
            "metallic": annotation.get("metallic", False), "properties": props,
        }
        if dim == 2 and deck is not None:
            group["conditions"] = conditions
        groups.append(group)

    mesh_info = {**meta.get("mesh", {}), "nodes": len(xyz),
                 "cells": sum(len(rows) for (dim, _), rows in cells.items() if dim == 3),
                 "elements": ", ".join(sorted(shapes)),
                 "corner_preview": any(b.dim >= 2 and b.type[-1].isdigit() for b in mesh.cells)}
    properties = dict(meta.get("properties", {}))
    if (deck is None or "Model" not in deck) and "units" not in meta:
        properties.setdefault("Coordinate units", "Assumed mm (unlabelled mesh)")
    geometry = {**meta, "model": meta.get("model", mesh_path.stem), "mesh_file": mesh_path.name,
                "bounds_mm": [xyz.min(axis=0).tolist(), xyz.max(axis=0).tolist()],
                "mesh": mesh_info, "properties": properties}
    return {"geometry": geometry, "points": xyz.tolist(), "groups": groups,
            "regions": meta.get("regions", [])}
