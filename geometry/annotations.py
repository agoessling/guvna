"""Optional inspection annotations for the coupled-microstrip geometry producer."""
from .mesh_policy import MeshPolicy
from .model import CoupledMicrostrip, Dimensions


_STYLES = {
    "substrate": ("Substrate", "Materials", "#59756a", True, False),
    "air": ("Air domain", "Materials", "#9ab6c9", False, True),
    "enclosure_pec": ("Enclosure walls", "Boundary conditions", "#76838d", False, True),
    "ground_pec": ("Ground plane", "Conductors", "#b88b60", True, False),
    "main_trace_pec": ("Main trace", "Conductors", "#c68a58", True, False),
    "pickup_trace_pec": ("Pickup trace", "Conductors", "#c68a58", True, False),
    "end_pmc": ("End planes", "Boundary conditions", "#927faa", False, True),
}


def sizing_regions(model, mesh, policy=None):
    if policy is None:
        # Reconstruct the sizing rules when reading a sidecar without its original policy.
        ny, nz = mesh["y_intervals"], mesh["z_intervals"]
        middle = len(ny) // 2
        policy = MeshPolicy(length_cells=mesh["x_intervals"], side_cells=ny[0],
                            strip_cells=ny[middle - 1], gap_cells=ny[middle],
                            substrate_cells=nz[0], air_cells=nz[-1],
                            edge_cells=ny[1] if len(ny) == 7 else 0,
                            interface_cells=nz[1] if len(nz) == 4 else 0)
    y, across, z, up = policy.cross_section(model)
    length = model.dimensions.length
    regions = {}
    for axis, bounds, spans in (("Y", y, across), ("Z", z, up)):
        for lo, hi, (name, count, ratio) in zip(bounds[:-1], bounds[1:], spans, strict=True):
            rule = "Transfinite" if ratio == 1 else "Graded transfinite"
            region = regions.setdefault(name, dict(name=name, axis=axis, intervals=count,
                                                   boxes=[], rule=rule))
            if axis == "Y":
                box = [0, lo, z[0], length, hi, z[-1]]
            else:
                box = [0, y[0], lo, length, y[-1], hi]
            region["boxes"].append(box)
    extrusion = dict(name="Extrusion length", axis="X", intervals=policy.length_cells,
                     boxes=[[0, y[0], z[0], length, y[-1], z[-1]]], rule="Extruded layers")
    return [regions.pop("Coupling gap"), regions.pop("Trace widths"), *regions.values(), extrusion]


def annotate_coupon(meta, model, policy=None):
    """Keep raw Gmsh physical names for the solver and add display labels for generic consumers."""
    by_tag = {p["tag"]: p for p in meta.get("ports", [])}
    roles = {"forward-coupled": "near-end pickup", "isolated": "far-end pickup"}
    groups = []
    for group in meta["physical_groups"]:
        name = group["name"]
        props = {}
        port = by_tag.get(group["tag"]) if group["dimension"] == 2 else None
        if port:
            role = roles.get(port["role"], port["role"])
            style = (f'P{port["index"]} · {role}', "Ports", "#548ab0", False, False)
            props["Center (mm)"] = ", ".join(f"{v:g}" for v in port["center_mm"])
        elif name in _STYLES:
            style = _STYLES[name]
        else:
            groups.append(group)
            continue
        label, category, color, visible, translucent = style
        groups.append({**group, "display_name": label, "category": category, "color": color,
                       "visible": visible, "translucent": translucent,
                       "metallic": category == "Conductors", "properties": props})
    dims = meta["dimensions_mm"]
    labels = {"length": "Length", "width": "Trace width", "gap": "Gap",
              "substrate_height": "Core thickness", "lid_clearance": "Lid clearance",
              "side_clearance": "Side clearance"}
    props = {label: f"{dims[key]:g} mm" for key, label in labels.items()}
    return {**meta, "physical_groups": groups, "properties": props,
            "regions": sizing_regions(model, meta["mesh"], policy)}


def upgrade_archived_coupon(meta):
    """Supply annotations omitted by the initial coupon generator, without modifying its files."""
    if (meta.get("model") == "uniform edge-coupled microstrip" and "regions" not in meta
            and "dimensions_mm" in meta and "physical_groups" in meta
            and {"x_intervals", "y_intervals", "z_intervals"} <= meta.get("mesh", {}).keys()):
        return annotate_coupon(meta, CoupledMicrostrip(Dimensions(**meta["dimensions_mm"])))
    return meta
