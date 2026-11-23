"""Read the labeled Palace four-port output and export a real-reference Touchstone 1.x matrix."""

import cmath
import csv
import json
import math
import re
from xml.etree import ElementTree as ET


PORTS = range(1, 5)
ROLES = ("input", "through", "near-end pickup", "far-end pickup")
DIRECTIVITY_PORTS = {"drive": 1, "coupled": 3, "isolated": 4}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def read_matrices(path, frequencies):
    matrices = []
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, skipinitialspace=True)
        expected = {"f (GHz)"}
        for i in PORTS:
            for j in PORTS:
                expected.update({f"|S[{i}][{j}]| (dB)", f"arg(S[{i}][{j}]) (deg.)"})
        columns = reader.fieldnames or []
        if len(columns) != len(expected) or set(columns) != expected:
            raise ValueError(f"Incomplete or unexpected four-port CSV header in {path}")
        for f, row in zip(frequencies, reader, strict=True):
            if not math.isclose(f, float(row["f (GHz)"]), rel_tol=1e-8):
                raise ValueError(f"Unexpected frequency or ordering in {path}")
            matrix = []
            for i in PORTS:
                values = []
                for j in PORTS:
                    db = float(row[f"|S[{i}][{j}]| (dB)"])
                    phase = math.radians(float(row[f"arg(S[{i}][{j}]) (deg.)"]))
                    value = cmath.rect(10**(db / 20), phase)
                    if not cmath.isfinite(value):
                        raise ValueError(f"Nonfinite S[{i}][{j}] at {f} GHz")
                    values.append(value)
                matrix.append(values)
            matrices.append(matrix)
    return matrices


def max_singular_value(s):
    # The sign of the smallest eigenvalue of tI - S* S brackets sigma_max squared.
    # A Cholesky factor exists exactly when the Hermitian matrix is positive definite.
    g = [[sum(row[i].conjugate() * row[j] for row in s) for j in range(4)] for i in range(4)]
    low = 0.0
    high = sum(g[i][i].real for i in range(4))
    for _ in range(52):
        t = (low + high) / 2
        l = [[0j] * 4 for _ in range(4)]
        for i in range(4):
            for j in range(i):
                inner = sum(l[i][k] * l[j][k].conjugate() for k in range(j))
                l[i][j] = (-g[i][j] - inner) / l[j][j]
            pivot = t - g[i][i].real - sum(abs(x)**2 for x in l[i][:i])
            if pivot <= 0:
                low = t
                break
            l[i][i] = math.sqrt(pivot)
        else:
            high = t
    return math.sqrt(high)


def loss(value):
    return -20 * math.log10(abs(value)) if value else None


def sample_diagnostics(f, s):
    drive = DIRECTIVITY_PORTS["drive"] - 1
    coupling = loss(s[DIRECTIVITY_PORTS["coupled"] - 1][drive])
    isolation = loss(s[DIRECTIVITY_PORTS["isolated"] - 1][drive])
    reciprocal = max(abs(s[i][j] - s[j][i]) for j in range(4) for i in range(j))
    return {
        "frequency_ghz": f,
        "coupling_loss_db": coupling,
        "isolation_db": isolation,
        "directivity_db": isolation - coupling if None not in (coupling, isolation) else None,
        "return_loss_db": loss(s[0][0]),
        "through_loss_db": loss(s[1][0]),
        "max_reciprocity_error": reciprocal,
        "max_singular_value": max_singular_value(s),
    }


def field_files(run, saved, ranks):
    fields = []
    for drive in PORTS:
        folder = run / "postpro/paraview/driven" / f"excitation_{drive}"
        series = ET.parse(folder / f"excitation_{drive}.pvd")
        seen = []
        for item in series.findall("./Collection/DataSet"):
            timestep = float(item.attrib["timestep"])
            # VTK collections can round a GHz timestamp more coarsely than the port CSV.
            matches = [f for f in saved if math.isclose(f, timestep, rel_tol=5e-6)]
            if not matches:
                continue
            if len(matches) != 1:
                raise ValueError(f"Ambiguous PVD timestamp {timestep} GHz")
            f = matches[0]
            path = folder / item.attrib["file"]
            grid = ET.parse(path)
            names = {a.get("Name") for a in grid.findall(".//PPointData/PDataArray")}
            pieces = [path.parent / node.attrib["Source"] for node in grid.findall(".//Piece")]
            if not {"E_real", "E_imag"} <= names:
                raise ValueError(f"Missing complex electric field in {path}")
            if len(pieces) != ranks or not all(p.is_file() for p in pieces):
                raise ValueError(f"Missing parallel field pieces for {path}")
            seen.append(f)
            fields.append({"excitation": drive, "frequency_ghz": f,
                           "path": str(path.relative_to(run))})
        if sorted(seen) != saved:
            raise ValueError(f"Missing saved frequencies for excitation {drive}: {seen}")
    return fields


def validate_solver(run, frequencies, ranks):
    meta = json.loads((run / "postpro/palace.json").read_text())
    logfile = (run / "solver.log").read_text()
    gmres = re.findall(r"^GMRES solver converged in (\d+) iterations", logfile, re.M)
    count = 4 * len(frequencies)
    if len(gmres) != count or meta["LinearSolver"]["TotalSolves"] != count:
        raise ValueError(f"Expected {count} converged independent solves; see {run}/solver.log")
    drives = [(i, info["LumpedPort"]) for group in meta["Excitations"] for i, info in group]
    if drives != [(i, [i]) for i in PORTS]:
        raise ValueError(f"Unexpected Palace excitation groups: {drives}")
    if meta["Problem"]["MPISize"] != ranks or meta["Problem"]["OpenMPThreads"] != 1:
        raise ValueError("Palace MPI/OpenMP settings differ from the requested run")
    return {
        "palace_version": meta["GitTag"],
        "linear_solves": count,
        "gmres_iterations": [int(x) for x in gmres],
        "degrees_of_freedom": meta["Problem"]["DegreesOfFreedom"],
        "mesh_elements": meta["Problem"]["MeshElements"],
        "peak_node_mib": meta["PeakNodeMemoryMegabytes"]["Max"],
    }


def write_touchstone(path, frequencies, matrices):
    # For four-port Touchstone 1.x each frequency uses four rows, each in S[out][in] order.
    with path.open("w") as stream:
        for i, role in zip(PORTS, ROLES):
            stream.write(f"! Port {i} = {role}; PCB end-face lumped reference, 50 ohm\n")
        stream.write("# GHz S RI R 50\n")
        for f, matrix in zip(frequencies, matrices, strict=True):
            for i, row in enumerate(matrix):
                prefix = f"{f:.12g}  " if i == 0 else "  "
                pairs = [f"{z.real:.12e} {z.imag:.12e}" for z in row]
                stream.write(prefix + "  ".join(pairs) + "\n")
