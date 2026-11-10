"""Execute the real RTL on one submitted 8x8 sample and compare all intermediate values."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, run_tool, write_hex
sys.path.insert(0, str(ROOT/'python'))
from neurotile.model import load_model, predict

_build_lock = threading.Lock()


def ensure_inference_bench() -> Path:
    from tools.build import ACCEL, compile_bench
    sources = [*ACCEL, 'sim/tb_inference.sv']
    target = ROOT/'build/tb_inference.vvp'
    with _build_lock:
        if not target.exists() or any((ROOT/p).stat().st_mtime > target.stat().st_mtime for p in sources):
            compile_bench('tb_inference', sources)
    return target


def rtl_infer(features, model=None) -> dict:
    model = model or load_model()
    expected = predict(features, model)  # Also validates the input.
    bench = ensure_inference_bench()
    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='infer-', dir=ROOT/'build') as directory:
        tmp = Path(directory)
        for name, values, width in [('input', features, 8), ('w1', model['w1'], 8),
                                    ('w2', model['w2'], 8), ('b1', model['b1'], 32), ('b2', model['b2'], 32)]:
            write_hex(tmp/(name+'.hex'), values, width)
        result = run_tool('vvp', [bench, *[f'+{n.upper()}={tmp/(n+".hex")}'
                              for n in ['input', 'w1', 'w2', 'b1', 'b2']],
                              f'+SHIFT={model["hidden_shift"]}'], timeout=60)
    for line in result.stdout.splitlines():
        if line.startswith('RTL_RESULT '):
            report = json.loads(line[len('RTL_RESULT '):])
            if any(report[k] != expected[k] for k in ['prediction', 'hidden', 'logits']):
                raise RuntimeError('RTL differs from the Python integer reference.')
            report.update(backend='rtl', verified=True,
                          host_elapsed_ms=round((time.perf_counter()-start)*1000, 3),
                          cycle_scope='Actual standalone RTL bench cycles; transaction cycles include MMIO loading and readback, not CPU execution.')
            return report
    raise RuntimeError('Simulator produced no result:\n' + result.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='JSON array of 64 integer pixels in 0..16')
    args = parser.parse_args()
    model = load_model()
    features = json.loads(args.input.read_text()) if args.input else model['sample_input']
    print(json.dumps(rtl_infer(features, model), indent=2))
