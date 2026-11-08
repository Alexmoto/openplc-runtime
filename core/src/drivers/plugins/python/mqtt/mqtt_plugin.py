# SPDX-License-Identifier: GPL-3.0-only
"""OpenPLC Runtime v4 MQTT data source plugin."""
import ctypes
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared import safe_extract_runtime_args_from_capsule, SafeBufferAccess, SafeLoggingAccess
from shared.image_sizes import set_image_sizes  # declares support for per-table sizing
from mqtt_model import validate
from mqtt_engine import MqttEngine

_engine = None
_args = None
_logger = None


def _log(level, message):
    if _logger is not None and _logger.is_valid:
        getattr(_logger, 'log_' + level)(message)


def _read(binding):
    # Always reserve the maximum debug scalar/string buffer, even if a stale
    # config somehow reaches this point. Never allocate a narrow destination.
    buffer = (ctypes.c_uint8 * 256)()
    _args.image_lock()
    try:
        if _args.debug_size(binding['arr'], binding['elem']) != binding['size']:
            return None
        size = _args.debug_read(binding['arr'], binding['elem'], buffer)
        return bytes(buffer[:size]) if size == binding['size'] else None
    finally:
        _args.image_unlock()


def _write(binding, raw):
    if _args.debug_size(binding['arr'], binding['elem']) != binding['size']:
        return False
    buffer = (ctypes.c_uint8 * len(raw)).from_buffer_copy(raw)
    # Runtime queues this soft write and applies it between PLC scans.
    return _args.debug_write(binding['arr'], binding['elem'], buffer, len(raw)) == 0x7e


def init(capsule):
    global _args, _logger, _engine
    try:
        _args, error = safe_extract_runtime_args_from_capsule(capsule)
        if _args is None:
            return False
        _logger = SafeLoggingAccess(_args)
        accessor = SafeBufferAccess(_args)
        path, error = accessor.get_config_path()
        if not path:
            raise ValueError('missing config path')
        with open(path, encoding='utf-8') as stream:
            config = validate(json.load(stream))
        with open(Path(path).resolve().parent.parent / 'debug-map.json', encoding='utf-8') as stream:
            debug_map = json.load(stream)
        if debug_map.get('md5', '').lower() != config['programMd5'] or debug_map.get('version') != 2:
            raise ValueError('program / MQTT configuration mismatch')
        leaves = {leaf['path']: leaf for leaf in debug_map['leaves']}
        for b in config['bindings']:
            leaf = leaves.get(b['variable'], {})
            if (leaf.get('arrayIdx'), leaf.get('elemIdx'), leaf.get('type'), leaf.get('size')) != (b['arr'], b['elem'], b['type'], b['size']):
                raise ValueError('compiled variable mismatch')
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config['clientId'], clean_session=True, protocol=mqtt.MQTTv311)
        client.max_queued_messages_set(256)
        client.max_inflight_messages_set(20)
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.connect_timeout = 5.0
        if config['username']:
            client.username_pw_set(config['username'], config['password'])
        if config['tls']:
            client.tls_set(ca_certs=config['caFile'] or None)
        _engine = MqttEngine(config, client, _read, _write, _log)
        return True
    except Exception as exc:
        # Do not log config/payloads or exception text which can include credentials.
        _log('error', f'MQTT initialization failed ({type(exc).__name__}); check configuration, debug map and paho-mqtt installation')
        return False


def start_loop():
    if _engine is None:
        return False
    _engine.start()
    return True


def stop_loop():
    if _engine is not None:
        _engine.stop()
    return True


def cleanup():
    global _engine, _args, _logger
    stop_loop()
    _engine = _args = _logger = None
    return True
