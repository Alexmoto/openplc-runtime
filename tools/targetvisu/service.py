# SPDX-License-Identifier: GPL-3.0-only
"""Private Unix socket broker. GTK/X11 never runs inside the PLC scan thread."""
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import stat
import threading
import time
from .model import require


class Engine:
    def __init__(self, model, backend):
        self.model, self.backend = model, backend
        self.lock = threading.RLock()
        self.values, self.error = {}, 'Connecting'
        self.updated = 0.0
        self.leases = {}  # target -> (owner, expiry); expired releases retried while backend offline
        self.held_elements = {}
        self.period = model.doc['refreshMs'] / 1000
        self.lease_seconds = max(1.0, self.period * 3)
        self.closed = threading.Event()

    def tick(self):
        with self.lock:
            now = time.monotonic()
            try:
                values = self.backend.poll()
                for path, (owner, expiry) in list(self.leases.items()):
                    element = self.model.elements[self.held_elements[path]]
                    if now >= expiry or not self.model.enabled(element, values):
                        self.backend.write(path, False)
                        del self.leases[path]
                        del self.held_elements[path]
                self.values, self.error, self.updated = values, '', time.monotonic()
            except (ValueError, OSError, ConnectionError) as exc:
                self.error = str(exc)
                self.values = {}

    def run(self):
        while not self.closed.is_set():
            self.tick()
            self.closed.wait(self.period)

    def online(self):
        return not self.error and time.monotonic() - self.updated <= max(2, self.period * 3)

    def release(self, owner):
        with self.lock:
            for path, (client, _) in list(self.leases.items()):
                if client == owner:
                    self.leases[path] = (client, 0)
            # Try immediately; periodic tick retries if Runtime is unavailable.
            self.tick()

    def request(self, request, owner):
        with self.lock:
            op = request.get('op')
            if op == 'poll':
                # Heartbeat belongs to a connected owner, not an element supplied by the UI.
                for path, (client, expiry) in list(self.leases.items()):
                    if client == owner and expiry > time.monotonic():
                        self.leases[path] = (client, time.monotonic() + self.lease_seconds)
                online = self.online()
                return dict(ok=True, online=online, error=self.error or ('' if online else 'Stale data'),
                            values=self.values if online else {},
                            md5=self.model.md5)
            if op == 'release':
                self.release(owner)
                return dict(ok=True)
            require(op == 'action', 'Unknown broker operation')
            require(self.online(), self.error or 'Runtime offline / stale')
            e = self.model.elements.get(request.get('id'))
            require(e is not None and self.model.enabled(e, self.values), 'Element hidden or disabled')
            action = e['action']
            kind, path = action['kind'], action['target'].lower()
            require(kind != 'none', 'Element has no action')
            if kind == 'navigate':
                self.values = self.backend.poll()
                require(self.model.enabled(e, self.values), 'Element hidden or disabled')
                self.release(owner)
                return dict(ok=True, screen=action['target'])
            require(path not in self.leases or self.leases[path][0] == owner, 'Target is held by another client')
            if kind == 'momentary':
                require(request.get('pressed') is True, 'Use release operation to release momentary controls')
                self.backend.write(path, True)
                self.leases[path] = (owner, time.monotonic() + self.lease_seconds)
                self.held_elements[path] = e['id']
            else:
                # Refresh before checking enables and toggling to avoid UI snapshot races.
                self.values = self.backend.poll()
                require(self.model.enabled(e, self.values), 'Element hidden or disabled')
                if kind == 'toggle':
                    value = not self.values[path]
                elif kind == 'write':
                    value = request.get('value')
                    require(type(value) in (int, float) and e['minimum'] <= value <= e['maximum'], 'Value outside widget limits')
                else:
                    value = action['value']
                self.backend.write(path, value)
            return dict(ok=True, queued=True)


def serve(model, backend, socket_path):
    engine = Engine(model, backend)
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            owner = id(self)
            self.request.settimeout(engine.lease_seconds)
            try:
                while True:
                    line = self.rfile.readline(65537)
                    if not line:
                        break
                    if len(line) > 65536:
                        break
                    try:
                        data = json.loads(line)
                        require(isinstance(data, dict), 'Expected JSON object')
                        reply = engine.request(data, owner)
                    except (ValueError, OSError, ConnectionError, KeyError, TypeError) as exc:
                        reply = dict(ok=False, error=str(exc))
                    self.wfile.write(json.dumps(reply, allow_nan=False).encode('utf-8') + b'\n')
                    self.wfile.flush()
            except (OSError, ConnectionError):
                pass
            finally:
                engine.release(owner)

    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True
        block_on_close = False
    path = Path(socket_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = path.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == os.geteuid() and not parent.st_mode & 0o022,
            'Use an owned directory without group/world write permission for the broker socket')
    if path.exists():
        # Refuse to steal an active socket or remove a non-socket path.
        require(stat.S_ISSOCK(path.lstat().st_mode), 'Broker path exists and is not a socket')
        with socket.socket(socket.AF_UNIX) as probe:
            try:
                probe.connect(str(path))
            except ConnectionRefusedError:
                path.unlink()
            else:
                raise ValueError('Broker already running')
    old_umask = os.umask(0o077)
    try:
        server = Server(str(path), Handler)
    finally:
        os.umask(old_umask)
    worker = threading.Thread(target=engine.run, daemon=True)
    worker.start()
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print('TargetVisu service: ' + str(path), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        engine.closed.set()
        worker.join(timeout=2)
        with engine.lock:
            for path_name, (owner, _) in list(engine.leases.items()):
                engine.leases[path_name] = (owner, 0)
            engine.tick()
        server.server_close()
        path.unlink(missing_ok=True)


class Client:
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(2)
        self.sock.connect(path)
        self.stream = self.sock.makefile('rwb')

    def request(self, request):
        self.stream.write(json.dumps(request, allow_nan=False).encode('utf-8') + b'\n')
        self.stream.flush()
        line = self.stream.readline(1048577)
        if not line or len(line) > 1048576:
            raise ConnectionError('Broker disconnected / oversized response')
        result = json.loads(line)
        if not result.get('ok'):
            raise ValueError(result.get('error', 'Broker error'))
        return result

    def close(self):
        self.stream.close()
        self.sock.close()
