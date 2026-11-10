# Attribution and licenses

Original project source is MIT licensed. The following material retains its
upstream license. No ownership of third-party work is claimed.

## PicoRV32

- Author: Claire Xenia Wolf and upstream contributors.
- Source: https://github.com/YosysHQ/picorv32
- Pinned commit: `ef203c2b0a3fb793280f5114941416c425c5b461`.
- Files: `third_party/picorv32/picorv32.v` and `COPYING`, unmodified.
- License: ISC, reproduced in `third_party/picorv32/COPYING` and source header.
- Upstream is archived; this project uses a pinned educational reference core.

## Optical Recognition of Handwritten Digits

- E. Alpaydin and C. Kaynak (1998), UCI Machine Learning Repository.
- DOI: https://doi.org/10.24432/C50P49
- License: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/.
- Training and test files are recompressed without changing rows or values.
- Dataset attribution, transformations and SHA256 hashes: `data/README.md`
  and `data/provenance.json`.
- Trained weight/header exports derive from this attributed dataset.

## MNIST: high-resolution version 2 model

- Authors: Yann LeCun, Corinna Cortes and Christopher J. C. Burges.
- Original homepage: http://yann.lecun.com/exdb/mnist/.
- Dataset card: https://huggingface.co/datasets/ylecun/mnist/blob/main/README.md.
  The ylecun card identifies the dataset license as **MIT**.
- Original IDX archive mirror: https://ossci-datasets.s3.amazonaws.com/mnist/.
- Bundled data: `data/mnist_train.u8.gz`, a stratified 20,000-image subset of
  official training data; `data/mnist_test.u8.gz`, all 10,000 official test images.
- Transformation: intensities 0–255 become 0–16 through the fixed expression
  `(pixel*16+127)//255`. Labels and official test ordering remain unchanged.
  Gzip timestamps are fixed to zero.
- Attribution, original training indices, source/hashes and binary format:
  `data/mnist_README.md`, `data/mnist_train_indices.json` and
  `data/mnist_provenance.json`.
- Trained model, C header and example exports derive from this attributed
  dataset. Original dataset work is not claimed as project-authored content.

## Architectural inspiration

The small original Verilog accelerator takes conceptual inspiration from tiled
matrix accelerators, including Berkeley Gemmini. The memory lab references
IP-classified prefetching, and the isolation lab references DAWG. Their source
code is not included. See README references for the original publications.
