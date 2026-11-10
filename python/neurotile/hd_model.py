"""Exact stdlib-only integer inference for the genuine28x28 MNIST model."""
from __future__ import annotations
from functools import lru_cache
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def validate_hd_model(model:dict)->None:
    for name,expected in [('input_size',784),('hidden_size',64),('output_size',10)]:
        if type(model.get(name))is not int or model[name]!=expected:
            raise ValueError('HD model must be784->64->10')
    if type(model.get('hidden_shift'))is not int or not 0<=model['hidden_shift']<=24:
        raise ValueError('hidden_shift must be an integer0..24')
    for field,count,lower,upper in [('w1',50176,-128,127),('w2',640,-128,127),
                                   ('b1',64,-2**31,2**31-1),('b2',10,-2**31,2**31-1)]:
        values=model.get(field)
        if not isinstance(values,list) or len(values)!=count or any(type(v)is not int or not lower<=v<=upper for v in values):
            raise ValueError('Malformed HD model '+field)
    for field,bias,k,n,bound in [('w1','b1',784,64,16),('w2','b2',64,10,127)]:
        for j in range(n):
            if abs(model[bias][j])+bound*sum(abs(model[field][i*n+j])for i in range(k))>2**31-1:
                raise ValueError('HD model may overflow signedINT32')


@lru_cache(maxsize=4)
def load_hd_model(path:str|Path|None=None)->dict:
    file=Path(path) if path is not None else ROOT/'models/mnist_q8.json'
    model=json.loads(file.read_text(encoding='utf-8'))
    validate_hd_model(model);return model


def predict_hd(features,model:dict|None=None)->dict:
    model=load_hd_model() if model is None else model
    if not isinstance(features,(list,tuple,bytes,bytearray)) or len(features)!=784:
        raise ValueError('Expected784 MNIST pixels')
    if any(type(v)is not int or not 0<=v<=16 for v in features):
        raise ValueError('HD pixels must be integer0..16')
    # Pixel-major loop skips background zeros and keeps the 64-weight row local.
    # The result remains independent of NumPy and exact across integer backends.
    hidden_acc=list(model['b1']);weights=model['w1']
    for i,pixel in enumerate(features):
        if pixel:
            start=i*64
            for j in range(64):hidden_acc[j]+=pixel*weights[start+j]
    hidden=[max(0,min(127,value>>model['hidden_shift']))for value in hidden_acc]
    logits=list(model['b2']);weights=model['w2']
    for i,value in enumerate(hidden):
        if value:
            start=i*10
            for j in range(10):logits[j]+=value*weights[start+j]
    return {'prediction':max(range(10),key=lambda j:logits[j]),'hidden':hidden,'logits':logits}
