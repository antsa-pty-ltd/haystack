#!/usr/bin/env python3
import http.server
import pathlib
import socketserver
import sys


status = int(sys.argv[1])
port_file = pathlib.Path(sys.argv[2])
body_file = pathlib.Path(sys.argv[3])


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body_file.write_bytes(self.rfile.read(length))
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b"accepted" if 200 <= status < 300 else b"rejected")

    def log_message(self, *_args):
        return


with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
    port_file.write_text(str(server.server_address[1]), encoding="utf-8")
    server.handle_request()
