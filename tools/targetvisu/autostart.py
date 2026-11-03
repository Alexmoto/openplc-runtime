# SPDX-License-Identifier: GPL-3.0-only
"""X-session supervisor: launch only for a valid uploaded project in RUN."""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from .backend import Runtime
from .project import load_project

FILES = ('conf/targetvisu.json', 'conf/targetvisu-project.json', 'debug-map.json')


def fingerprint(project):
    digest = hashlib.sha256()
    for name in FILES:
        with (project / name).open('rb') as stream:
            data = stream.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError('Project JSON exceeds 4 MiB')
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return digest.digest()


class Supervisor:
    def __init__(self, project, runtime_socket, broker_socket, fullscreen=True):
        self.project = Path(project).resolve()
        self.runtime_socket, self.broker_socket = runtime_socket, broker_socket
        self.fullscreen = fullscreen
        self.children = []
        self.key = None
        self.retry_at = 0
        self.last_error = None

    def stop(self):
        children, self.children = self.children, []
        self.key = None
        # Close the viewer first; broker releases any held momentary controls.
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()

    def tick(self):
        try:
            key = fingerprint(self.project)
            model = load_project(self.project)
            if fingerprint(self.project) != key:
                raise ValueError('Upload in progress')
            Runtime(model, self.runtime_socket).handshake()
            if self.children and self.key == key and all(p.poll() is None for p in self.children):
                return
            self.stop()
            if time.monotonic() < self.retry_at:
                return
            self.retry_at = time.monotonic() + 3
            base = [sys.executable, '-m', 'targetvisu']
            common = ['--project', str(self.project), '--broker-socket', self.broker_socket]
            cwd = str(Path(__file__).resolve().parent.parent)
            self.children.append(subprocess.Popen(base + ['serve'] + common + ['--runtime-socket', self.runtime_socket], cwd=cwd))
            self.children.append(subprocess.Popen(base + ['view'] + common + (['--fullscreen'] if self.fullscreen else []), cwd=cwd))
            self.key = key
            self.last_error = None
            print('TargetVisu: project RUN, viewer started', flush=True)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            self.stop()
            message = str(exc)
            if message != self.last_error:
                print('TargetVisu waiting: ' + message, flush=True)
                self.last_error = message


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--runtime-socket', default='/run/runtime/targetvisu/core.sock')
    parser.add_argument('--broker-socket', default='/run/openplc-targetvisu/control.sock')
    parser.add_argument('--windowed', action='store_true')
    args = parser.parse_args()
    if not os.environ.get('DISPLAY'):
        parser.error('Run from the local X11 session; DISPLAY is missing')
    state = Path.home() / '.local/state/openplc-targetvisu'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / 'supervisor.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        closed = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: closed.set())
        signal.signal(signal.SIGINT, lambda *_: closed.set())
        supervisor = Supervisor(args.project, args.runtime_socket, args.broker_socket, not args.windowed)
        try:
            while not closed.is_set():
                supervisor.tick()
                closed.wait(1)
        finally:
            supervisor.stop()


if __name__ == '__main__':
    main()
