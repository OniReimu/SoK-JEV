"""Real CPU image transformation for the execution-path feasibility probe."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import os
from PIL import Image


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.end_headers();self.wfile.write(b'ready')

    def do_POST(self):
        raw=self.rfile.read(int(self.headers['Content-Length']))
        im=Image.open(BytesIO(raw)).convert('L').resize((64,64))
        out=BytesIO();im.save(out,format='PNG');body=out.getvalue()
        self.send_response(200);self.send_header('Content-Type','image/png')
        self.send_header('X-Node',os.environ.get('NODE_NAME','unknown'))
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
