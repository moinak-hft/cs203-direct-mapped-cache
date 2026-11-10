# Genuine 28×28 MNIST data

MNIST handwritten digit database by **Yann LeCun, Corinna Cortes and
Christopher J. C. Burges**. Original homepage:
http://yann.lecun.com/exdb/mnist/.

The [ylecun/mnist dataset card](https://huggingface.co/datasets/ylecun/mnist/blob/main/README.md)
identifies the dataset license as **MIT**. This attribution belongs to the
dataset and its derivatives; the project does not claim authorship of MNIST.
The [MIT license text](https://opensource.org/license/mit) describes the license.
Original compressed IDX files were obtained from the PyTorch/OSSCI mirror:
https://ossci-datasets.s3.amazonaws.com/mnist/.

## Exactly what is bundled

- `mnist_train.u8.gz`: **20,000 samples** drawn only from the original60,000
  training partition, with exactly2,000 samples per digit.
- `mnist_test.u8.gz`: **all10,000 official test samples**, in original order.
- `mnist_train_indices.json`: sorted original training indices. Selection uses
  `random.Random(2026)`, class-by-class sampling; the explicit indices make the
  subset auditable without depending on an implicit shuffle.
- `mnist_provenance.json`: original archive URLs, upstream MD5 values, observed
  SHA256 hashes and integrity hashes for the bundled transformed data.

Each gzip payload is a sequence of785-byte rows: one label byte followed by784
row-major28×28 pixel bytes. The original grayscale intensity0–255 is quantized
by the fixed transform **`(pixel*16+127)//255`**, producing integer0–16. Labels,
official test order and official partition membership are unchanged. Gzip
timestamps are fixed to zero for reproducible byte exports.

Selection, floating-model training and quantization calibration use training
data only. The test partition is evaluated at the end; it is not used for
normalization fitting, hyperparameter search or early stopping. This model
is trained on the20,000-sample subset, not all60,000 original training images.

The runtime loader is Python-stdlib only and checks compressed SHA256 hashes.
Bundling these files makes reference inference, examples and retraining work
offline after checkout. To explicitly rebuild the bundle from original IDX
archives, use:

```sh
python tools/train_hd_model.py --prepare-data
```

That optional command performs network downloads and then trains. Ordinary
`python tools/train_hd_model.py` uses the bundled data without downloading.
