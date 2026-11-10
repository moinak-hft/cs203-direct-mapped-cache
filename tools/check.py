"""Run the meaningful regression and regenerate reviewable evidence."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,run_tool,tool_available
sys.path.insert(0,str(ROOT/'python'))


class Tee:
    def __init__(self,*streams):self.streams=streams
    def write(self,text):
        for stream in self.streams:stream.write(text)
    def flush(self):
        for stream in self.streams:stream.flush()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-tools',action='store_true',help='Fail instead of accepting missing hardware tools or skipped tests.')
    parser.add_argument('--synth',action='store_true',help='Also run Yosys structural synthesis checks.')
    args=parser.parse_args()
    required=['gcc','iverilog','vvp','riscv64-unknown-elf-gcc','riscv64-unknown-elf-objcopy']
    if args.synth:required.append('yosys')
    missing=[name for name in required if not tool_available(name)]
    if args.require_tools and missing:parser.error('Missing tools: '+', '.join(missing))
    (ROOT/'reports').mkdir(exist_ok=True)
    log=io.StringIO();start=time.perf_counter()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(stream=Tee(sys.stderr,log),verbosity=2).run(suite)
    report={'passed':result.wasSuccessful() and not (args.require_tools and result.skipped),
            'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'skipped':[{'test':str(test),'reason':reason} for test,reason in result.skipped],
            'duration_seconds':round(time.perf_counter()-start,3),'python':platform.python_version(),
            'tools':{},'scope':'Simulation and software verification. No physical FPGA timing, power, or area claim.'}
    for name in required:
        if not tool_available(name):report['tools'][name]=None;continue
        flag='-V' if name in ['iverilog','vvp','yosys'] else '--version'
        output=run_tool(name,[flag],check=False)
        lines=(output.stdout+'\n'+output.stderr).strip().splitlines()
        report['tools'][name]=lines[0] if lines else 'available'
    (ROOT/'reports/tests.log').write_text(log.getvalue(),encoding='utf-8')
    if report['passed']:
        from neurotile.labs import run_all_labs
        (ROOT/'reports/labs.json').write_text(json.dumps(run_all_labs(),indent=2)+'\n')
        if tool_available('iverilog') and tool_available('vvp'):
            from tools.infer import rtl_infer
            from neurotile.model import load_model
            (ROOT/'reports/inference.json').write_text(json.dumps(rtl_infer(load_model()['sample_input']),indent=2)+'\n')
        if args.synth:
            from tools.build import synth
            synth()
            for top,sources in [('adaptive_selector',['rtl/labs/adaptive_selector.v']),
                                ('domain_cache',['rtl/labs/domain_cache.v']),
                                ('neurotile_uart',['rtl/uart.v'])]:
                commands='read_verilog '+' '.join(sources)+f'; hierarchy -check -top {top}; proc; opt; check -assert'
                output=run_tool('yosys',['-Q','-T','-p',commands])
                (ROOT/'reports'/f'{top}_synthesis.log').write_text(output.stdout,encoding='utf-8')
            report['synthesis']='Accelerator generic RTL statistics and lab/UART structural checks passed.'
    (ROOT/'reports/verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
