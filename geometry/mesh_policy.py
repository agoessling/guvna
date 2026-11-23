"""Structured mesh interval counts for a straight coupled-microstrip section."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MeshPolicy:
    length_cells: int = 12
    side_cells: int = 5
    strip_cells: int = 4
    gap_cells: int = 2
    substrate_cells: int = 3
    air_cells: int = 5

    def __post_init__(self):
        for key, value in asdict(self).items():
            if type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")

    @classmethod
    def preset(cls, level):
        if level == 0:
            return cls()
        if level == 1:
            return cls(length_cells=20, side_cells=8, strip_cells=7, gap_cells=4,
                       substrate_cells=5, air_cells=8)
        raise ValueError("Available mesh refinement presets are 0 and 1")

    @property
    def y_intervals(self):
        side, strip = self.side_cells, self.strip_cells
        return (side, strip, self.gap_cells, strip, side)

    @property
    def z_intervals(self):
        return (self.substrate_cells, self.air_cells)
