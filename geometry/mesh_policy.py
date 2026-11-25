"""Structured mesh interval counts for a straight coupled-microstrip section."""
from dataclasses import asdict, dataclass
from math import ceil


@dataclass(frozen=True)
class MeshPolicy:
    length_cells: int = 12
    side_cells: int = 5
    strip_cells: int = 4
    gap_cells: int = 2
    substrate_cells: int = 3
    air_cells: int = 5

    # Optional additional layers at both outer trace edges and on each side of the trace plane.
    edge_cells: int = 0
    interface_cells: int = 0

    def __post_init__(self):
        for key, value in asdict(self).items():
            minimum = 0 if key in ("edge_cells", "interface_cells") else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"{key} must be an integer >= {minimum}")

    @classmethod
    def preset(cls, level, length_mm=8.0):
        if level == 0:
            return cls()
        if level == 1:
            return cls(length_cells=20, side_cells=8, strip_cells=7, gap_cells=4,
                       substrate_cells=5, air_cells=8)
        if level == "trace-edges":
            return cls(length_cells=ceil(length_mm * 0.96), side_cells=3, strip_cells=4,
                       gap_cells=4, substrate_cells=2, air_cells=3, edge_cells=2,
                       interface_cells=2)
        raise ValueError("Available mesh presets are 0, 1 and trace-edges")

    @property
    def y_intervals(self):
        side, strip = self.side_cells, self.strip_cells
        edge = (self.edge_cells,) if self.edge_cells else ()
        return (side, *edge, strip, self.gap_cells, strip, *edge, side)

    @property
    def z_intervals(self):
        bands = (self.interface_cells,) * 2 if self.interface_cells else ()
        return (self.substrate_cells, *bands, self.air_cells)

    def cross_section(self, model):
        """Return named spans shared by the transfinite mesher and viewer region overlays."""
        y = list(model.y_edges)
        z = list(model.z_edges)
        side, strip, gap = "Side clearances", "Trace widths", "Coupling gap"
        across = [(side, self.side_cells, 1 / 1.32), (strip, self.strip_cells, 1.0),
                  (gap, self.gap_cells, 1.0), (strip, self.strip_cells, 1.0),
                  (side, self.side_cells, 1.32)]
        up = [("Substrate depth", self.substrate_cells, 1.0),
              ("Air clearance", self.air_cells, 1.35)]
        if self.edge_cells:
            height = model.dimensions.substrate_height
            width = min(model.dimensions.side_clearance / 8, height / 2)
            y = [y[0], y[1] - width, *y[1:5], y[4] + width, y[5]]
            edge = ("Outer trace edges", self.edge_cells, 1.0)
            across = [across[0], edge, *across[1:4], edge, across[-1]]
        if self.interface_cells:
            below = z[1] - model.dimensions.substrate_height / 4
            above = z[1] + min(model.dimensions.lid_clearance * 0.12,
                               model.dimensions.substrate_height / 2)
            z = [z[0], below, z[1], above, z[-1]]
            up = [up[0], ("Substrate at traces", self.interface_cells, 1.0),
                  ("Air at traces", self.interface_cells, 1.0), up[1]]
        return y, across, z, up
