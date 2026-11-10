"""Model evidence: held-out accuracy, integer semantics and real reproduction."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from neurotile.dataset import load_dataset
from neurotile.model import load_model, predict, validate_model


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_model()

    def test_export_matches_firmware_and_hash(self):
        expected_hash = (ROOT / "models" / "digits_q8.sha256").read_text().split()[0]
        self.assertEqual(hashlib.sha256((ROOT / "models" / "digits_q8.json").read_bytes()).hexdigest(), expected_hash)
        header = (ROOT / "firmware" / "generated" / "model.h").read_text()
        for field in ("w1", "w2", "b1", "b2", "sample_input"):
            match = re.search(r"nt_" + field + r"\[\d+\] = \{([^}]+)\}", header, re.S)
            self.assertIsNotNone(match)
            values = [int(v) for v in re.findall(r"-?\d+", match.group(1))]
            self.assertEqual(values, self.model[field])
        self.assertIn(f"#define NT_HIDDEN_SHIFT {self.model['hidden_shift']}", header)

    def test_original_dataset_split_and_integrity(self):
        for split, count in (("train", 3823), ("test", 1797)):
            inputs, labels = load_dataset(split)
            self.assertEqual(len(inputs), count)
            self.assertEqual(len(labels), count)
            self.assertEqual(set(labels), set(range(10)))
        with self.assertRaises(ValueError):
            load_dataset("validation")

    def test_actual_held_out_integer_accuracy(self):
        inputs, labels = load_dataset("test")
        correct = sum(predict(values, self.model)["prediction"] == label
                      for values, label in zip(inputs, labels))
        self.assertEqual(correct, self.model["metrics"]["correct_test_predictions"])
        self.assertEqual(correct / len(labels), self.model["metrics"]["quantized_test_accuracy"])
        self.assertGreaterEqual(correct / len(labels), 0.90)

    def test_sample_exact_golden_reference(self):
        result = predict(self.model["sample_input"], self.model)
        self.assertEqual(result, self.model["sample_reference"])
        self.assertEqual(result["logits"], [14829, -20313, -2233, -8822, -10038,
                                            -927, -5241, -5375, -841, -1601])

    def test_signed_products_bias_shift_clip_and_matrix_layout(self):
        fixture = {"input_size": 64, "hidden_size": 32, "output_size": 10,
                   "hidden_shift": 6, "w1": [0] * 2048, "w2": [0] * 320,
                   "b1": [0] * 32, "b2": [0] * 10}
        fixture["w1"][0] = -127
        fixture["b1"][0] = 200
        fixture["w1"][1 * 32 + 1] = 127
        fixture["b1"][2] = 100000
        fixture["b1"][3] = -1
        fixture["w1"][63 * 32 + 4] = -128
        fixture["b1"][4] = 2047
        fixture["w2"][0 * 10 + 3] = -128
        fixture["w2"][1 * 10 + 4] = 127
        fixture["w2"][2 * 10 + 8] = -127
        fixture["b2"][9] = 6000
        validate_model(fixture)
        features = [0] * 64
        features[0], features[1], features[63] = 1, 16, 16
        result = predict(features, fixture)
        self.assertEqual(result["hidden"], [1, 31, 127] + [0] * 29)
        self.assertEqual(result["logits"], [0, 0, 0, -128, 3937, 0, 0, 0, -16129, 6000])
        self.assertEqual(result["prediction"], 9)

    def test_invalid_inputs_and_model_are_rejected(self):
        for features in ([0] * 63, [17] + [0] * 63, [-1] + [0] * 63,
                         [0.5] + [0] * 63, [True] + [0] * 63):
            with self.assertRaises(ValueError):
                predict(features, self.model)
        damaged = dict(self.model, w1=[0])
        with self.assertRaises(ValueError):
            validate_model(damaged)

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "NumPy needed only for retraining")
    def test_fixed_seed_training_reproduces_integer_model_and_metrics(self):
        with tempfile.TemporaryDirectory(prefix="neurotile-model-") as output:
            process = subprocess.run([sys.executable, str(ROOT / "tools" / "train_model.py"),
                                      "--output-root", output], cwd=ROOT, capture_output=True,
                                     text=True, timeout=120)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            reproduced = json.loads((Path(output) / "models" / "digits_q8.json").read_text())
            # The public reproducibility contract covers the integer model,
            # emitted firmware and functional evaluation. Floating training
            # scale metadata and the recorded NumPy version are environment
            # dependent; byte-identical JSON requires the same numerical stack.
            for field in ("input_size", "hidden_size", "output_size", "hidden_shift",
                          "w1", "b1", "w2", "b2", "sample_input", "sample_label",
                          "sample_reference"):
                self.assertEqual(reproduced[field], self.model[field], field)
            for field in ("correct_test_predictions", "train_samples", "test_samples",
                          "quantized_test_accuracy", "confusion_matrix"):
                self.assertEqual(reproduced["metrics"][field], self.model["metrics"][field], field)
            self.assertEqual((Path(output) / "firmware" / "generated" / "model.h").read_bytes(),
                             (ROOT / "firmware" / "generated" / "model.h").read_bytes())


if __name__ == "__main__":
    unittest.main()
