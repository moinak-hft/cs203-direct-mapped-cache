"""Measure two-digit batching using real RTL and evaluate composed held-out pairs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT
sys.path.insert(0,str(ROOT/'python'))
from neurotile.hd_dataset import load_hd_dataset
from neurotile.hd_model import load_hd_model,predict_hd
from neurotile.vision import compose_digits,segment_digits


def evaluate_pairs(count=100):
    if type(count)is not int or not 1<=count<=5000:raise ValueError('Pair count must be1..5000.')
    rows,labels=load_hd_dataset('test');model=load_hd_model()
    correct_pairs=0;correct_digits=0;segmented=0;examples=[]
    for index in range(count):
        offset=index*2;images=rows[offset:offset+2]
        canvas=compose_digits(images);segments=segment_digits(canvas,128,64,'double')
        predictions=[predict_hd(image,model)['prediction'] for image in segments['normalized']]
        expected=labels[offset:offset+2]
        segmented+=len(predictions)==2
        correct_digits+=sum(a==b for a,b in zip(predictions,expected))
        correct_pairs+=predictions==expected
        if index<10:examples.append({'test_indices':[offset,offset+1],
                                    'expected':''.join(map(str,expected)),
                                    'prediction':''.join(map(str,predictions))})
    return {'pairs':count,'correct_pairs':correct_pairs,'pair_accuracy':correct_pairs/count,
            'digit_accuracy':correct_digits/(count*2),'two_crops_detected':segmented,
            'selection':'Consecutive official test indices0..'+str(count*2-1)+'; no success filtering.',
            'scope':'Synthetic side-by-side composition of held-out MNIST digits, including segmentation/normalization. Not a real handwritten two-digit dataset.',
            'examples':examples}


def benchmark_batch():
    from tools.hd_infer import rtl_infer_hd_batch
    rows,_=load_hd_dataset('test');model=load_hd_model();images=[list(rows[0]),list(rows[1])]
    single=[rtl_infer_hd_batch([image],model) for image in images]
    batch=rtl_infer_hd_batch(images,model)
    for i in range(2):
        if batch['logits'][i]!=single[i]['logits'][0]:raise RuntimeError('Batch changed output.')
    single_cycles=sum(row['transaction_cycles'] for row in single)
    return {'batch_size':2,'single_kernel_cycles':[row['kernel_cycles'] for row in single],
            'batch_kernel_cycles':batch['kernel_cycles'],'single_transaction_cycles':[row['transaction_cycles'] for row in single],
            'batch_transaction_cycles':batch['transaction_cycles'],
            'transaction_speedup':single_cycles/batch['transaction_cycles'],
            'kernel_speedup':sum(row['kernel_cycles'] for row in single)/batch['kernel_cycles'],
            'predictions':batch['predictions'],'verified':True,
            'scope':'Measured standalone RTL cycles, including MMIO transfers and partial-sum accumulation; excludes CPU firmware, image processing and host transport.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs',type=int,default=100)
    parser.add_argument('--reference-only',action='store_true')
    args=parser.parse_args();(ROOT/'reports').mkdir(exist_ok=True)
    pairs=evaluate_pairs(args.pairs)
    (ROOT/'reports/recognition.json').write_text(json.dumps(pairs,indent=2)+'\n')
    result={'recognition':pairs}
    if not args.reference_only:
        batch=benchmark_batch();(ROOT/'reports/hd_benchmark.json').write_text(json.dumps(batch,indent=2)+'\n')
        result['batching']=batch
    print(json.dumps(result,indent=2))
