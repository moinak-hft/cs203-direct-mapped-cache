"""Bundled genuine 28x28 MNIST with an official-test, training-only subset split.

The runtime loader uses stdlib only. Each gzip member contains rows of one
label byte followed by 784 quantized pixel bytes (0..16). Original IDX archives
are downloaded only when explicitly preparing data for a new source checkout.
"""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import random
import struct
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
SOURCE_BASE='https://ossci-datasets.s3.amazonaws.com/mnist/'
SOURCES={
    'train-images-idx3-ubyte.gz':'f68b3c2dcbeaaa9fbdd348bbdeb94873',
    'train-labels-idx1-ubyte.gz':'d53e105ee54ea40749a09fcbcd1e9432',
    't10k-images-idx3-ubyte.gz':'9fb629c4189551a2d022fa330f9573f3',
    't10k-labels-idx1-ubyte.gz':'ec29112dd5afa0611ce80d1b7f02629c',
}


def load_hd_dataset(split: str='test',verify: bool=True)->tuple[list[bytes],list[int]]:
    if split not in ('train','test'):raise ValueError('split must be train or test')
    path=ROOT/'data'/f'mnist_{split}.u8.gz'
    metadata=json.loads((ROOT/'data/mnist_provenance.json').read_text())
    compressed=path.read_bytes()
    if verify and hashlib.sha256(compressed).hexdigest()!=metadata['bundled_files'][path.name]['sha256']:
        raise ValueError('MNIST dataset SHA256 mismatch: '+path.name)
    raw=gzip.decompress(compressed)
    expected=metadata['bundled_files'][path.name]['samples']
    if len(raw)!=expected*785:raise ValueError('Malformed MNIST row count')
    images=[];labels=[]
    for start in range(0,len(raw),785):
        label=raw[start];pixels=raw[start+1:start+785]
        if label>9 or max(pixels)>16:raise ValueError('Malformed MNIST label or pixel')
        labels.append(label);images.append(pixels)
    return images,labels


def prepare_hd_dataset(download_dir:Path,output_root:Path=ROOT,seed:int=2026)->dict:
    """Download original archives; pick 2,000 per class from training only.

    Official test ordering/membership is preserved. Pixel quantization is a
    fixed public transform, round(pixel*16/255), not a fitted normalization.
    """
    download_dir=Path(download_dir);download_dir.mkdir(parents=True,exist_ok=True)
    original={}
    for name,expected_md5 in SOURCES.items():
        path=download_dir/name
        if not path.exists():
            print('Downloading '+SOURCE_BASE+name,flush=True)
            urllib.request.urlretrieve(SOURCE_BASE+name,path)
        payload=path.read_bytes()
        if hashlib.md5(payload).hexdigest()!=expected_md5:
            raise ValueError('Original MNIST archive MD5 mismatch: '+name)
        original[name]={'url':SOURCE_BASE+name,'md5':expected_md5,
                        'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}
    def idx(prefix):
        raw_images=gzip.decompress((download_dir/(prefix+'-images-idx3-ubyte.gz')).read_bytes())
        raw_labels=gzip.decompress((download_dir/(prefix+'-labels-idx1-ubyte.gz')).read_bytes())
        magic,count,height,width=struct.unpack('>IIII',raw_images[:16])
        label_magic,label_count=struct.unpack('>II',raw_labels[:8])
        if (magic,height,width,label_magic,label_count)!=(2051,28,28,2049,count):
            raise ValueError('Original IDX header mismatch')
        if len(raw_images)!=16+count*784 or len(raw_labels)!=8+count:raise ValueError('IDX payload mismatch')
        return raw_images[16:],raw_labels[8:]
    train_images,train_labels=idx('train');test_images,test_labels=idx('t10k')
    rng=random.Random(seed);indices=[]
    for digit in range(10):
        indices.extend(rng.sample([i for i,label in enumerate(train_labels) if label==digit],2000))
    indices.sort()
    target=Path(output_root)/'data';target.mkdir(parents=True,exist_ok=True)
    metadata={'dataset':'MNIST','authors':'Yann LeCun, Corinna Cortes, Christopher J. C. Burges',
        'homepage':'http://yann.lecun.com/exdb/mnist/',
        'dataset_card':'https://huggingface.co/datasets/ylecun/mnist/blob/main/README.md',
        'license':'MIT (as identified by the ylecun/mnist dataset card)',
        'original_archives':original,
        'split':'20,000 stratified samples from official60,000 training only; all official10,000 test, original order',
        'training_subset':{'seed':seed,'per_class':2000,'original_count':60000,'selected_count':20000,
                           'indices_file':'data/mnist_train_indices.json'},
        'transform':'Fixed integer pixel quantization: (original_uint8*16+127)//255; no fitted statistics',
        'binary_format':'gzip of repeated785-byte rows: uint8label,784uint8pixels(0..16)',
        'bundled_files':{}}
    table=bytes((value*16+127)//255 for value in range(256))
    for split,images,labels,chosen in [('train',train_images,train_labels,indices),
                                      ('test',test_images,test_labels,range(len(test_labels)))]:
        data=bytearray()
        for index in chosen:
            data.append(labels[index]);data.extend(images[index*784:(index+1)*784].translate(table))
        path=target/f'mnist_{split}.u8.gz'
        packed=gzip.compress(data,compresslevel=9,mtime=0);path.write_bytes(packed)
        metadata['bundled_files'][path.name]={'sha256':hashlib.sha256(packed).hexdigest(),
            'uncompressed_sha256':hashlib.sha256(data).hexdigest(),'samples':len(chosen),'bytes':len(packed)}
    (target/'mnist_train_indices.json').write_text(json.dumps(indices,separators=(',',':'))+'\n')
    (target/'mnist_provenance.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return metadata
