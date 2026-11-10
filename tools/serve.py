"""Local engineering demo; serves real reference, native C and Icarus RTL results."""
from __future__ import annotations
import argparse
import functools
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, tool_available
sys.path.insert(0,str(ROOT/'python'))
from neurotile.model import load_model,predict
from neurotile.dataset import load_dataset
from neurotile.labs import run_all_labs


@functools.lru_cache(maxsize=1)
def examples(): return load_dataset('test')


def sample(index: int) -> dict:
    rows,labels=examples()
    if not 0<=index<len(rows): raise ValueError('Sample index must be 0..1796.')
    return {'pixels':rows[index],'label':labels[index],'index':index}


@functools.lru_cache(maxsize=1)
def hd_examples():
    from neurotile.hd_dataset import load_hd_dataset
    return load_hd_dataset('test')


def hd_sample(index=0,digits=2):
    from neurotile.vision import compose_digits
    rows,labels=hd_examples()
    if not 0<=index<len(rows):raise ValueError('MNIST sample index must be0..9999.')
    if digits not in (1,2):raise ValueError('digits must be1 or2.')
    indices=[(index+i)%len(rows) for i in range(digits)]
    return {'pixels':compose_digits([rows[i] for i in indices]),'width':128,'height':64,
            'label':''.join(str(labels[i]) for i in indices),'index':index,'indices':indices,
            'source':'Unmodified official MNIST test samples composed on a canvas.'}


def reports() -> dict:
    result={}
    for name in ['soc','verification','synthesis','hd_soc','hd_benchmark','recognition']:
        path=ROOT/'reports'/(name+'.json')
        result[name]=json.loads(path.read_text()) if path.exists() else None
    return result


@functools.lru_cache(maxsize=1)
def labs(): return run_all_labs()


class Handler(BaseHTTPRequestHandler):
    server_version='NeuroTile/2.0'

    def send_json(self,payload,status=200):
        data=json.dumps(payload,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(data)

    def do_GET(self):
        parsed=urlsplit(self.path)
        try:
            if parsed.path=='/api/status':
                model=load_model()
                from neurotile.hd_model import load_hd_model
                hd_model=load_hd_model()
                backends={'rtl':tool_available('iverilog') and tool_available('vvp'),
                          'c':tool_available('gcc'),'reference':True}
                self.send_json({'name':'NeuroTile','version':'2.0','model':{k:model[k] for k in
                    ['input_size','hidden_size','output_size','metrics']},
                    'backends':backends,
                    'highres':{'model':{k:hd_model[k] for k in ['input_size','hidden_size','output_size','metrics']},
                               'canvas':{'width':128,'height':64},'backends':backends,
                               'features':['single_digit','two_digits','segmentation','image_upload','batched_rtl']},
                    'sample':sample(0),'reports':reports()})
            elif parsed.path=='/api/sample':
                self.send_json(sample(int(parse_qs(parsed.query).get('index',['0'])[0])))
            elif parsed.path=='/api/labs': self.send_json(labs())
            elif parsed.path=='/api/hd/sample':
                query=parse_qs(parsed.query)
                self.send_json(hd_sample(int(query.get('index',['0'])[0]),int(query.get('digits',['2'])[0])))
            elif parsed.path=='/api/reports': self.send_json(reports())
            else:
                allowed={'/':'index.html','/index.html':'index.html',
                         '/app.js':'app.js','/style.css':'style.css'}
                filename=allowed.get(parsed.path)
                if filename is None: self.send_json({'error':'Not found'},404);return
                path=ROOT/'web'/filename
                if not path.exists(): self.send_json({'error':'UI file missing'},404);return
                types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
                       '.css':'text/css; charset=utf-8'}
                data=path.read_bytes();self.send_response(200)
                self.send_header('Content-Type',types[path.suffix])
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers();self.wfile.write(data)
        except (ValueError,TypeError) as error: self.send_json({'error':str(error)},400)
        except Exception as error: self.send_json({'error':str(error)},500)

    def do_POST(self):
        path=urlsplit(self.path).path
        if path not in ('/api/infer','/api/recognize'): self.send_json({'error':'Not found'},404);return
        try:
            # Bind to loopback by default; also reject cross-origin browser requests.
            origin=self.headers.get('Origin')
            host=self.headers.get('Host','')
            if origin and origin not in ('http://'+host,'https://'+host):
                self.send_json({'error':'Cross-origin request rejected'},403);return
            size=int(self.headers.get('Content-Length','0'))
            maximum=262144 if path=='/api/recognize' else 16384
            if not 0<size<=maximum: self.send_json({'error':'Invalid body size'},413);return
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict): raise ValueError('Expected a JSON object.')
            pixels=body.get('pixels')
            if path=='/api/recognize':
                from neurotile.recognition import recognize_image
                self.send_json(recognize_image(pixels,width=body.get('width',128),height=body.get('height',64),
                    mode=body.get('mode','auto'),backend=body.get('backend','reference'),split=body.get('split')))
                return
            if not isinstance(pixels,list): raise ValueError('pixels must be an array of 64 integers.')
            model=load_model();start=time.perf_counter();expected=predict(pixels,model)
            backend=body.get('backend','reference')
            if backend=='reference':
                result={**expected,'backend':'reference','verified':False,
                        'host_elapsed_ms':round((time.perf_counter()-start)*1000,3),
                        'cycle_scope':'Python reference only; no hardware cycles measured.'}
            elif backend=='rtl':
                from tools.infer import rtl_infer
                result=rtl_infer(pixels,model)
            elif backend=='c':
                from tools.native_ref import c_infer
                result=c_infer(pixels,model)
            else: raise ValueError('backend must be reference, c or rtl.')
            self.send_json(result)
        except (ValueError,TypeError,KeyError) as error:self.send_json({'error':str(error)},400)
        except Exception as error:self.send_json({'error':str(error)},500)


class LocalServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR allows multiple live listeners on the same address,
    # which can make a restarted app appear to serve stale code.
    allow_reuse_address=os.name!='nt'
    def server_bind(self):
        if os.name=='nt':
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


def make_server(host='127.0.0.1',port=8000):
    return LocalServer((host,port),Handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',default=8000,type=int)
    args=parser.parse_args()
    server=make_server(args.host,args.port)
    print(f'NeuroTile: http://{args.host}:{server.server_port}',flush=True)
    print('Press Ctrl+C to stop. RTL buttons execute Icarus; reference mode needs only Python.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
