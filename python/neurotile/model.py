"""Portable integer reference: deliberately requires only the Python stdlib.

Weights are flat, input-major row-major matrices. Negative right shifts use
Python's floor arithmetic, matching the firmware helper and signed RTL.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "models" / "digits_q8.json"


def validate_model(model: dict) -> None:
    for field in ("input_size", "hidden_size", "output_size", "hidden_shift"):
        if type(model.get(field)) is not int:
            raise ValueError(f"Model {field} must be an integer")
    ni, nh, no = (model[k] for k in ("input_size", "hidden_size", "output_size"))
    if (ni, nh, no) != (64, 32, 10):
        raise ValueError("This demo requires a 64 -> 32 -> 10 model")
    if not 0 <= model["hidden_shift"] <= 24:
        raise ValueError("hidden_shift is outside supported range 0..24")
    for field, count, lower, upper in (
        ("w1", ni * nh, -128, 127), ("b1", nh, -(2**31), 2**31 - 1),
        ("w2", nh * no, -128, 127), ("b2", no, -(2**31), 2**31 - 1),
    ):
        values = model.get(field)
        if not isinstance(values, list) or len(values) != count:
            raise ValueError(f"Model {field} must contain {count} flat values")
        if any(type(v) is not int or not lower <= v <= upper for v in values):
            raise ValueError(f"Model {field} contains an invalid integer")
    # All backends use signed int32 accumulators. Reject models that could
    # overflow for any accepted input; Python's unbounded ints must not hide it.
    for weights, biases, inputs, outputs, max_input in (
        (model['w1'],model['b1'],ni,nh,16),
        (model['w2'],model['b2'],nh,no,127),
    ):
        for j in range(outputs):
            bound=abs(biases[j])+max_input*sum(abs(weights[i*outputs+j]) for i in range(inputs))
            if bound>2**31-1:
                raise ValueError('Model may overflow a signed int32 accumulator')


def load_model(path: str | Path | None = None) -> dict:
    with Path(path or DEFAULT_MODEL).open(encoding="utf-8") as handle:
        model = json.load(handle)
    validate_model(model)
    return model


def predict(features: list[int], model: dict) -> dict:
    """Return exact integer hidden activations, logits and first-max prediction."""
    ni, nh, no = model["input_size"], model["hidden_size"], model["output_size"]
    if len(features) != ni:
        raise ValueError(f"Expected {ni} pixel intensities")
    if any(type(value) is not int or not 0 <= value <= 16 for value in features):
        raise ValueError("Pixel intensities must be integers in 0..16")
    w1, w2, shift = model["w1"], model["w2"], model["hidden_shift"]
    hidden = []
    for j in range(nh):
        total = model["b1"][j] + sum(features[i] * w1[i * nh + j] for i in range(ni))
        hidden.append(max(0, min(127, total >> shift)))
    logits = [
        model["b2"][j] + sum(hidden[i] * w2[i * no + j] for i in range(nh))
        for j in range(no)
    ]
    return {"prediction": max(range(no), key=lambda j: logits[j]),
            "hidden": hidden, "logits": logits}
