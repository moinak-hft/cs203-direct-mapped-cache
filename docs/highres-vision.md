# Larger-canvas single- and two-digit recognition

Version 2 uses a **128×64 drawing image** and a genuine **28×28 model input per
digit**. Host preprocessing locates up to two regions; Python, C or RTL then
classifies the normalized crops. It is not an RTL camera pipeline or a learned
sequence detector.

## Use the interface

```sh
python tools/serve.py
```

Open http://127.0.0.1:8000. Draw with mouse, pen or touch. The brush supports 2–10
canvas pixels; erasing uses a larger stroke. Undo restores previous drawing,
example or import states, with up to 24 stored states. Keyboard users can focus
the canvas, move with arrows and paint using Space. The initial example uses
consecutive held-out MNIST samples rather than images selected for success.

Select a mode:

- **One digit:** treat the foreground as one region.
- **Two digits:** seek two regions, with an ambiguity warning when the cut is
  weak or only one foreground region is found.
- **Auto detect:** split when a clear low-ink gap separates the regions;
  otherwise retain one crop.

Leave some space between digits. For touching digits, enable **Adjust the digit
split** and move the slider until each preview contains the intended digit.
Leading zeros are retained because the result is assembled as text. Changes
invalidate the previous result; run recognition again after editing or changing
the mode/split.

Select either normalized crop to inspect its actual activations and logits.
The first largest logit wins. Alternatives are sorted scores rather than
calibrated probabilities.

## PNG and JPEG import

The browser accepts PNG/JPEG files up to 10 MB. It decodes and proportionally
resizes them within the canvas, converts RGB to grayscale and estimates the
background polarity from the image edge. Light backgrounds are inverted so
the model receives bright ink on a dark background. Surrounding canvas pixels
become zero ink. No external upload service is used; the local API receives
the resulting pixel array.

Use a reasonably clean, cropped image. Edge-polarity handling is not a document
scanner: shadows, patterned backgrounds, perspective, colored text and digits
touching an image border can interfere. Transparent images are composited onto
a white import background before grayscale conversion.

## Deterministic image preparation

`python/neurotile/vision.py` implements these operations:

1. **Validate.** Image width is 28–256 and height 28–128. Supply an exact
   width×height flat list of integer ink values 0–16. The UI uses 128×64.
2. **Clean noise.** An 8-connected mask uses intensity ≥2. Components smaller
   than a threshold relative to the largest are removed. Adjacent faint
   antialiasing is retained.
3. **Find foreground.** Significant pixels define bounding boxes. Empty or
   noise-only input returns `status: "blank"`, zero crops and no digit guess.
4. **Choose a split.** A vertical ink projection seeks a broad low-ink valley
   with meaningful ink on both sides. Auto mode requires a clear gap; two-digit
   mode can use a sufficiently low-ink cut with a warning. A manual column
   overrides the decision outside single mode.
5. **Normalize.** Preserve aspect ratio, fit each region into 20×20 using area
   resampling, place it inside 28×28 and shift its ink center of mass toward
   the center. Pixels remain integers in 0–16.
6. **Classify left to right.** Supply one or two crops as a batch to the selected
   backend. The larger model computes 784→64→10.

Boxes use half-open extents: `x`, `y`, `width`, `height`. Normalized crops contain
exactly 784 row-major values. Their previews show the actual model inputs,
helping distinguish an incorrect crop from a classifier error.

The classifier learned already-normalized MNIST digits. Re-normalizing a
composed image can change its pixels and prediction even when it originated
from MNIST. Original-dataset accuracy and full canvas-pair accuracy are therefore
separate measurements.

## API

`GET /api/hd/sample?index=0&digits=2` returns a 128×64 image containing consecutive
official test examples, its expected label string and source indices. `digits`
is 1 or 2. The second index wraps at the end of the test set. The legacy 8×8
example endpoint remains `GET /api/sample`.

`POST /api/recognize` accepts `pixels`, `width`, `height`, `mode`, `backend` and
optional `split`. A 128×64 request needs **8,192 integers** in its pixel array.
`mode` is `single`, `double` or `auto`; `backend` is `reference`, `c` or `rtl`.
Omit `split` for automatic selection. A supplied split is an integer column
strictly inside the canvas.

The response includes `text`, `predictions`, `status`, `batch_size`, backend,
warnings, timing scope and `segmentation`. Each entry in `digits` contains its
box, normalized pixels, prediction, actual hidden activations, logits,
top-three alternatives and relative score margin. Empty input returns before
classifier invocation. Small score gaps and wide/ambiguous regions produce
inspection messages.

The score-gap heuristic is:

```text
(largest_logit - second_largest_logit)
    / max(1, abs(largest_logit), abs(second_largest_logit))
```

It is not a probability and can exceed 1 when scores have opposite signs. A
small gap suggests inspecting the crop; a large gap does not establish
correctness or out-of-distribution detection.

## What each backend executes

| Backend | Execution and evidence |
|---|---|
| Python | Exact host integer model; no hardware-cycle measurement |
| Native C | Compiled 784→64→10 reference returning its own activations/logits, checked against Python |
| Verilog | Actual K-blocked batched accelerator simulation returning outputs/counters, checked against Python |

Two crops form two rows of a matrix operation in RTL, sharing weights and
launches. Thirteen input blocks cover the first layer, with INT32 sums combined
before activation. See [highres-hardware.md](highres-hardware.md). All image
segmentation and normalization precede that hardware work.

## Evaluation and limits

The committed model reaches **96.42% (9,642/10,000)** on the untouched official
MNIST single-digit test set. A separate experiment composes the first 200 test
images into 100 consecutive pairs, runs segmentation/normalization, then
classifies them. It reports **94/100 exact pairs**, **97% digit accuracy** and
**100/100 two-crop detections**. Saved examples include errors; failures are not
filtered out.

```sh
python tools/benchmark_hd.py --reference-only --pairs 100
python tools/benchmark_hd.py
```

The first command runs reference evaluation. The second also measures actual
RTL batching. Results go to `reports/recognition.json` and
`reports/hd_benchmark.json`. A larger `--pairs` value evaluates a larger
consecutive subset rather than reusing the 100-pair result.

These examples are synthetically separated digits, not a natural two-digit
handwriting dataset. At most two crops are supported. Arbitrary text, letters,
decimal points, signs and longer sequences are outside this recognition
contract. Touching/overlapping digits, difficult backgrounds and distribution
changes remain practical limits. No calibrated confidence, general unknown-input
detector or real-time camera pipeline is claimed.

Legacy CPU/UART experiments keep using the original 8×8 network unless their
command explicitly selects high-resolution firmware. The new browser API does
not change the legacy 64-pixel UART request format.
