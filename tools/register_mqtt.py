#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Register MQTT in an existing checkout without replacing other plugin settings."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil

ENTRY = 'mqtt,./core/src/drivers/plugins/python/mqtt/plugin.py,0,0,./core/generated/conf/mqtt.json,./venvs/mqtt'


def register(root, check=False):
    path = root / 'plugins.conf'
    if not (root / 'core/src/drivers/plugins/python/mqtt/plugin.py').is_file():
        raise ValueError('MQTT plugin is missing; update the Runtime checkout first')
    text = path.read_text() if path.exists() else (root / 'plugins_default.conf').read_text()
    entries = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#') and line.split(',')[0].strip() == 'mqtt']
    if entries:
        parts = entries[0].split(',')
        if len(entries) != 1 or len(parts) < 6 or parts[1].strip() != ENTRY.split(',')[1] or parts[3].strip() != '0' or parts[5].strip() != './venvs/mqtt':
            raise ValueError('Existing MQTT registration differs; review plugins.conf manually')
        if not path.exists() and not check:
            path.write_text(text)
        print('MQTT already registered; existing enable/config settings preserved')
        return
    if check:
        print('MQTT registration can be added; no files changed')
        return
    if path.exists():
        backup = path.with_name('plugins.conf.backup.' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        shutil.copy2(path, backup)
    # Append only: preserve every existing plugin and its configuration.
    with path.open('a') as stream:
        if not path.stat().st_size:
            stream.write(text.rstrip() + '\n')
        elif text and not text.endswith('\n'):
            stream.write('\n')
        stream.write(ENTRY + '\n')
    print('MQTT registered (disabled until a project with conf/mqtt.json is uploaded)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        register(Path(__file__).resolve().parents[1], args.check)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
