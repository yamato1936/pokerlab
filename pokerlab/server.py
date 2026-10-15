"""Local-only zero-dependency Poker Lab UI server.

Run: python -m pokerlab.server
Opens http://127.0.0.1:8765. Nothing is uploaded anywhere.
"""
from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .session import Session

STATIC = Path(__file__).resolve().parent / 'static'
SESSION = Session()
LOCK = threading.RLock()


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, status=200):
        self._send(json.dumps(value, ensure_ascii=False).encode('utf-8'),
                   'application/json; charset=utf-8', status)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/state':
            with LOCK:
                self._json(SESSION.state())
            return
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/ui.js': ('ui.js', 'application/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path not in files:
            self._json({'error': 'not found'}, 404)
            return
        filename, typ = files[path]
        self._send((STATIC / filename).read_bytes(), typ)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/api/action', '/api/new', '/api/reset'):
            return self._json({'error': 'not found'}, 404)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 4096:
                return self._json({'error': 'request is too large'}, 413)
            data = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(data, dict):
                raise ValueError('expected JSON object')
            with LOCK:
                global SESSION
                if path == '/api/new':
                    state = SESSION.new_hand()
                elif path == '/api/reset':
                    SESSION = Session()
                    state = SESSION.state()
                else:
                    if set(data) - {'kind', 'raise_to'}:
                        raise ValueError('unknown fields')
                    state = SESSION.human_action(data.get('kind'), data.get('raise_to'))
            self._json(state)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json({'error': str(exc)}, 400)

    def log_message(self, format, *args):
        # Avoid dumping full paths or action payloads to stdout.
        if '/api/' not in str(args):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description='Poker Lab v0.2 (offline local browser app)')
    parser.add_argument('--port', default=8765, type=int)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    url = f'http://127.0.0.1:{server.server_address[1]}'
    print(f'Poker Lab v0.2: {url} (ローカル専用 / Ctrl+Cで終了)', flush=True)
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
