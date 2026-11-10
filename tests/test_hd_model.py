"""Genuine28x28 model evidence: official split, all10k predictions and exports."""
from __future__ import annotations
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from neurotile.hd_dataset import load_hd_dataset
from neurotile.hd_model import load_hd_model,predict_hd,validate_hd_model


class HighResolutionModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.model=load_hd_model()

    def test_official_test_partition_and_training_only_subset_integrity(self):
        train,train_y=load_hd_dataset('train');test,test_y=load_hd_dataset('test')
        self.assertEqual((len(train),len(test)),(20000,10000))
        self.assertEqual(Counter(train_y),{digit:2000 for digit in range(10)})
        self.assertEqual(test_y[:10],[7,2,1,0,4,1,4,9,5,9])
        indices=json.loads((ROOT/'data/mnist_train_indices.json').read_text())
        self.assertEqual(len(indices),20000);self.assertEqual(indices,sorted(set(indices)))
        self.assertTrue(all(0<=i<60000 for i in indices))
        self.assertEqual(len(test[0]),784)
        with self.assertRaises(ValueError):load_hd_dataset('validation')

    def test_actual_all10000_official_test_predictions(self):
        rows,labels=load_hd_dataset('test')
        correct=sum(predict_hd(row,self.model)['prediction']==label for row,label in zip(rows,labels))
        self.assertEqual(correct,9642)
        self.assertEqual(correct,self.model['metrics']['correct_test_predictions'])
        self.assertEqual(correct/len(rows),self.model['metrics']['quantized_test_accuracy'])

    def test_header_hash_layout_and_first_position_sample(self):
        payload=(ROOT/'models/mnist_q8.json').read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(),(ROOT/'models/mnist_q8.sha256').read_text().split()[0])
        header=(ROOT/'firmware/generated/mnist_model.h').read_text()
        for field in ['w1','b1','w2','b2','sample_input']:
            match=re.search(r'hd_'+field+r'\[\d+\] = \{([^}]+)\}',header,re.S)
            self.assertIsNotNone(match)
            self.assertEqual(list(map(int,re.findall(r'-?\d+',match.group(1)))),self.model[field])
        self.assertIn('#define HD_INPUTS 784',header)
        shift_match=re.search(r'^#define HD_HIDDEN_SHIFT (\d+)$',header,re.M)
        self.assertIsNotNone(shift_match)
        self.assertEqual(int(shift_match.group(1)),self.model['hidden_shift'])
        result=predict_hd(self.model['sample_input'],self.model)
        self.assertEqual(result,self.model['sample_reference'])
        self.assertEqual(result['prediction'],7)
        self.assertEqual(result['logits'],[-1360,-4417,565,-664,-6772,-1186,-8946,5060,-1764,-901])

    def test_signed_784column_layout_and_integer_activation_semantics(self):
        fixture={'input_size':784,'hidden_size':64,'output_size':10,'hidden_shift':8,
                 'w1':[0]*50176,'w2':[0]*640,'b1':[0]*64,'b2':[0]*10}
        fixture['w1'][0]=-128;fixture['b1'][0]=385
        fixture['w1'][783*64+1]=127;fixture['b1'][2]=100000;fixture['b1'][3]=-1
        fixture['w2'][3]=-128;fixture['w2'][10+4]=127;fixture['w2'][20+8]=-127
        fixture['b2'][9]=6000
        pixels=[0]*784;pixels[0]=1;pixels[783]=16
        validate_hd_model(fixture);result=predict_hd(pixels,fixture)
        self.assertEqual(result['hidden'],[1,7,127]+[0]*61)
        self.assertEqual(result['logits'],[0,0,0,-128,889,0,0,0,-16129,6000])
        self.assertEqual(result['prediction'],9)

    def test_invalid_inputs_and_int32_overflow_models_are_rejected(self):
        for pixels in [[0]*783,[17]+[0]*783,[-1]+[0]*783,[True]+[0]*783,[0.5]+[0]*783]:
            with self.assertRaises(ValueError):predict_hd(pixels,self.model)
        for field,value in [('hidden_shift',25),('hidden_shift',True),('w1',[0])]:
            fixture=copy.deepcopy(self.model);fixture[field]=value
            with self.assertRaises(ValueError):validate_hd_model(fixture)
        for bias in ['b1','b2']:
            fixture=copy.deepcopy(self.model);fixture[bias][0]=2**31-1
            with self.assertRaises(ValueError):validate_hd_model(fixture)

    @unittest.skipUnless(importlib.util.find_spec('numpy'),'NumPy required only for retraining')
    def test_fixed_seed_retraining_repeats_integer_exports_in_current_environment(self):
        with tempfile.TemporaryDirectory(prefix='neurotile-hd-model-')as output:
            first=Path(output)/'first';second=Path(output)/'second'
            for destination in [first,second]:
                process=subprocess.run([sys.executable,str(ROOT/'tools/train_hd_model.py'),
                    '--output-root',str(destination)],cwd=ROOT,capture_output=True,text=True,timeout=180)
                self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            reproduced=json.loads((first/'models/mnist_q8.json').read_text())
            repeated=json.loads((second/'models/mnist_q8.json').read_text())
            # Float32 training differs between BLAS implementations. Check real
            # repeatability on the current machine, while separate tests lock
            # down the committed golden artifact and its full test accuracy.
            validate_hd_model(reproduced)
            for field in ['input_size','hidden_size','output_size','hidden_shift','w1','w2','b1','b2',
                          'sample_input','sample_label','sample_reference']:
                self.assertEqual(reproduced[field],repeated[field],field)
            for field in ['correct_test_predictions','quantized_test_accuracy','confusion_matrix']:
                self.assertEqual(reproduced['metrics'][field],repeated['metrics'][field],field)
            self.assertGreaterEqual(reproduced['metrics']['quantized_test_accuracy'],.96)
            self.assertEqual((first/'firmware/generated/mnist_model.h').read_bytes(),
                             (second/'firmware/generated/mnist_model.h').read_bytes())


if __name__=='__main__':unittest.main()
