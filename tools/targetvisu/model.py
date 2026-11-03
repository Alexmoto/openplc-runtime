# SPDX-License-Identifier: GPL-3.0-only
"""Editor schema v1 and compiler-authoritative scalar bindings."""
import json
import math
import re
import struct
from pathlib import Path
from .graphics import validate_graphic

FORMATS = dict(BOOL='?', SINT='b', USINT='B', BYTE='B', INT='h', UINT='H', WORD='H',
               DINT='i', UDINT='I', DWORD='I', LINT='q', ULINT='Q', LWORD='Q', REAL='f', LREAL='d')
KINDS = {'rectangle', 'ellipse', 'line', 'text', 'indicator', 'button', 'number', 'graphic'}
ACTIONS = {'none', 'set', 'toggle', 'momentary', 'write', 'navigate'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    path = Path(path)
    require(path.stat().st_size <= 4 * 1024 * 1024, 'JSON exceeds 4 MiB')
    return json.loads(path.read_text(encoding='utf-8-sig'),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def number(value, low, high, label, integer=False):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high
            and (not integer or type(value) is int), f'Invalid {label}: {value!r}')


def document(raw):
    require(isinstance(raw, dict) and type(raw.get('version')) is int and raw.get('version') == 1 and raw.get('target') == 'native-x11',
            'Expected TargetVisu version 1 / native-x11')
    number(raw.get('refreshMs'), 100, 5000, 'refreshMs', True)
    screens = raw.get('screens')
    require(isinstance(screens, list) and 1 <= len(screens) <= 64, 'Expected 1..64 screens')
    ids, names = set(), set()
    def unique(obj):
        require(isinstance(obj, dict), 'Expected screen/element object')
        key = obj.get('id')
        require(isinstance(key, str) and 1 <= len(key) <= 128 and key not in ids, f'Duplicate/invalid id: {key}')
        ids.add(key)
    def color(obj, key):
        require(isinstance(obj.get(key), str) and re.fullmatch(r'#[0-9a-fA-F]{6}', obj[key]), f'Invalid color: {key}')
    for screen in screens:
        unique(screen)
        name = screen.get('name')
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', name)
                and name.lower() not in names, 'Invalid/duplicate screen name')
        names.add(name.lower())
        number(screen.get('width'), 160, 8192, 'screen width', True)
        number(screen.get('height'), 120, 8192, 'screen height', True)
        number(screen.get('grid'), 1, 100, 'grid', True)
        color(screen, 'background')
        elements = screen.get('elements')
        require(isinstance(elements, list) and len(elements) <= 1000, 'Too many elements')
        for e in elements:
            unique(e)
            require(e.get('kind') in KINDS, 'Unknown element kind')
            if e.get('kind') == 'graphic':
                validate_graphic(e.get('graphic'))
            require(isinstance(e.get('name'), str) and 1 <= len(e['name']) <= 80, 'Invalid name')
            for key in ('fill', 'activeFill', 'stroke', 'textColor'):
                color(e, key)
            for key in ('x', 'y'):
                number(e.get(key), 0, 8192, key)
            for key in ('width', 'height'):
                number(e.get(key), 8, 8192, key)
            require(e['x'] + e['width'] <= screen['width'] and e['y'] + e['height'] <= screen['height'], 'Element exceeds screen')
            number(e.get('strokeWidth'), 0, 20, 'strokeWidth')
            number(e.get('borderRadius', 0), 0, 100, 'borderRadius')
            number(e.get('fontSize'), 6, 200, 'fontSize', True)
            number(e.get('decimals'), 0, 6, 'decimals', True)
            number(e.get('minimum'), -float('inf'), float('inf'), 'minimum')
            number(e.get('maximum'), e['minimum'], float('inf'), 'maximum')
            require(isinstance(e.get('text'), str) and len(e['text']) <= 1024, 'Invalid text')
            require(e.get('lineDirection', 'horizontal') in {'horizontal', 'vertical', 'diagonal-down', 'diagonal-up'}, 'Invalid line direction')
            require(isinstance(e.get('bindings'), dict), 'Missing bindings')
            for key in ('value', 'visible', 'enabled'):
                require(isinstance(e['bindings'].get(key), str) and len(e['bindings'][key]) <= 256, 'Invalid binding')
            for key in ('fill', 'stroke', 'textColor'):
                binding = e['bindings'].get(key, '')
                require(isinstance(binding, str) and len(binding) <= 256, 'Invalid color binding')
                require(not binding or e['kind'] == 'number', 'Color bindings require Number')
            a = e.get('action', {})
            require(isinstance(a, dict), 'Invalid action object')
            if e['kind'] == 'graphic':
                require(a.get('kind') == 'none', 'Graphic view is display-only')
            require(a.get('kind') in ACTIONS and isinstance(a.get('target'), str) and len(a['target']) <= 256, 'Invalid action')
            require(type(a.get('value')) in (bool, int, float, str), 'Invalid action value')
            if type(a['value']) in (int, float):
                require(math.isfinite(a['value']), 'Non-finite action value')
            if isinstance(a['value'], str):
                require(len(a['value']) <= 256, 'Action value too long')
    require(raw.get('startScreen') in {s['id'] for s in screens}, 'Missing start screen')
    screen_ids = {s['id'] for s in screens}
    for screen in screens:
        for e in screen['elements']:
            if e['action']['kind'] == 'navigate':
                require(e['kind'] == 'button', 'navigate requires a button')
                require(e['action']['target'] in screen_ids, 'Navigation target screen is missing')
    return raw


