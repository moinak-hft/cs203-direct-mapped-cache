"""Read the bundled, attributed UCI writer-disjoint train/test digit split."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_dataset(split: str = "test", verify: bool = True) -> tuple[list[list[int]], list[int]]:
    """Load official train (3823) or test (1797); never reshuffle/split writers."""
    if split not in ("train", "test"):
        raise ValueError("split must be train or test")
    path = ROOT / "data" / f"digits_{split}.csv.gz"
    if verify:
        metadata = json.loads((ROOT / "data" / "provenance.json").read_text(encoding="utf-8"))
        expected = metadata["bundled_files"][path.name]["sha256"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Dataset SHA-256 mismatch: {path.name}")
    with gzip.open(path, "rt", encoding="ascii", newline="") as handle:
        rows = [[int(value) for value in row] for row in csv.reader(handle)]
    if any(len(row) != 65 or any(v < 0 or v > 16 for v in row[:64])
           or not 0 <= row[-1] <= 9 for row in rows):
        raise ValueError("Malformed digits dataset")
    return [row[:64] for row in rows], [row[-1] for row in rows]
