"""Saved electric-field sections from a completed Palace driven run."""
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import re
from xml.etree import ElementTree as ET

import numpy as np

from viewer.inputs import read_deck
from viewer.scene import mm_per_unit


@dataclass(frozen=True)
class Snapshot:
    excitation: int | None
    frequency: float
    pieces: tuple[Path, ...]
    boundary: tuple[Path, ...] = ()
    current: bool = False


def child(folder, name, suffix):
    path = (folder / name).resolve()
    if not path.is_relative_to(folder.resolve()) or path.suffix != suffix:
        raise ValueError(f"Invalid field dataset reference: {name}")
    return path


def snapshots(source):
    if source.kind != "run":
        return [], 1.0
    deck_file = source.path / "palace.json"
    if not deck_file.exists():
        return [], 1.0
    deck = read_deck(deck_file)
    out = source.path / deck.get("Problem", {}).get("Output", "postpro")
    root = out / "paraview"
    boundary = dict(series_files(root / "driven_boundary"))
    result = []
    for key, (pieces, names) in series_files(root / "driven"):
        if {"E_real", "E_imag"} <= names:
            sheet, arrays = boundary.get(key, ((), set()))
            result.append(Snapshot(*key, pieces, sheet, {"J_s_real", "J_s_imag"} <= arrays))
    result.sort(key=lambda item: (item.excitation or 0, item.frequency))
    return result, mm_per_unit(deck, {})


def series_files(series):
    for collection in sorted(series.rglob("*.pvd")):
        match = re.search(r"excitation_(\d+)", str(collection.relative_to(series)))
        drive = int(match[1]) if match else None
        for entry in ET.parse(collection).iter("DataSet"):
            header = child(collection.parent, entry.attrib["file"], ".pvtu")
            xml = ET.parse(header)
            names = {a.get("Name") for a in xml.findall(".//PPointData/PDataArray")}
            pieces = tuple(child(header.parent, p.attrib["Source"], ".vtu")
                           for p in xml.iter("Piece"))
            freq = float(entry.attrib["timestep"])
            if not math.isfinite(freq) or not pieces:
                raise ValueError(f"Invalid saved field in {header}")
            yield (drive, freq), (pieces, names)


@lru_cache(maxsize=8)
def grid(path, stamp, quantity="E"):
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader

    reader = vtkXMLUnstructuredGridReader()
    reader.SetFileName(str(path))
    reader.UpdateInformation()
    selection = reader.GetPointDataArraySelection()
    selection.DisableAllArrays()
    for suffix in ("_real", "_imag"):
        name = quantity + suffix
        if selection.ArrayExists(name):
            selection.EnableArray(name)
    reader.Update()
    data = reader.GetOutput()
    if not data.GetNumberOfCells():
        raise ValueError(f"No field cells in {path.name}")
    return data


def polygons(grid, axis, position):
    from vtkmodules.vtkCommonCore import vtkIdList
    from vtkmodules.vtkCommonDataModel import vtkPlane, vtkStaticCellLocator
    from vtkmodules.vtkFiltersCore import vtkExtractCells, vtkPlaneCutter
    from vtkmodules.vtkFiltersGeneral import vtkDataSetTriangleFilter

    direction = axis
    normal, origin = [0.] * 3, [0.] * 3
    normal[direction], origin[direction] = 1., position
    plane = vtkPlane()
    plane.SetOrigin(origin)
    plane.SetNormal(normal)
    if not grid.IsHomogeneous() or not grid.GetCell(0).IsLinear():
        # Restrict first: triangulating an entire high-order parallel mesh can exhaust host RAM.
        cells = vtkIdList()
        locator = vtkStaticCellLocator()
        locator.SetDataSet(grid)
        locator.BuildLocator()
        locator.FindCellsAlongPlane(origin, normal, grid.GetLength() * 1e-8, cells)
        region = vtkExtractCells()
        region.SetInputData(grid)
        region.SetCellList(cells)
        linear = vtkDataSetTriangleFilter()
        linear.SetInputConnection(region.GetOutputPort())
        linear.Update()
        grid = linear.GetOutput()
    cutter = vtkPlaneCutter()
    cutter.SetInputData(grid)
    cutter.SetPlane(plane)
    cutter.InterpolateAttributesOn()
    cutter.MergePointsOff()
    cutter.GeneratePolygonsOn()
    cutter.Update()
    return cutter.GetOutput()


def field_values(data, quantity, component):
    """Return vector magnitudes or the real/imaginary pair of one Cartesian component."""
    from vtkmodules.util.numpy_support import vtk_to_numpy

    parts = [data.GetPointData().GetArray(quantity + suffix) for suffix in ("_real", "_imag")]
    if any(part is None for part in parts):
        raise ValueError(f"Incomplete complex {quantity} field")
    real, imag = (vtk_to_numpy(part).astype("d") for part in parts)
    if component == "magnitude":
        return np.sqrt((real**2 + imag**2).sum(axis=1))
    if component not in ("x", "y", "z") or quantity != "E":
        raise ValueError("Select electric field x, y, z or magnitude")
    index = "xyz".index(component)
    return np.column_stack((real[:, index], imag[:, index]))


