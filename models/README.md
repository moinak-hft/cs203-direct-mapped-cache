# Integer digit classifier

Run `python tools/train_model.py` from the project root to reproduce the
64-input, 32-hidden ReLU, 10-output MLP using NumPy alone. Training is fixed
at 180 epochs with seed 2026; no test-based early stopping or parameter
search occurs. The training entrypoint fixes BLAS threads to one before
importing NumPy. Byte-identical output is expected with the same Python,
NumPy and BLAS environment; different numerical libraries may round training
updates differently. The JSON records the NumPy version.
The reproduction test compares exported integer parameters, the C header
and functional test metrics. Version strings and floating scale metadata
are allowed to reflect the local numerical environment.

The bundled data uses the official UCI writer-disjoint split. Inputs are
divided by the known bound 16 during floating training. No test mean,
variance or other fitted statistics are used. Quantization scales and the
power-of-two activation shift use trained weights and training samples only.

`digits_q8.json` stores signed 8-bit weights as **flat, input-major matrices**:
`w1[input * 32 + hidden]` and `w2[hidden * 10 + output]`. Biases and final
logits are signed 32-bit. Hardware performs raw integer matrix products;
firmware adds bias and applies the hidden shift and clipping:

```
hidden[j] = min(127, max(0, (sum(input[i] * w1[i,j]) + b1[j]) >> hidden_shift))
logit[j]  = sum(hidden[i] * w2[i,j]) + b2[j]
prediction = first index with the maximum logit
```

The shift is arithmetic (floor for negative integers). Final logits are
unnormalized integer scores, **not probabilities**. The model contains 2,368
weights and 42 int32 biases: 2,536 bytes excluding JSON/metadata and input
storage. Each inference performs 2,368 useful multiply-accumulate operations.

`metrics.json` contains actual results on all 1,797 held-out UCI test samples.
These are dataset results rather than a guarantee for mouse-drawn digits,
which have a different distribution and require matching centering, scale,
stroke width and intensity. The sample in `model.h` is test index 0, selected
by position rather than cherry-picked from model predictions.

Exports: `models/digits_q8.json`, `models/metrics.json`,
`models/digits_q8.sha256`, and `firmware/generated/model.h`. The Python
integer inference reference has no NumPy runtime dependency. NumPy is needed
only for retraining. Dataset attribution and hashes are in `data/`.
