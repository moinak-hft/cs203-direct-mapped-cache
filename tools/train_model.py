#!/usr/bin/env python3
"""Offline reproducible NumPy-only trainer and C/JSON exporter."""

import argparse
import os
from pathlib import Path
import sys

# Set before importing NumPy. Override existing multithread BLAS settings only
# for this standalone training process so reduction order is reproducible.
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from neurotile.training import train_and_export  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--epochs", type=int, default=180)
    parser.add_argument("--output-root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("--epochs must be positive")
    train_and_export(args.output_root, seed=args.seed, epochs=args.epochs)


if __name__ == "__main__":
    main()
