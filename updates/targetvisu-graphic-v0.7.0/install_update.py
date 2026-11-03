#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Install the Graphic View image-state update into an existing OpenPLC Runtime checkout.

This updates only TargetVisu Python rendering/model files. It does not modify
PLC logic, retention, the native binary, or the active TargetVisu project.
Compatible with Python 3.7+.
"""
import argparse
import ast
import datetime
import hashlib
import os
from pathlib import Path
import shutil
import sys

FILES = ('tools/targetvisu/model.py', 'tools/targetvisu/render.py', 'tools/targetvisu/graphics.py')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, help='Existing live runtime source directory')
    parser.add_argument('--check', action='store_true', help='Validate only; do not copy or restart anything')
    args = parser.parse_args()
    source_root = Path(__file__).resolve().parents[2]
    target_root = Path(args.runtime).resolve()

    if not target_root.is_dir():
        parser.error('Runtime directory not found: {}'.format(target_root))

    pending = []
    for rel in FILES:
        src = source_root / rel
        dst = target_root / rel
        if not src.is_file() or not dst.is_file():
            parser.error('Missing source or installed Runtime file: {}'.format(rel))
        if rel.endswith('model.py'):
            if 'image selector requires BOOL or 32-bit integer PLC variable' not in src.read_text(encoding='utf-8'):
                parser.error('Source model.py does not contain the Graphic View image-state update.')
        if rel.endswith('render.py'):
            if "draw_graphic(ctx, e, model.bound(e, 'value', values)" not in src.read_text(encoding='utf-8'):
                parser.error('Source render.py does not contain the image-state update.')
        if rel.endswith('graphics.py'):
            if 'def select_graphic_data(' not in src.read_text(encoding='utf-8'):
                parser.error('Source graphics.py does not contain the image-state update.')
        # Syntax-check sources before any installation.
        ast.parse(src.read_text(encoding='utf-8'), filename=str(src))
        if digest(src) != digest(dst):
            pending.append((rel, src, dst))

    print('Runtime:', target_root)
    print('Changed files:', len(pending))
    for rel, _, _ in pending:
        print(' -', rel)
    if args.check or not pending:
        print('Check OK. No changes made.' if args.check else 'Already up to date.')
        return

    backup_root = target_root / ('targetvisu-graphic-backup-' +
                                 datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ'))
    backup_root.mkdir()
    for rel, _, dst in pending:
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(dst), str(backup))

    changed = []
    try:
        for rel, src, dst in pending:
            staging = dst.with_name(dst.name + '.number-update-tmp')
            try:
                shutil.copy2(str(src), str(staging))
                os.replace(str(staging), str(dst))
                changed.append((rel, dst))
            finally:
                if staging.exists():
                    staging.unlink()
    except Exception:
        for rel, dst in reversed(changed):
            shutil.copy2(str(backup_root / rel), str(dst))
        raise
    print('Updated successfully. Backup:', backup_root)
    print('Restart the TargetVisu graphical session when safe; do not rebuild plc_main.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, SyntaxError, UnicodeError) as exc:
        sys.exit('Installation failed: {}'.format(exc))
