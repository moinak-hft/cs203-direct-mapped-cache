# High-resolution integer model

The new model learns from genuine **28×28 MNIST images**. It does not enlarge
the old8×8 UCI samples and call the result higher-resolution learning. Each
digit contributes784 model pixels, compared with64 in the legacy classifier.
Canvas segmentation and normalization are separate preprocessing operations;
the classifier accepts exactly784 integer pixel intensities in0–16.

## Model and numerical contract

```text
784 inputs → 64 ReLU hidden neurons → 10 signed integer class scores
```

Weights are signed INT8; biases and dot-product results are signed INT32.
Matrices are flat, input-major row-major: `w1[input*64+hidden]` and
`w2[hidden*10+class]`. Hidden activations are:

```text
h[j] = clip_0_127((sum(pixel[i]*w1[i,j]) + b1[j]) >> hidden_shift)
logit[j] = sum(h[i]*w2[i,j]) + b2[j]
prediction = first class index with the largest logit
```

The shift is arithmetic floor division. The committed model's shift is9.
The validator rejects unsupported dimensions, malformed integer parameters,
unsupported shifts and potential INT32 overflow for any accepted pixel input.
Python reference inference requires no NumPy; the training/exporter does.

This is a50,816-MAC network with51,112 bytes of weights and biases, excluding
input/activation buffers and JSON metadata. Inputs are genuinely28×28, while
weight/input arithmetic stays efficient8-bit integer arithmetic. The existing
RTL engine can evaluate the first layer in K-blocks of at most64 inputs; the
host accumulates partial INT32 sums before applying the hidden activation.

## Measured result

The fixed40epoch NumPy-only training run achieved:

| Metric | Measured value |
|---|---:|
| Training subset |20,000 official-training images,2,000 per class|
| Official test images |10,000|
| Floating test accuracy |96.35%|
| Quantized test accuracy |**96.42% (9,642/10,000)**|
| Useful MACs per digit |50,816|
| Parameter bytes |51,112|

The original official test partition remains untouched during training and
calibration. The schedule is40epochs, batch128, Adam learning rate0.0015,
L2 coefficient0.0001, seed2026. No test-based checkpoint selection, early
stopping or hyperparameter search occurred. Quantizer scales use trained
weights; the hidden shift uses the maximum hidden accumulator over training
samples only. `models/mnist_metrics.json` records the complete confusion matrix.

The test accuracy concerns individual original MNIST digits. It is **not** a
measured claim about all two-digit handwriting, arbitrary uploads, touching
digits or preprocessing robustness. Pair recognition composes two classifier
outputs; its exact string accuracy depends on both segmentation and each digit.
Mouse drawings and photographed numbers differ from MNIST's input distribution.

## Reproduce and inspect

```sh
python -m pip install -r requirements-training.txt
python tools/train_hd_model.py
python -m unittest discover -s tests -p test_hd_model.py -v
```

To train into another output folder without changing committed exports:

```sh
python tools/train_hd_model.py --output-root work/hd-retrain
```

The entrypoint fixes BLAS thread counts before importing NumPy. Fresh training
with the same numerical environment reproduces integer weights, biases, shift,
firmware header and functional metrics. Different floating libraries alter
float32 training reductions, so cross-platform retraining can produce different
integer weights and slightly different accuracy. A separate Linux NumPy2.3.5
run reached96.44%; the committed Windows NumPy2.4.4 model remains96.42%. This
is numerical implementation variation, not another selected test-tuned model.
The regression trains twice locally and compares those exports; separately it
checks the committed artifact hash, firmware arrays and all10,000 golden test
predictions. Source/data provenance and hashes are included.

Public APIs:

```python
from neurotile.hd_model import load_hd_model, predict_hd
from neurotile.hd_dataset import load_hd_dataset

model = load_hd_model()
result = predict_hd(model['sample_input'], model)
images, labels = load_hd_dataset('test')
```

The model JSON is `models/mnist_q8.json`, with a separate SHA256 file. The C
export is `firmware/generated/mnist_model.h` using `HD_INPUTS`, `HD_HIDDEN`,
`HD_OUTPUTS`, `HD_HIDDEN_SHIFT` and `hd_*` arrays. The first original test image
(index0, label7) is the default sample. UI examples choose the first test image
per digit by position, independently of predictions, rather than cherry-picking
images the model gets right.
