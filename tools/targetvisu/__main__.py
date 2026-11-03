# SPDX-License-Identifier: GPL-3.0-only
import argparse
import sys
from .model import Model, load_json
from .backend import Runtime, Demo


def main():
    parser = argparse.ArgumentParser(description='OpenPLC native X11 TargetVisu 0.2.1')
    parser.add_argument('mode', choices=['check', 'serve', 'view'])
    parser.add_argument('--project', help='Runtime generated directory with uploaded TargetVisu')
    parser.add_argument('--document')
    parser.add_argument('--debug-map')
    parser.add_argument('--runtime-socket', default='/run/runtime/targetvisu/core.sock')
    parser.add_argument('--broker-socket', default='/run/openplc-targetvisu/control.sock')
    parser.add_argument('--demo', action='store_true', help='Explicit simulation; no Runtime connection')
    parser.add_argument('--fullscreen', action='store_true')
    args = parser.parse_args()
    try:
        if args.project:
            if args.document or args.debug_map or args.demo:
                parser.error('--project cannot be combined with --document, --debug-map or --demo')
            from .project import load_project
            model = load_project(args.project)
        else:
            if not args.document or not args.debug_map:
                parser.error('Specify --project or both --document and --debug-map')
            model = Model(load_json(args.document), load_json(args.debug_map))
        if args.mode == 'check':
            print(f'Valid: {len(model.doc["screens"])} screens, {len(model.paths)} scalar symbols; program {model.md5}')
        elif args.mode == 'serve':
            from .service import serve
            serve(model, Demo(model) if args.demo else Runtime(model, args.runtime_socket), args.broker_socket)
        else:
            from .viewer import run
            run(model, args.broker_socket, args.fullscreen, args.demo)
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        parser.exit(1, f'TargetVisu: {exc}\n')


if __name__ == '__main__':
    main()
