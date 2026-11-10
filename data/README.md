# Bundled digit data

E. Alpaydin and C. Kaynak (1998), **Optical Recognition of Handwritten
Digits**, UCI Machine Learning Repository,
<https://doi.org/10.24432/C50P49>.

Dataset license: **Creative Commons Attribution 4.0 International**
(CC BY 4.0), <https://creativecommons.org/licenses/by/4.0/>.
The UCI dataset page explicitly identifies this license:
<https://archive.ics.uci.edu/dataset/80/optical+recognition+of+handwritten+digits>.
This attribution applies to the dataset; project source has its own license.

The original `optdigits.tra` and `optdigits.tes` members are recompressed as
`digits_train.csv.gz` and `digits_test.csv.gz` with gzip modification time 0.
No feature values, labels, row ordering or sample membership were changed.
Every row has 64 integer pixel counts (0..16) followed by the label (0..9).

The original split contains 3,823 training samples from 30 writers and 1,797
test samples from 13 **different** writers. It is stronger than randomly
resplitting scikit-learn's 1,797-sample `load_digits` subset, which itself
contains only the original UCI test partition. The test partition is used
only after training and training-only quantization calibration are complete.

`provenance.json` records the original download, archive SHA-256, original
members' uncompressed hashes and bundled compressed file hashes. The Python
loader verifies bundled hashes by default. Bundled data supports offline
training; downloads are unnecessary after checkout.
