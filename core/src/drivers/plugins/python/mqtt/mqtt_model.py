# SPDX-License-Identifier: GPL-3.0-only
"""MQTT v1 contract and scalar codecs. No network or runtime dependency."""
import json
import math
import re
import struct

FORMATS = dict(BOOL='?', SINT='b', USINT='B', BYTE='B', INT='h', UINT='H', WORD='H', DINT='i', UDINT='I', DWORD='I', LINT='q', ULINT='Q', LWORD='Q', REAL='f', LREAL='d')


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def validate(config):
    if not isinstance(config, dict) or config.get('version') != 1 or config.get('enabled') is not True:
        raise ValueError('MQTT: unsupported or disabled configuration')
    for key, limit in [('host', 253), ('clientId', 128), ('username', 256), ('password', 1024), ('caFile', 1024)]:
        if not isinstance(config.get(key), str) or len(config[key]) > limit or '\0' in config[key]:
            raise ValueError(f'MQTT: invalid {key}')
    if not config['host'].strip() or type(config.get('tls')) is not bool:
        raise ValueError('MQTT: invalid connection settings')
    for key, low, high in [('port', 1, 65535), ('keepalive', 5, 3600), ('intervalMs', 100, 60000)]:
        if not integer(config.get(key), low, high):
            raise ValueError(f'MQTT: invalid {key}')
    if not isinstance(config.get('programMd5'), str) or not re.fullmatch('[a-f0-9]{32}', config['programMd5']):
        raise ValueError('MQTT: invalid program hash')
    bindings = config.get('bindings')
    if not isinstance(bindings, list) or not 1 <= len(bindings) <= 256:
        raise ValueError('MQTT: expected 1..256 bindings')
    inputs, outputs, ids = set(), set(), set()
    for b in bindings:
        if not isinstance(b, dict) or b.get('direction') not in ('subscribe', 'publish'):
            raise ValueError('MQTT: invalid direction')
        for key in ('id', 'variable', 'topic'):
            if not isinstance(b.get(key), str) or not b[key] or len(b[key]) > 1024 or '\0' in b[key]:
                raise ValueError(f'MQTT: invalid binding {key}')
        if any(c in b['topic'] for c in '+#') or b['id'] in ids:
            raise ValueError('MQTT: wildcard topic or duplicate binding')
        ids.add(b['id'])
        if b.get('type') not in FORMATS or b.get('size') != struct.calcsize('=' + FORMATS[b['type']]):
            raise ValueError('MQTT: invalid scalar type/size')
        if not integer(b.get('arr'), 0, 255) or not integer(b.get('elem'), 0, 65535) or not integer(b.get('qos'), 0, 2) or type(b.get('retain')) is not bool:
            raise ValueError('MQTT: invalid address/QoS/retain')
        pointer = b.get('jsonPointer')
        if not isinstance(pointer, str) or len(pointer) > 512 or (pointer and (not pointer.startswith('/') or re.search('~(?![01])', pointer))):
            raise ValueError('MQTT: invalid JSON pointer')
        mode = b.get('publishMode', 'interval')
        if b['direction'] == 'publish':
            if mode not in ('interval', 'on-change'):
                raise ValueError('MQTT: invalid publish mode')
            if 'publishIntervalMs' in b and not integer(b['publishIntervalMs'], 100, 60000):
                raise ValueError('MQTT: invalid publish interval')
        elif 'publishMode' in b or 'publishIntervalMs' in b:
            raise ValueError('MQTT: publish options require publish direction')
        if b['direction'] == 'subscribe':
            address = (b['arr'], b['elem'])
            if address in inputs:
                raise ValueError('MQTT: duplicate input address')
            inputs.add(address)
        else:
            if pointer or b['topic'] in outputs:
                raise ValueError('MQTT: invalid or duplicate publisher')
            outputs.add(b['topic'])
    if any(b['direction'] == 'subscribe' and b['topic'] in outputs for b in bindings):
        raise ValueError('MQTT: publish/subscribe feedback topic')
    return config



