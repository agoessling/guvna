"""Read the final Palace driven port response for an explicitly opened run."""
import csv
import math
import re

from viewer.inputs import read_deck


def sweep(source, directory=None):
    if source.kind != "run" and directory is None:
        return []
    deck = source.path if source.kind == "case" else source.path / "palace.json"
    if not deck.is_file():
        return []
    output = read_deck(deck).get("Problem", {}).get("Output", "postpro")
    path = (directory or source.path / output) / "port-S.csv"
    if not path.is_file():
        return []

    with path.open(newline="") as stream:
        rows = csv.DictReader(stream, skipinitialspace=True)
        headers = rows.fieldnames or []
        if "f (GHz)" not in headers:
            raise ValueError(f"{path}: missing frequency in GHz")
        traces = {}
        for name in headers:
            match = re.fullmatch(r"\|(S\[(\d+)\]\[(\d+)\])\| \(dB\)", name)
            if match:
                phase = f"arg({match[1]}) (deg.)"
                traces[name, phase] = dict(port=int(match[2]), drive=int(match[3]), samples=[])
        for row in rows:
            ghz = float(row["f (GHz)"])
            if not math.isfinite(ghz):
                raise ValueError(f"{path}: invalid frequency")
            for (name, phase), trace in traces.items():
                if not (row.get(name) or "").strip():
                    continue
                db = float(row[name])
                if math.isnan(db) or db == math.inf:
                    continue
                angle = float(row[phase]) if (row.get(phase) or "").strip() else math.nan
                trace["samples"].append([ghz, db if math.isfinite(db) else "-inf",
                                         angle if math.isfinite(angle) else None])
        for trace in traces.values():
            trace["samples"].sort(key=lambda sample: sample[0])
        return [t for t in traces.values() if t["samples"]]
