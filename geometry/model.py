"""Dimensions, materials and physical surfaces of a uniform edge-coupled microstrip section."""
from dataclasses import asdict, dataclass
from math import isfinite


# These attributes are the interface between the CAD, the field solver and the viewer.
GROUPS = (
    (3, 1, "substrate"), (3, 2, "air"), (2, 10, "enclosure_pec"),
    (2, 11, "main_trace_pec"), (2, 12, "pickup_trace_pec"), (2, 13, "end_pmc"),
    (2, 14, "ground_pec"),
    (2, 21, "port_1"), (2, 22, "port_2"), (2, 23, "port_3"), (2, 24, "port_4"),
)


@dataclass(frozen=True)
class Dimensions:
    """All lengths are millimetres. Width refers to one signal trace."""

    length: float = 8.0
    width: float = 1.1
    gap: float = 0.22
    substrate_height: float = 0.508
    lid_clearance: float = 2.0
    side_clearance: float = 2.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class PortSheet:
    """Rectangular x-normal terminal between a ground plane and a strip, in millimetres."""

    index: int
    tag: int
    role: str
    x: float
    y_center: float
    width: float
    height: float
    ground_z: float = 0.0

    def contains(self, x, y, z, tolerance=0.0):
        return (abs(x - self.x) <= tolerance and
                abs(y - self.y_center) <= self.width / 2 + tolerance and
                self.ground_z - tolerance <= z <= self.ground_z + self.height + tolerance)

    def metadata(self):
        return {"index": self.index, "tag": self.tag, "role": self.role,
                "center_mm": [self.x, self.y_center, self.ground_z + self.height / 2],
                "direction": [0, 0, 1]}


@dataclass(frozen=True)
class CoupledMicrostrip:
    dimensions: Dimensions = Dimensions()
    relative_permittivity: float = 3.48

    def __post_init__(self):
        if not isfinite(self.relative_permittivity) or self.relative_permittivity < 1:
            raise ValueError("relative_permittivity must be finite and at least 1")

    @property
    def y_edges(self):
        d = self.dimensions
        inner = d.gap / 2
        outer = inner + d.width
        side = outer + d.side_clearance
        return (-side, -outer, -inner, inner, outer, side)

    @property
    def z_edges(self):
        d = self.dimensions
        return (0.0, d.substrate_height, d.substrate_height + d.lid_clearance)

    @property
    def port_sheets(self):
        d = self.dimensions
        offset = (d.width + d.gap) / 2
        locations = ((0, -offset, "input"), (d.length, -offset, "through"),
                     (0, offset, "near-end pickup"), (d.length, offset, "far-end pickup"))
        return tuple(
            PortSheet(i, 20 + i, role, x, y, d.width, d.substrate_height)
            for i, (x, y, role) in enumerate(locations, start=1)
        )

    @property
    def ports(self):
        return [sheet.metadata() for sheet in self.port_sheets]

    def metadata(self):
        d = self.dimensions
        return {
            "model": "uniform edge-coupled microstrip",
            "units": "mm",
            "dimensions_mm": asdict(d),
            "bounds_mm": [[0, self.y_edges[0], 0], [d.length, self.y_edges[-1], self.z_edges[-1]]],
            "materials": {"substrate": {"relative_permittivity": self.relative_permittivity},
                          "air": {"relative_permittivity": 1.0}},
            "physical_groups": [
                {"dimension": dim, "tag": tag, "name": name} for dim, tag, name in GROUPS
            ],
            "ports": self.ports,
        }
