"""TargetVisu 0.5.0: verified, reversible Editor/Python-only Runtime update."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() if path.is_file() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--editor')
    target.add_argument('--runtime')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    kind = 'editor' if args.editor else 'runtime'
    root = Path(args.editor or args.runtime).resolve()
    package = Path(__file__).resolve().parent
    manifest = json.loads((package / (kind + '-manifest.json')).read_text(encoding='utf-8'))
    if not root.is_dir():
        parser.error('Target directory does not exist')
    pending = []
    problems = []
    for name, spec in manifest['files'].items():
        src, dst = package / kind / name, root / name
        if not dst.resolve().is_relative_to(root):
            problems.append('Target escapes root: ' + name)
            continue
        if digest(src) != spec['after']:
            problems.append('Package damaged: ' + name)
        current = digest(dst)
        if current == spec['after']:
            continue
        if current not in spec['before']:
            problems.append('Modified source needs merge: ' + name)
        pending.append((name, src, dst))
    for name, expected in manifest.get('dependencies', {}).items():
        if digest(root / name) not in expected:
            problems.append('Incompatible dependency: ' + name)
    if problems:
        parser.error('; '.join(problems) + '. No files changed. See README.ru.md.')
    if args.check:
        print('Compatible. Files to update:', len(pending))
        return
    if not pending:
        print('TargetVisu 0.5.0 already installed.')
        return
    backup = root / ('targetvisu-navigation-backup-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir()
    existed = {}
    for name, src, dst in pending:
        existed[name] = dst.exists()
        if existed[name]:
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, saved)
    (backup / 'created-files.json').write_text(json.dumps([n for n in existed if not existed[n]], indent=2))
    changed = []
    try:
        for name, src, dst in pending:
            changed.append((name, dst))
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    except Exception:
        for name, dst in reversed(changed):
            if existed[name]:
                shutil.copy2(backup / name, dst)
            else:
                dst.unlink(missing_ok=True)
        raise
    print('Installed TargetVisu 0.5.0:', kind)
    print('Backup:', backup)
    print('Rebuild/restart Editor.' if kind == 'editor' else 'Restart TargetVisu/X session. PLC core files were not changed.')


if __name__ == '__main__':
    main()
