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
