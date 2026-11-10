"""Higher-resolution MNIST inference using actual K-blocked, two-row RTL batches."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,run_tool,write_hex,tool_command,_linux_arg
sys.path.insert(0,str(ROOT/'python'))
_build_lock=threading.Lock()
_c_lock=threading.Lock()


def _validated(batch,model):
    from neurotile.hd_model import load_hd_model,predict_hd,validate_hd_model
    model=load_hd_model() if model is None else model
    if not isinstance(batch,list) or len(batch) not in (1,2):
        raise ValueError('High-resolution hardware accepts one or two 28x28 inputs.')
    if tuple(model.get(k) for k in ['input_size','hidden_size','output_size'])!=(784,64,10):
        raise ValueError('Hardware requires a 784 -> 64 -> 10 model.')
    validate_hd_model(model)
    expected=[predict_hd(features,model) for features in batch]
    return model,expected


def ensure_hd_bench():
    from tools.build import compile_bench,ACCEL
    sources=[*ACCEL,'sim/tb_hd_inference.sv']
    target=ROOT/'build/tb_hd_inference.vvp'
    with _build_lock:
        if not target.exists() or any((ROOT/p).stat().st_mtime>target.stat().st_mtime for p in sources):
            compile_bench('tb_hd_inference',sources)
    return target


def rtl_infer_hd_batch(features_batch:list[list[int]],model=None)->dict:
    model,expected=_validated(features_batch,model)
    bench=ensure_hd_bench();start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='hd-infer-',dir=ROOT/'build') as directory:
        tmp=Path(directory)
        # Fixed-length memory file avoids simulator short-file warnings in batch1.
        pixels=[value for image in features_batch for value in image]
        pixels += [0]*(1568-len(pixels))
        for name,values,width in [('input',pixels,8),('w1',model['w1'],8),
            ('w2',model['w2'],8),('b1',model['b1'],32),('b2',model['b2'],32)]:
            write_hex(tmp/(name+'.hex'),values,width)
        result=run_tool('vvp',[bench,*[f'+{n.upper()}={tmp/(n+".hex")}' for n in
            ['input','w1','w2','b1','b2']],f'+SHIFT={model["hidden_shift"]}',
            f'+BATCH={len(features_batch)}'],timeout=180)
    for line in result.stdout.splitlines():
        if line.startswith('HD_RTL_RESULT '):
            report=json.loads(line[len('HD_RTL_RESULT '):])
            for key,singular in [('predictions','prediction'),('hidden','hidden'),('logits','logits')]:
                if report[key]!=[r[singular] for r in expected]:
                    raise RuntimeError(f'High-resolution RTL {key} differs from integer reference.')
            report.update(backend='rtl',verified=True,
                host_elapsed_ms=round((time.perf_counter()-start)*1000,3),
                cycle_scope='Actual standalone RTL K-blocked batch cycles; includes MMIO tensor transfers/readback but not CPU firmware or image preprocessing.')
            return report
    raise RuntimeError('Missing HD RTL inference response:\n'+result.stdout)


def c_infer_hd_batch(features_batch:list[list[int]],model=None)->dict:
    from neurotile.hd_model import load_hd_model
    model,expected=_validated(features_batch,model)
    if model!=load_hd_model():raise ValueError('C backend is compiled against the bundled MNIST header.')
    compiler=tool_command('gcc')
    if not compiler:raise RuntimeError('Native C compiler unavailable.')
    uses_wsl=Path(compiler[0]).stem.lower()=='wsl'
    executable=ROOT/'build'/('hd_reference.exe' if os.name=='nt' and not uses_wsl else 'hd_reference')
    sources=[ROOT/p for p in ['firmware/hd_reference.c','firmware/quant.h','firmware/generated/mnist_model.h']]
    with _c_lock:
        if not executable.exists() or any(p.stat().st_mtime>executable.stat().st_mtime for p in sources):
            executable.parent.mkdir(exist_ok=True)
            run_tool('gcc',['-std=c11','-O2','-Wall','-Wextra','-Werror','-Ifirmware',
                'firmware/hd_reference.c','-o',executable])
    command=[*compiler[:-1],_linux_arg(executable)] if uses_wsl else [str(executable)]
    start=time.perf_counter()
    request=str(len(features_batch))+'\n'+'\n'.join(' '.join(map(str,x)) for x in features_batch)+'\n'
    result=subprocess.run(command,input=request,capture_output=True,text=True,cwd=ROOT,timeout=30)
    if result.returncode:raise RuntimeError('HD native C inference failed: '+result.stderr)
    report=json.loads(result.stdout)
    for key,singular in [('predictions','prediction'),('hidden','hidden'),('logits','logits')]:
        if report[key]!=[r[singular] for r in expected]:
            raise RuntimeError(f'HD native C {key} differs from integer reference.')
    report.update(backend='c',verified=True,host_elapsed_ms=round((time.perf_counter()-start)*1000,3),
        cycle_scope='Native host C process elapsed time; not RISC-V cycles.')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,help='JSON array containing one or two 784-integer images')
    parser.add_argument('--backend',choices=['rtl','c'],default='rtl')
    args=parser.parse_args()
    from neurotile.hd_model import load_hd_model
    model=load_hd_model();batch=json.loads(args.input.read_text()) if args.input else [model['sample_input']]
    fn=rtl_infer_hd_batch if args.backend=='rtl' else c_infer_hd_batch
    print(json.dumps(fn(batch,model),indent=2))
