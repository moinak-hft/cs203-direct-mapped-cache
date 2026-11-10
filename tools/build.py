"""Build targets without Make, shell-specific quoting, or Python package installation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, run_tool, tool_available, tool_command, write_hex

BUILD = ROOT / 'build'
ACCEL = ['rtl/mac_pe.v', 'rtl/neurotile_accel.v']


def compile_bench(top: str, sources: list[str]) -> Path:
    BUILD.mkdir(exist_ok=True)
    output = BUILD / (top + '.vvp')
    run_tool('iverilog', ['-g2012', '-Wall', '-s', top, '-o', output, *sources])
    return output


def firmware(interactive: bool = False, highres: bool = False) -> Path:
    BUILD.mkdir(exist_ok=True)
    if interactive and highres:raise ValueError('Select the legacy UART or high-resolution benchmark firmware.')
    stem='hd_firmware' if highres else 'interactive' if interactive else 'firmware'
    elf = BUILD / (stem+'.elf')
    run_tool('riscv64-unknown-elf-gcc', [
        '-march=rv32im', '-mabi=ilp32', '-O2' if highres else '-Os', '-ffreestanding', '-fno-builtin',
        '-fno-pic', '-fno-stack-protector', '-msmall-data-limit=0',
        '-nostdlib', '-Wall', '-Wextra', '-Werror', '-Ifirmware',
        '-Wl,-T,firmware/link.ld', '-Wl,--build-id=none', '-Wl,--no-relax',
        'firmware/start.S', 'firmware/hd_main.c' if highres else 'firmware/interactive.c' if interactive else 'firmware/main.c',
        'firmware/runtime.c', '-o', elf,
    ])
    binary = BUILD / (stem+'.bin')
    run_tool('riscv64-unknown-elf-objcopy', ['-O', 'binary', elf, binary])
    data = binary.read_bytes()
    data += bytes((-len(data)) % 4)
    if len(data) > 128 * 1024 - 4096:
        raise RuntimeError('Firmware does not leave a 4KiB stack.')
    # Pad to RAM size to avoid readmemh short-file warnings.
    data += bytes(128 * 1024 - len(data))
    write_hex(BUILD / (stem+'.hex'),
              (int.from_bytes(data[i:i+4], 'little') for i in range(0, len(data), 4)), 32)
    return elf


def native() -> Path:
    BUILD.mkdir(exist_ok=True)
    import os
    output = BUILD / ('host_reference.exe' if os.name == 'nt' and
                       Path(tool_command('gcc')[0]).stem.lower() != 'wsl' else 'host_reference')
    run_tool('gcc', ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                     '-Ifirmware', 'firmware/host_reference.c', '-o', output])
    return output


def run_soc(vcd: bool = False) -> dict:
    firmware()
    binary = compile_bench('tb_soc', [*ACCEL, 'third_party/picorv32/picorv32.v',
                                     'rtl/neurotile_soc.v', 'sim/tb_soc.sv'])
    result = run_tool('vvp', [binary, *(['+VCD'] if vcd else [])], timeout=180)
    lines = result.stdout.splitlines()
    for line in lines:
        if line.startswith('NT_RESULT '):
            report = json.loads(line[len('NT_RESULT '):])
            report['backend'] = 'PicoRV32 RV32IM + original accelerator, Icarus RTL simulation'
            report['speedup_including_transfers'] = report['software_cycles'] / report['accelerated_cycles']
            if not report['passed'] or 'SOC_PASS' not in result.stdout:
                raise RuntimeError('Firmware comparison failed:\n' + result.stdout)
            (ROOT / 'reports').mkdir(exist_ok=True)
            (ROOT / 'reports/soc.json').write_text(json.dumps(report, indent=2)+'\n')
            return report
    raise RuntimeError('Missing firmware result:\n' + result.stdout)


def run_uart_soc() -> dict:
    sys.path.insert(0,str(ROOT/'python'))
    from neurotile.model import load_model,predict
    model=load_model();firmware(interactive=True)
    write_hex(BUILD/'uart_input.hex',model['sample_input'])
    binary=compile_bench('tb_fpga_uart',[*ACCEL,'rtl/uart.v',
        'third_party/picorv32/picorv32.v','rtl/neurotile_soc.v',
        'rtl/neurotile_fpga_top.v','sim/tb_fpga_uart.sv'])
    result=run_tool('vvp',[binary,f'+INPUT={BUILD/"uart_input.hex"}'],timeout=180)
    responses=[json.loads(line[len('UART_RESULT '):]) for line in result.stdout.splitlines()
               if line.startswith('UART_RESULT ')]
    if len(responses)!=3 or responses[0].get('error')!='invalid frame' or 'FPGA_UART_PASS' not in result.stdout:
        raise RuntimeError('UART protocol regression failed:\n'+result.stdout)
    for response,pixels in zip(responses[1:],[model['sample_input'],[0]*64]):
        expected=predict(pixels,model)
        if response.get('logits')!=expected['logits'] or response.get('prediction')!=expected['prediction']:
            raise RuntimeError('UART inference differs from reference:\n'+result.stdout)
    report={**responses[1],'invalid_frames_rejected':1,'valid_frames':2,'second_result':responses[2],
            'scope':'Full UART wire protocol + RISC-V + accelerator RTL simulation, accelerated baud divider32; not a physical board test.'}
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/uart_soc.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def run_hd_soc() -> dict:
    sys.path.insert(0,str(ROOT/'python'))
    from neurotile.hd_model import load_hd_model,predict_hd
    firmware(highres=True)
    binary=compile_bench('tb_hd_soc',[*ACCEL,'third_party/picorv32/picorv32.v',
                                     'rtl/neurotile_soc.v','sim/tb_hd_soc.sv'])
    result=run_tool('vvp',[binary],timeout=480)
    for line in result.stdout.splitlines():
        if line.startswith('HD_SOC_RESULT '):
            report=json.loads(line[len('HD_SOC_RESULT '):])
            if not report.get('passed') or 'HD_SOC_PASS' not in result.stdout:
                raise RuntimeError('High-resolution CPU firmware failed:\n'+result.stdout)
            model=load_hd_model();original=model['sample_input']
            mirror=[original[y*28+27-x] for y in range(28) for x in range(28)]
            expected=[predict_hd(image,model) for image in [original,mirror]]
            if report['logits']!=[row['logits'] for row in expected]:
                raise RuntimeError('High-resolution CPU output differs from Python reference.')
            report.update(backend='PicoRV32 RV32IM + K-blocked batched accelerator, Icarus RTL simulation',
                          cpu_fast_mul=True,compiler_optimization='-O2',
                          speedup_including_transfers=report['software_cycles']/report['accelerated_cycles'],
                          scope='Two normalized28x28 inputs; CPU copies, block accumulation and activation included. Image segmentation and host transport excluded.')
            (ROOT/'reports').mkdir(exist_ok=True)
            (ROOT/'reports/hd_soc.json').write_text(json.dumps(report,indent=2)+'\n')
            return report
    raise RuntimeError('Missing high-resolution CPU result:\n'+result.stdout)


def synth() -> dict:
    BUILD.mkdir(exist_ok=True)
    (ROOT/'reports').mkdir(exist_ok=True)
    script = ('read_verilog rtl/mac_pe.v rtl/neurotile_accel.v; '
              'hierarchy -check -top neurotile_accel; proc; opt; '
              'check -assert; memory_collect; stat -json')
    result = run_tool('yosys', ['-Q', '-T', '-p', script], timeout=240)
    (ROOT / 'reports/synthesis.log').write_text(result.stdout, encoding='utf-8')
    # Generic RTL cell statistics, deliberately not FPGA utilization or timing.
    start = result.stdout.rfind('\n{')
    if start < 0:
        raise RuntimeError('Yosys did not emit JSON statistics.')
    decoder = json.JSONDecoder()
    stats, _ = decoder.raw_decode(result.stdout[start:].lstrip())
    stats['scope'] = 'Generic Yosys RTL synthesis; no FPGA mapping, place/route, or Fmax claim.'
    (ROOT / 'reports/synthesis.json').write_text(json.dumps(stats, indent=2)+'\n')
    return stats


def doctor() -> dict:
    names = ['gcc', 'iverilog', 'vvp', 'riscv64-unknown-elf-gcc',
             'riscv64-unknown-elf-objcopy', 'yosys']
    return {name: list(tool_command(name)) if tool_available(name) else None for name in names}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['doctor', 'native', 'firmware', 'hd-firmware', 'interactive', 'accel', 'infer', 'hd-infer', 'soc', 'hd-soc', 'uart-soc', 'labs', 'synth'])
    parser.add_argument('--vcd', action='store_true')
    args = parser.parse_args()
    if args.target == 'doctor': print(json.dumps(doctor(), indent=2))
    elif args.target == 'native': print(native())
    elif args.target == 'firmware': print(firmware())
    elif args.target == 'hd-firmware': print(firmware(highres=True))
    elif args.target == 'interactive': print(firmware(interactive=True))
    elif args.target == 'soc': print(json.dumps(run_soc(args.vcd), indent=2))
    elif args.target == 'hd-soc': print(json.dumps(run_hd_soc(),indent=2))
    elif args.target == 'hd-infer':
        from tools.hd_infer import rtl_infer_hd_batch
        sys.path.insert(0,str(ROOT/'python'))
        from neurotile.hd_model import load_hd_model
        print(json.dumps(rtl_infer_hd_batch([load_hd_model()['sample_input']]),indent=2))
    elif args.target == 'uart-soc': print(json.dumps(run_uart_soc(), indent=2))
    elif args.target == 'synth': print(json.dumps(synth(), indent=2))
    elif args.target == 'infer':
        from tools.infer import rtl_infer
        sys.path.insert(0, str(ROOT/'python'))
        from neurotile.model import load_model
        print(json.dumps(rtl_infer(load_model()['sample_input']), indent=2))
    else:
        top = 'tb_accel' if args.target == 'accel' else 'tb_labs'
        sources = ACCEL if args.target == 'accel' else sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'rtl/labs').glob('*.v'))
        binary = compile_bench(top, [*sources, 'sim/'+top+'.sv'])
        print(run_tool('vvp', [binary, *(['+VCD'] if args.vcd else [])]).stdout)


if __name__ == '__main__': main()