def section(snapshot, scale, axis, position, keep_upper, component="magnitude"):
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkFiltersCore import vtkTriangleFilter

    if axis not in (0, 1, 2) or not math.isfinite(position):
        raise ValueError("Expected a coordinate axis and a finite position in mm")
    points, faces, values, materials = [], [], [], []
    grids = [grid(path, path.stat().st_mtime_ns) for path in snapshot.pieces]
    ranges = [g.GetBounds()[axis * 2:axis * 2 + 2] for g in grids]
    lo, hi = min(r[0] for r in ranges), max(r[1] for r in ranges)
    # Choose the retained side at interfaces. At an outer face take its interior limit.
    eps = (hi - lo) * 1e-7
    location = position / scale
    location += eps if keep_upper else -eps
    location = np.clip(location, lo + eps, hi - eps)
    if lo - eps <= position / scale <= hi + eps:
        for data in grids:
            tri = vtkTriangleFilter()
            tri.SetInputData(polygons(data, axis, location))
            tri.PassLinesOff()
            tri.PassVertsOff()
            tri.Update()
            poly = tri.GetOutput()
            if not poly.GetNumberOfPolys():
                continue
            values.extend(field_values(poly, "E", component).tolist())
            xyz = vtk_to_numpy(poly.GetPoints().GetData()).astype("d") * scale
            xyz[:, axis] = position
            ids = vtk_to_numpy(poly.GetPolys().GetConnectivityArray()).reshape(-1, 3)
            faces.extend((ids + len(points)).tolist())
            points.extend(xyz.tolist())
            tags = poly.GetCellData().GetArray("attribute")
            materials.extend(vtk_to_numpy(tags).tolist() if tags else [None] * len(ids))
    return dict(points=points, faces=faces, values=values, materials=materials)


def face_key(cell):
    # VTK triangles and quads store corners first, including Lagrange faces. Palace can
    # repeat the same face with distinct point IDs in neighbouring cells and MPI pieces.
    coords = cell.GetPoints()
    return tuple(sorted(coords.GetPoint(i) for i in range(cell.GetNumberOfEdges())))


def surface(snapshot, scale, quantity, domain=None, component="magnitude"):
    """Return independent face samples, preserving each material's one-sided field."""
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkCommonCore import vtkIdList

    if quantity not in ("E", "J_s") or (quantity == "E" and domain is None):
        raise ValueError("Select surface current or the electric field of a material")
    if quantity == "J_s" and not snapshot.current:
        raise ValueError("No saved boundary current for this sample")
    points, faces, values, materials = [], [], [], []
    triangulation = vtkIdList()

    def add_face(cell, array, tag):
        if not cell.TriangulateLocalIds(0, triangulation):
            raise ValueError(f"Cannot triangulate {cell.GetClassName()}")
        start = len(points)
        local = np.array([triangulation.GetId(i) for i in range(triangulation.GetNumberOfIds())])
        local = local.reshape(-1, 3)
        ids = [cell.GetPointId(i) for i in range(cell.GetNumberOfPoints())]
        points.extend((vtk_to_numpy(cell.GetPoints().GetData()) * scale).tolist())
        values.extend(array[ids].tolist())
        faces.extend((start + local).tolist())
        materials.extend([tag] * len(local))

    def attributes(data):
        tags = data.GetCellData().GetArray("attribute")
        if tags is None:
            raise ValueError("Saved field mesh has no material or boundary attributes")
        return vtk_to_numpy(tags)

    boundary_tags = {}
    for path in snapshot.boundary:
        sheet = grid(path, path.stat().st_mtime_ns, quantity)
        tags = attributes(sheet)
        array = field_values(sheet, quantity, component) if quantity == "J_s" else None
        for i, tag in enumerate(tags):
            cell = sheet.GetCell(i)
            if quantity == "J_s":
                add_face(cell, array, int(tag))
            else:
                boundary_tags[face_key(cell)] = int(tag)

    if quantity == "E":
        # Retain only faces on the skin of the chosen material. Cancel internal faces across
        # partitions before tessellation, without merging point fields at dielectric interfaces.
        skin = {}
        grids = []
        for path in snapshot.pieces:
            data = grid(path, path.stat().st_mtime_ns)
            tags = attributes(data)
            part = len(grids)
            grids.append((data, field_values(data, quantity, component)))
            for i in np.flatnonzero(tags == domain):
                cell = data.GetCell(i)
                for f in range(cell.GetNumberOfFaces()):
                    key = face_key(cell.GetFace(f))
                    if key in skin:
                        del skin[key]
                    else:
                        skin[key] = (part, i, f)
        for key, (part, i, f) in skin.items():
            data, array = grids[part]
            add_face(data.GetCell(i).GetFace(f), array, boundary_tags.get(key))
    return dict(points=points, faces=faces, values=values, materials=materials)
