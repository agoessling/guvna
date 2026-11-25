"""Discover completed Palace AMR iterations and read their saved visualization meshes."""
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkStaticCellLocator, vtkUnstructuredGrid
from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader

from viewer.fields import child
from viewer.inputs import read_deck
from viewer.scene import mm_per_unit


@dataclass(frozen=True)
class Stage:
    number: int
    directory: Path
    cells: int
    dofs: int
    indicator: float | None
    volume: tuple
    boundary: tuple

    def summary(self):
        return dict(id=self.number, cells=self.cells, dofs=self.dofs, indicator=self.indicator)


def pieces(series):
    # Every frequency and excitation within this iteration uses the same mesh.
    for collection in sorted(series.rglob("*.pvd")):
        for entry in ET.parse(collection).iter("DataSet"):
            header = child(collection.parent, entry.attrib["file"], ".pvtu")
            return tuple(child(header.parent, p.attrib["Source"], ".vtu")
                         for p in ET.parse(header).iter("Piece"))
    return ()


@lru_cache(maxsize=32)
def stages(source):
    files = source.files()
    if not files.deck:
        return {}
    deck = read_deck(files.deck)
    out = files.deck.parent / deck.get("Problem", {}).get("Output", "postpro")
    order = files.deck.parent / "mesh-stages.json"
    indexed = source.kind == "run" and order.is_file()
    if indexed:
        # A restart resets Palace's iteration counter. The index orders the original outputs
        # and includes the repeated restart mesh only once.
        paths = read_deck(order).get("outputs")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
            raise ValueError(f"{order}: expected an ordered list of stage output directories")
        folders = [order.parent / path for path in paths]
    else:
        final = out / "palace.json"
        if not final.is_file() or read_deck(final).get("Problem", {}).get("Iteration", 0) < 2:
            return {}
        folders = [*out.glob("iteration[0-9]*"), out]
    result = {}
    for index, folder in enumerate(folders, start=1):
        report = folder / "palace.json"
        if not indexed and not report.is_file():
            continue
        stats = read_deck(report)["Problem"]
        number = index if indexed else int(stats["Iteration"])
        root = folder / "paraview"
        for series in sorted(root.glob("*")):
            if series.name.endswith("_boundary"):
                continue
            volume = pieces(series)
            if volume:
                norm = None
                indicator = folder / "error-indicators.csv"
                if indicator.is_file():
                    with indicator.open() as stream:
                        row = next(csv.DictReader(stream, skipinitialspace=True), {})
                        if "Norm" in row:
                            norm = float(row["Norm"])
                result[number] = Stage(number, folder, stats["MeshElements"],
                                       stats["DegreesOfFreedom"], norm, volume,
                                       pieces(root / (series.name + "_boundary")))
                break
        if indexed and number not in result:
            raise ValueError(f"{folder}: missing saved mesh for stage {number}")
    return dict(sorted(result.items()))


# Linear, quadratic and Lagrange VTK cells all place the corner nodes first.
# Each row gives the linear VTK type, its corner count and cell faces.
SHAPES = (
    ((5, 22, 69), 5, 3, ()),
    ((9, 23, 28, 70), 9, 4, ()),
    ((10, 24, 71), 10, 4, ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))),
    ((12, 25, 29, 72), 12, 8, ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                                (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))),
    ((13, 26, 73), 13, 6, ((0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5))),
    ((14, 27, 74), 14, 5, ((0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4))),
)
SHAPE = {key: (kind, n, faces) for keys, kind, n, faces in SHAPES for key in keys}


def read_stage(stage, source):
    point_ids = {}
    groups = {}
    types = []
    connectivity = []
    offsets = [0]
    attributes = []
    unmatched = {}
    for dimension, files in ((3, stage.volume), (2, stage.boundary)):
        for path in files:
            reader = vtkXMLUnstructuredGridReader()
            reader.SetFileName(str(path))
            reader.UpdateInformation()
            reader.GetPointDataArraySelection().DisableAllArrays()
            reader.GetCellDataArraySelection().DisableAllArrays()
            reader.GetCellDataArraySelection().EnableArray("attribute")
            reader.Update()
            grid = reader.GetOutput()
            if not grid.GetNumberOfCells():
                continue
            pts = vtk_to_numpy(grid.GetPoints().GetData())
            tags = vtk_to_numpy(grid.GetCellData().GetArray("attribute")).ravel()
            ids = vtk_to_numpy(grid.GetCells().GetConnectivityArray())
            starts = vtk_to_numpy(grid.GetCells().GetOffsetsArray())
            for i, raw in enumerate(vtk_to_numpy(grid.GetCellTypes()).ravel()):
                if int(raw) not in SHAPE:
                    raise ValueError(f"Unsupported Palace visualization cell {raw} in {path}")
                kind, n, faces = SHAPE[int(raw)]
                tag = int(tags[i])
                group = groups.setdefault((dimension, tag), dict(dimension=dimension, tag=tag,
                                                                  cells=[]))
                cell = [point_ids.setdefault(tuple(p), len(point_ids))
                        for p in pts[ids[starts[i]:starts[i] + n]]]
                group["cells"].append(cell)
                if dimension == 2:
                    continue
                idx = len(types)
                types.append(kind)
                attributes.append(tag)
                connectivity.extend(cell)
                offsets.append(len(connectivity))
                for face in faces:
                    ring = tuple(cell[j] for j in face)
                    key = tag, tuple(sorted(ring))
                    if key in unmatched:
                        del unmatched[key]
                    else:
                        unmatched[key] = idx, ring

    if len(types) != stage.cells:
        raise ValueError(f"Palace saved {len(types)} visualization cells for {stage.cells} solver "
                         "elements. This preview requires one saved cell per element.")
    xyz = np.asarray(list(point_ids), dtype=float)
    vtk_points = vtkPoints()
    vtk_points.SetData(numpy_to_vtk(xyz))
    cells = vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(np.asarray(offsets, dtype=np.int64), deep=True),
                  numpy_to_vtkIdTypeArray(np.asarray(connectivity, dtype=np.int64), deep=True))
    mesh = vtkUnstructuredGrid()
    mesh.SetPoints(vtk_points)
    mesh.SetCells(numpy_to_vtk(np.asarray(types, dtype=np.uint8), deep=True), cells)
    locator = vtkStaticCellLocator()
    locator.SetDataSet(mesh)
    locator.BuildLocator()
    for group in groups.values():
        if group["dimension"] == 3:
            group["skin"] = []
    # At hanging nodes coarse and fine faces do not have matching vertex IDs. Probe across
    # each unpaired face to discard internal faces between elements of the same material.
    for (tag, _), (idx, ring) in unmatched.items():
        center = xyz[connectivity[offsets[idx]:offsets[idx + 1]]].mean(axis=0)
        face = xyz[list(ring)].mean(axis=0)
        neighbor = locator.FindCell(face + (face - center) * 1e-4)
        if neighbor < 0 or neighbor == idx or attributes[neighbor] != tag:
            groups[3, tag]["skin"].append(ring)
    scale = mm_per_unit(read_deck(source.files().deck), {})
    return dict(points=(xyz * scale).tolist(), groups=list(groups.values()))
