#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Register or migrate MQTT without changing other plugins' settings."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil

MQTT_PLUGIN = './core/src/drivers/plugins/python/mqtt/mqtt_plugin.py'
LEGACY_PLUGIN = './core/src/drivers/plugins/python/mqtt/plugin.py'
MQTT_CONFIG = './core/generated/conf/mqtt.json'
LEGACY_CONFIG = './core/src/drivers/plugins/python/mqtt/mqtt.json'
MQTT_VENV = './venvs/mqtt'
ENTRY = f'mqtt,{MQTT_PLUGIN},0,0,{MQTT_CONFIG},{MQTT_VENV}'


def _backup(path):
    if path.exists():
        backup = path.with_name('plugins.conf.backup.' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        shutil.copy2(path, backup)


def register(root, check=False):
    path = root / 'plugins.conf'
    if not (root / MQTT_PLUGIN).is_file():
        raise ValueError('MQTT entry point is missing; update the Runtime checkout first')
    text = path.read_text() if path.exists() else (root / 'plugins_default.conf').read_text()
    lines = text.splitlines(keepends=True)
    indices = [
        i for i, line in enumerate(lines)
        if line.strip() and not line.lstrip().startswith('#') and line.split(',', 1)[0].strip() == 'mqtt'
    ]
    if len(indices) > 1:
        raise ValueError('Multiple MQTT entries in plugins.conf; review manually')
    if indices:
        index = indices[0]
        fields = lines[index].rstrip('\r\n').split(',')
        if (len(fields) != 6 or fields[1].strip() not in (MQTT_PLUGIN, LEGACY_PLUGIN)
                or fields[3].strip() != '0' or fields[4].strip() not in (MQTT_CONFIG, LEGACY_CONFIG)
                or fields[5].strip() != MQTT_VENV):
            raise ValueError('Existing MQTT registration differs; review plugins.conf manually')
        # Retain the user's enabled flag, QoS/config and all other plugin entries.
        fields[1], fields[4] = MQTT_PLUGIN, MQTT_CONFIG
        newline = '\r\n' if lines[index].endswith('\r\n') else '\n'
        normalized = ','.join(fields) + newline
        changed = lines[index] != normalized or not path.exists()
        if check:
            print('MQTT registration needs migration; no files changed' if changed else 'MQTT already registered; no files changed')
            return
        if changed:
            _backup(path)
            lines[index] = normalized
            path.write_text(''.join(lines))
            print('MQTT registration updated; enabled flag and other plugins preserved')
        else:
            print('MQTT already registered; existing enable/config settings preserved')
        return
    if check:
        print('MQTT registration can be added; no files changed')
        return
    _backup(path)
    path.write_text(text.rstrip('\r\n') + '\n' + ENTRY + '\n')
    print('MQTT registered (disabled until a project with conf/mqtt.json is uploaded)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        register(Path(__file__).resolve().parents[1], args.check)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
