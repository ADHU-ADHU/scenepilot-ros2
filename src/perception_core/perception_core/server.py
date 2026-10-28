"""Internal JSON/PNG API. Deploy behind trusted networking; no public listener by default."""
import argparse
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .backends import create_backend
from .contracts import load_config, validate_request, validate_response


class BackendService:
    def __init__(self, name, config):
        self.name, self.config = name, config
        self.backend = create_backend(config)
        self.lock = threading.Lock()

    def dispatch(self, path, payload):
        if path == '/healthz':
            return {'status':'alive','backend':self.name,'kind':self.config['kind'],'busy':self.lock.locked()}
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError('Backend busy; no second inference or unload admitted')
        try:
            if path == '/readyz':
                return self.backend.ready()
            if path == '/unload':
                self.backend.unload()
                return {'unloaded':True}
            if path != '/infer':
                raise KeyError('Unknown endpoint')
            validate_request(payload, self.config['kind'])
            start = time.perf_counter()
            output = self.backend.infer(payload)
            result = {**output, **{k:payload[k] for k in ('api_version','kind','generation','request_id')},
                      'backend':self.name,'inference_ms':(time.perf_counter()-start)*1000}
            if payload['kind']=='vlm':
                result['source_headers']={x['camera']:x['header'] for x in payload['images']}
            return validate_response(result,payload)
        finally:
            self.lock.release()


def make_server(service, host, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.handle_request({})

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 32*1024*1024:
                    raise ValueError('Request must be between 1 byte and 32 MiB')
                self.connection.settimeout(30)
                data = json.loads(self.rfile.read(size))
            except (ValueError, TimeoutError) as exc:
                self.respond(400, {'error':str(exc)})
                return
            self.handle_request(data)

        def handle_request(self, data):
            try:
                allowed = ('/healthz','/readyz') if self.command == 'GET' else ('/infer','/unload')
                if self.path not in allowed:
                    self.respond(404, {'error':'Unknown endpoint or method'})
                    return
                self.respond(200,service.dispatch(self.path,data))
            except BlockingIOError as exc:
                self.respond(409,{'error':str(exc)})
            except (ValueError,KeyError) as exc:
                self.respond(400,{'error':str(exc)})
            except Exception as exc:
                logging.exception('Backend operation failed')
                self.respond(503,{'error':type(exc).__name__+': '+str(exc)})

        def respond(self, code, data):
            body = json.dumps(data,allow_nan=False).encode()
            try:
                self.send_response(code)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):
                pass  # Caller timed out; inference still held its lease until completion.
    return ThreadingHTTPServer((host,port),Handler)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--backend',required=True)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args()
    config=load_config(args.config)['backends'][args.backend]
    server=make_server(BackendService(args.backend,config),args.host,args.port)
    print(f'Backend {args.backend} listening on {args.host}:{args.port}',flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
