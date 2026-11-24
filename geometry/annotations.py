"""Optional inspection annotations for the coupled-microstrip geometry producer."""
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


def sizing_regions(model, mesh):
    d, y, z = model.dimensions, model.y_edges, model.z_edges
    ny, nz = mesh["y_intervals"], mesh["z_intervals"]

    def box(left, right, bottom=z[0], top=z[-1]):
        return [0, left, bottom, d.length, right, top]

    entries = [
        ("Coupling gap", "Y", ny[2], [box(y[2], y[3])], "Transfinite"),
        ("Trace widths", "Y", ny[1], [box(y[1], y[2]), box(y[3], y[4])], "Transfinite"),
        ("Side clearances", "Y", ny[0], [box(y[0], y[1]), box(y[4], y[5])], "Graded transfinite"),
        ("Substrate depth", "Z", nz[0], [box(y[0], y[-1], z[0], z[1])], "Transfinite"),
        ("Air clearance", "Z", nz[1], [box(y[0], y[-1], z[1], z[2])], "Graded transfinite"),
        ("Extrusion length", "X", mesh["x_intervals"], [box(y[0], y[-1])], "Extruded layers"),
    ]
    return [{"name": name, "axis": axis, "intervals": count, "boxes": boxes, "rule": rule}
            for name, axis, count, boxes, rule in entries]


def annotate_coupon(meta, model):
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
            "regions": sizing_regions(model, meta["mesh"])}


def upgrade_archived_coupon(meta):
    """Supply annotations omitted by the initial coupon generator, without modifying its files."""
    if (meta.get("model") == "uniform edge-coupled microstrip" and "regions" not in meta
            and "dimensions_mm" in meta and "physical_groups" in meta
            and {"x_intervals", "y_intervals", "z_intervals"} <= meta.get("mesh", {}).keys()):
        return annotate_coupon(meta, CoupledMicrostrip(Dimensions(**meta["dimensions_mm"])))
    return meta
