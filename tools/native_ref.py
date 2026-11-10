"""Run the native C reference on the same submitted pixels."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, tool_command, _linux_arg
sys.path.insert(0,str(ROOT/'python'))
from neurotile.model import load_model, predict
_lock=threading.Lock()


def c_infer(features, model=None) -> dict:
    from tools.build import native
    model=model or load_model()
    expected=predict(features,model)
    # C is compiled against the committed model header, not arbitrary JSON models.
    if model != load_model():
        raise ValueError('Native C backend uses the committed model/header.')
    compiler=tool_command('gcc')
    if not compiler: raise RuntimeError('C compiler unavailable; see README.')
    uses_wsl=Path(compiler[0]).stem.lower()=='wsl'
    executable=ROOT/'build'/('host_reference.exe' if os.name=='nt' and not uses_wsl else 'host_reference')
    sources=[ROOT/p for p in ['firmware/host_reference.c','firmware/quant.h','firmware/generated/model.h']]
    with _lock:
        if not executable.exists() or any(p.stat().st_mtime>executable.stat().st_mtime for p in sources):
            native()
    command=[*compiler[:-1],_linux_arg(executable)] if uses_wsl else [str(executable)]
    start=time.perf_counter()
    result=subprocess.run(command,input=' '.join(map(str,features))+'\n',capture_output=True,
                          text=True,cwd=ROOT,timeout=30)
    if result.returncode: raise RuntimeError('Native C inference failed: '+result.stderr)
    report=json.loads(result.stdout)
    if any(report[key]!=expected[key] for key in ['hidden','logits','prediction']):
        raise RuntimeError('C differs from Python integer reference.')
    report.update(backend='c',verified=True,
                  host_elapsed_ms=round((time.perf_counter()-start)*1000,3),
                  cycle_scope='Native host process elapsed time; not RISC-V cycles.')
    return report
