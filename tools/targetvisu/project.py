# SPDX-License-Identifier: GPL-3.0-only
"""Load the exact document and write permissions emitted by Editor 0.2.1."""
import hashlib
import json
from pathlib import Path
from .model import Model, load_json, require


def load_project(directory):
    root = Path(directory).resolve()
    manifest_path = root / 'conf/targetvisu-project.json'
    manifest = load_json(manifest_path)
    require(isinstance(manifest, dict) and type(manifest.get('version')) is int
            and manifest['version'] == 1 and manifest.get('target') == 'native-x11',
            'Unsupported TargetVisu deployment manifest')
    with (root / 'conf/targetvisu.json').open('rb') as stream:
        contents = stream.read(4 * 1024 * 1024 + 1)
    require(len(contents) <= 4 * 1024 * 1024, 'TargetVisu document exceeds 4 MiB')
    require(hashlib.md5(contents).hexdigest() == manifest.get('documentMd5'),
            'Document / manifest mismatch; finish Upload and restart TargetVisu')
    doc = json.loads(contents.decode('utf-8-sig'),
                     parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    debug_map = load_json(root / 'debug-map.json')
    require(isinstance(debug_map, dict) and isinstance(debug_map.get('md5'), str)
            and debug_map['md5'].lower() == manifest.get('programMd5'),
            'Deployment / compiled program mismatch')
    writable = manifest.get('writableSymbols')
    require(isinstance(writable, list) and all(isinstance(p, str) and p for p in writable),
            'Missing TargetVisu write permissions')
    allowed = {p.lower() for p in writable}
    require(len(allowed) == len(writable), 'Duplicate TargetVisu write permission')
    require(isinstance(debug_map.get('leaves'), list), 'Invalid compiler leaves')
    for leaf in debug_map['leaves']:
        require(isinstance(leaf, dict) and isinstance(leaf.get('path'), str), 'Invalid compiled symbol')
        leaf['readOnly'] = bool(leaf.get('readOnly', False)) or leaf['path'].lower() not in allowed
    model = Model(doc, debug_map)
    require(allowed.issubset(model.leaves), 'Unknown symbol in TargetVisu write permissions')
    require(load_json(manifest_path) == manifest, 'Upload changed while loading; restart TargetVisu')
    return model