class Model:
    def __init__(self, doc, debug_map):
        self.doc = document(doc)
        require(isinstance(debug_map, dict) and type(debug_map.get('version')) is int and debug_map.get('version') == 2 and isinstance(debug_map.get('leaves'), list), 'Expected debug-map v2')
        self.md5 = debug_map.get('md5', '').lower()
        require(re.fullmatch('[0-9a-f]{32}', self.md5), 'Invalid compiler md5')
        self.leaves = {}
        addresses = set()
        for leaf in debug_map['leaves']:
            require(isinstance(leaf, dict), 'Invalid compiler leaf')
            name = leaf.get('path')
            require(isinstance(name, str) and 1 <= len(name) <= 256 and name.lower() not in self.leaves, 'Invalid/duplicate compiler symbol')
            number(leaf.get('arrayIdx'), 0, 255, 'arrayIdx', True)
            number(leaf.get('elemIdx'), 0, 65535, 'elemIdx', True)
            number(leaf.get('size'), 1, 65535, 'compiler size', True)
            address = (leaf['arrayIdx'], leaf['elemIdx'])
            require(address not in addresses, f'Duplicate compiler address: {name}')
            addresses.add(address)
            self.leaves[name.lower()] = leaf
        self.elements = {e['id']: e for s in doc['screens'] for e in s['elements']}
        self.paths = set()
        for e in self.elements.values():
            for key, path in e['bindings'].items():
                if path:
                    leaf = self.leaf(path)
                    if key in ('visible', 'enabled') or (key == 'value' and e['kind'] == 'indicator'):
                        require(leaf['type'] == 'BOOL', f'{path} must be BOOL')
                    if key == 'value' and e['kind'] == 'number':
                        require(leaf['type'] in FORMATS and leaf['type'] != 'BOOL', f'{path} must be numeric')
                    if key in ('fill', 'stroke', 'textColor'):
                        require(e['kind'] == 'number' and leaf['type'] in FORMATS and
                                leaf['type'] not in ('BOOL', 'REAL', 'LREAL'),
                                f'{path}: color binding requires integer PLC variable')
                    self.paths.add(path.lower())
            a = e['action']
            if a['kind'] not in ('none', 'navigate'):
                leaf = self.leaf(a['target'])
                require(not leaf.get('constant', False) and not leaf.get('readOnly', False)
                        and not str(leaf.get('location', '')).upper().startswith('%I'), f'{a["target"]} is read-only')
                self.paths.add(a['target'].lower())
                if a['kind'] in ('toggle', 'momentary'):
                    require(leaf['type'] == 'BOOL', 'toggle/momentary requires BOOL')
                elif a['kind'] == 'set':
                    self.encode(a['target'], a['value'])
                elif a['kind'] == 'write':
                    require(e['kind'] == 'number' and leaf['type'] in FORMATS and leaf['type'] != 'BOOL', 'write requires a numeric element and target')
        require(len(self.paths) <= 1000, 'v0.1 supports at most 1000 referenced scalar symbols')
        self.paths = sorted(self.paths)

    def leaf(self, path):
        require(path.lower() in self.leaves, f'Unknown compiled symbol: {path}')
        leaf = self.leaves[path.lower()]
        datatype = leaf.get('type')
        require(datatype in FORMATS, f'Unsupported type {datatype} for {path}; v0.1 supports BOOL and numbers')
        require(leaf['size'] == struct.calcsize(FORMATS[datatype]), f'Type/size mismatch: {path}')
        return leaf

    def encode(self, path, value, endian='<'):
        leaf = self.leaf(path)
        fmt = FORMATS[leaf['type']]
        if fmt == '?':
            require(type(value) is bool, f'{path}: expected BOOL')
        else:
            require(type(value) in (int, float) and math.isfinite(value), f'{path}: expected finite number')
            if fmt not in ('f', 'd'):
                require(value == int(value), f'{path}: expected integer')
                value = int(value)
        try:
            result = struct.pack(endian + fmt, value)
            if fmt in ('f', 'd'):
                require(math.isfinite(struct.unpack(endian + fmt, result)[0]), 'Floating-point overflow')
            return result
        except (struct.error, OverflowError) as exc:
            raise ValueError(f'{path}: value outside IEC type range') from exc

    def decode(self, path, value, endian='<'):
        return struct.unpack(endian + FORMATS[self.leaf(path)['type']], value)[0]

    def bound(self, e, key, values, default=None):
        path = e['bindings'].get(key, '')
        return values.get(path.lower(), default) if path else default

    def visible(self, e, values):
        return bool(self.bound(e, 'visible', values, True))

    def enabled(self, e, values):
        return self.visible(e, values) and bool(self.bound(e, 'enabled', values, True))
