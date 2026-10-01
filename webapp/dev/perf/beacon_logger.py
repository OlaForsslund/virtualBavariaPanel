#!/usr/bin/env python3
"""Receives perf-probe.js beacons and appends them as JSON lines.

Usage: beacon_logger.py [--port 8099] [--out perf-log.jsonl]
Standard library only; answers every request with 204.
"""
import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit


def make_handler(out_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == '/b':
                record = {
                    'ts': datetime.now().astimezone().isoformat(timespec='seconds'),
                    'ip': self.client_address[0],
                    'ua': self.headers.get('User-Agent', ''),
                    **dict(parse_qsl(url.query)),
                }
                with open(out_path, 'a') as f:
                    f.write(json.dumps(record) + '\n')
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8099)
    parser.add_argument('--out', default='perf-log.jsonl')
    args = parser.parse_args()
    ThreadingHTTPServer(('0.0.0.0', args.port), make_handler(args.out)).serve_forever()


if __name__ == '__main__':
    main()
