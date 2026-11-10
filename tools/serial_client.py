"""Submit one digit to a physical UART-connected NeuroTile and check exact logits."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT
sys.path.insert(0,str(ROOT/'python'))
from neurotile.model import load_model,predict


def encode_frame(pixels) -> bytes:
    if len(pixels)!=64 or any(type(v)is not int or not 0<=v<=16 for v in pixels):
        raise ValueError('Expected64 integer pixels in0..16.')
    checksum=0
    for value in pixels:checksum^=value
    return b'NT'+bytes(pixels)+bytes([checksum])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True,help='e.g.COM3 or /dev/ttyUSB0')
    parser.add_argument('--baud',type=int,default=115200)
    parser.add_argument('--input',type=Path,help='JSON array; default is bundled example')
    parser.add_argument('--timeout',type=float,default=8.0)
    args=parser.parse_args()
    try:import serial
    except ImportError:parser.error('Install optional hardware dependency: python -m pip install -r requirements-hardware.txt')
    model=load_model()
    pixels=json.loads(args.input.read_text()) if args.input else model['sample_input']
    expected=predict(pixels,model);frame=encode_frame(pixels)
    with serial.Serial(args.port,args.baud,timeout=0.25,write_timeout=2) as connection:
        # Let USB adapters finish opening; consume the boot banner if present.
        time.sleep(0.2);connection.reset_input_buffer();connection.write(frame);connection.flush()
        deadline=time.monotonic()+args.timeout;buffer=bytearray()
        while time.monotonic()<deadline:
            buffer.extend(connection.read(256))
            while b'\n' in buffer:
                line,_,remainder=buffer.partition(b'\n');buffer=bytearray(remainder)
                if not line.startswith(b'UART_RESULT '):continue
                report=json.loads(line[len(b'UART_RESULT '):])
                if 'error'in report:raise RuntimeError(report['error'])
                if report['logits']!=expected['logits'] or report['prediction']!=expected['prediction']:
                    raise RuntimeError('Board result differs from Python reference.')
                report.update(verified=True,backend='physical UART board')
                print(json.dumps(report,indent=2));return
    raise TimeoutError('No complete UART response before timeout.')


if __name__=='__main__':main()
