#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Safely install the Number touch keypad on an existing OpenPLC Runtime.

Updates only the TargetVisu Python files; no plc_main rebuild or PLC restart.
Run --check first. Compatible with Python 3.7+.
"""
import argparse
import ast
import datetime
import hashlib
import os
from pathlib import Path
import shutil
import sys

FILES = (
    'tools/targetvisu/keypad.py',
    'tools/targetvisu/graphics.py',
    'tools/targetvisu/render.py',
    'tools/targetvisu/model.py',
    'tools/targetvisu/viewer.py',
)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, help='Existing OpenPLC Runtime source folder')
    parser.add_argument('--check', action='store_true', help='Check only, do not install')
    args = parser.parse_args()
    source_root = Path(__file__).resolve().parents[2]
    target_root = Path(args.runtime).resolve()
    if not target_root.is_dir():
        parser.error('Runtime directory not found: {}'.format(target_root))
    if not (target_root / 'tools/targetvisu/viewer.py').is_file():
        parser.error('Target Runtime is missing tools/targetvisu/viewer.py')

    pending = []
    for rel in FILES:
        src = source_root / rel
        dst = target_root / rel
        if not src.is_file() or not dst.parent.is_dir():
            parser.error('Missing source or Runtime TargetVisu directory: {}'.format(rel))
        data = src.read_text(encoding='utf-8')
        ast.parse(data, filename=str(src))
        required = {
            'tools/targetvisu/keypad.py': 'def show(window, element, model, current):',
            'tools/targetvisu/model.py': "mode == 'input-output'",
            'tools/targetvisu/graphics.py': 'def select_graphic_data(',
            'tools/targetvisu/render.py': "screen.get('backgroundGraphic')",
            'tools/targetvisu/viewer.py': 'show_numeric_keypad(window, element, model, current)',
        }[rel]
        if required not in data:
            parser.error('File does not include Number keypad support: {}'.format(rel))
        if not dst.is_file() or sha256(src) != sha256(dst):
            pending.append((rel, src, dst))

    print('Runtime:', target_root)
    print('Changed/new files:', len(pending))
    for rel, _, dst in pending:
        print(' - {}{}'.format(rel, '' if dst.exists() else ' (new)'))
    if args.check or not pending:
        print('Check OK. No changes made.' if args.check else 'Already up to date.')
        return

    backup_root = target_root / ('targetvisu-number-input-backup-' +
                                 datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ'))
    backup_root.mkdir()
    for rel, _, dst in pending:
        if dst.exists():
            backup = backup_root / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(dst), str(backup))

    written = []
    try:
        for rel, src, dst in pending:
            temp = dst.with_name(dst.name + '.number-input-tmp')
            try:
                shutil.copy2(str(src), str(temp))
                os.replace(str(temp), str(dst))
                written.append((rel, dst))
            finally:
                if temp.exists():
                    temp.unlink()
    except Exception:
        for rel, dst in reversed(written):
            saved = backup_root / rel
            if saved.is_file():
                shutil.copy2(str(saved), str(dst))
            else:
                dst.unlink()
        raise
    print('TargetVisu Number keypad installed. Backup:', backup_root)
    print('Restart the graphical session when safe. No plc_main rebuild is required.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, SyntaxError, UnicodeError) as exc:
        sys.exit('Installation failed: {}'.format(exc))