def validate_bundle(data):
    """Return independent v1 connection configurations from v1 or v2 uploads.

    v2 is one PLC program/debug-map with 1..8 named MQTT connections. A
    subscription address has one producer across *all* connections.
    """
    if not isinstance(data, dict):
        raise ValueError('MQTT: invalid configuration')
    if data.get('version') == 1:
        return [('Legacy MQTT', validate(data))]
    if data.get('version') != 2 or data.get('enabled') is not True:
        raise ValueError('MQTT: invalid bundle version')
    md5 = data.get('programMd5')
    if not isinstance(md5, str) or not re.fullmatch('[a-f0-9]{32}', md5):
        raise ValueError('MQTT: invalid program hash')
    connections = data.get('connections')
    if not isinstance(connections, list) or not 1 <= len(connections) <= 8:
        raise ValueError('MQTT: expected 1..8 connections')
    names, inputs, client_ids = set(), set(), set()
    total_bindings = 0
    result = []
    for item in connections:
        if not isinstance(item, dict):
            raise ValueError('MQTT: invalid connection')
        name = item.get('name')
        if not isinstance(name, str) or not name.strip() or len(name) > 100 or '\0' in name:
            raise ValueError('MQTT: invalid connection name')
        if name.casefold() in names:
            raise ValueError('MQTT: duplicate connection name')
        names.add(name.casefold())
        # Inherit only the program identity from the v2 envelope.
        if item.get('version', 1) != 1 or item.get('enabled') is not True:
            raise ValueError('MQTT: disabled/invalid connection')
        if 'programMd5' in item and item['programMd5'] != md5:
            raise ValueError('MQTT: connection hash mismatch')
        validated = validate({**item, 'version': 1, 'programMd5': md5})
        total_bindings += len(validated['bindings'])
        if total_bindings > 256:
            raise ValueError('MQTT: maximum 256 bindings across connections')
        for binding in validated['bindings']:
            if binding['direction'] != 'subscribe':
                continue
            address = (binding['arr'], binding['elem'])
            if address in inputs:
                raise ValueError('MQTT: multiple subscriptions write one PLC variable')
            inputs.add(address)
        if validated['clientId']:
            identity = (validated['host'].casefold(), validated['port'], validated['clientId'])
            if identity in client_ids:
                raise ValueError('MQTT: duplicate client ID on the same broker')
            client_ids.add(identity)
        result.append((name, validated))
    return result


def encode(value, datatype):
    fmt = FORMATS[datatype]
    if datatype == 'BOOL':
        if type(value) is bool:
            pass
        elif type(value) is int and value in (0, 1):
            value = bool(value)
        else:
            raise ValueError('expected boolean or 0/1')
    elif datatype in ('REAL', 'LREAL'):
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError('expected finite number')
    elif type(value) is not int:
        raise ValueError('expected integer')
    try:
        raw = struct.pack('=' + fmt, value)
        if datatype in ('REAL', 'LREAL') and not math.isfinite(struct.unpack('=' + fmt, raw)[0]):
            raise ValueError('floating point overflow')
        return raw
    except (struct.error, OverflowError) as exc:
        raise ValueError('value outside IEC type range') from exc


def decode_message(payload, binding):
    if len(payload) > 65536:
        raise ValueError('payload exceeds 64 KiB')
    value = json.loads(payload.decode('utf-8'))
    if binding['jsonPointer']:
        for token in binding['jsonPointer'][1:].split('/'):
            token = token.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list) and re.fullmatch('0|[1-9][0-9]*', token):
                value = value[int(token)]
            elif isinstance(value, dict):
                value = value[token]
            else:
                raise ValueError('JSON pointer not found')
    return encode(value, binding['type'])


def encode_message(raw, binding):
    if len(raw) != binding['size']:
        raise ValueError('runtime read size mismatch')
    value = struct.unpack('=' + FORMATS[binding['type']], raw)[0]
    # JSON numbers preserve 64-bit integer precision in this Python codec.
    return json.dumps(value, allow_nan=False, separators=(',', ':'))
