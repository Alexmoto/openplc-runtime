# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'core/src/drivers/plugins/python/mqtt'))
from mqtt_model import decode_message, encode_message, validate
from mqtt_engine import MqttEngine


def binding(**changes):
    return dict(id='sensor', variable='TEMPERATURE', topic='sensor/temp', direction='subscribe', qos=1, retain=False, jsonPointer='', type='REAL', size=4, arr=0, elem=0, **changes) if not changes else {**binding(), **changes}


def config(bindings=None):
    return dict(version=1, enabled=True, programMd5='a'*32, host='localhost', port=1883, clientId='', username='', password='', tls=False, caFile='', keepalive=30, intervalMs=100, bindings=bindings or [binding()])


@pytest.mark.parametrize('datatype,size,payload,expected', [('BOOL',1,b'true', True), ('BOOL',1,b'0',False), ('INT',2,b'-32768',-32768), ('UINT',2,b'65535',65535), ('LINT',8,b'9223372036854775807',9223372036854775807), ('REAL',4,b'21.5',21.5)])
def test_scalar_roundtrip(datatype, size, payload, expected):
    b = binding(type=datatype, size=size)
    assert json.loads(encode_message(decode_message(payload,b),b)) == expected


@pytest.mark.parametrize('datatype,payload', [('BOOL',b'2'), ('BOOL',b'"false"'), ('INT',b'32768'), ('UINT',b'-1'), ('INT',b'1.5'), ('REAL',b'NaN'), ('REAL',b'1e100'), ('REAL',b'true'), ('REAL',b'null'), ('REAL',b'\xff')])
def test_bad_payload(datatype, payload):
    with pytest.raises((ValueError, OverflowError)):
        decode_message(payload,binding(type=datatype))


def test_pointer_and_limit():
    assert decode_message(b'{"a/b":{"~v":[3.5]}}', binding(jsonPointer='/a~1b/~0v/0')) == struct.pack('=f',3.5)
    with pytest.raises(ValueError):
        decode_message(b' ' * 65537,binding())


def test_config_rejects_overlap_and_bad_addresses():
    validate(config())
    for b in [binding(arr=256),binding(qos=True),binding(topic='a/#'),binding(size=8)]:
        with pytest.raises(ValueError): validate(config([b]))
    with pytest.raises(ValueError): validate(config([binding(),binding(id='two')]))
    with pytest.raises(ValueError): validate(config([binding(),binding(id='out',direction='publish')]))


class Client:
    def __init__(self): self.subscribed=[]; self.published=[]
    def subscribe(self, topics): self.subscribed.append(topics); return 0, 1
    def publish(self, *args, **kwargs): self.published.append((args,kwargs)); return SimpleNamespace(rc=0)


def test_bounded_queue_retries_and_keeps_latest_on_failure():
    client=Client(); writes=[]; success=False
    def write(b, raw):
        writes.append(raw)
        return success
    engine=MqttEngine(config(),client,lambda b: None,write,lambda *a: None)
    for i in range(10000): engine.on_message(client,None,SimpleNamespace(topic='sensor/temp',payload=str(i).encode()))
    assert len(engine.pending)==1
    engine.tick()
    assert len(engine.pending)==1
    success=True
    engine.on_message(client,None,SimpleNamespace(topic='sensor/temp',payload=b'10000'))
    engine.tick()
    assert writes[-1]==struct.pack('=f',10000)
    assert not engine.pending


def test_disconnect_invalid_payload_and_reconnect():
    client=Client(); writes=[]; logs=[]
    config_=config([binding(),binding(id='out', direction='publish',topic='plc/out',retain=True)])
    engine=MqttEngine(config_,client,lambda b: struct.pack('=f',12),lambda b, raw: writes.append(raw) or True,lambda *a: logs.append(a))
    engine.on_connect(client,None,None,0,None)
    engine.tick()
    assert client.published[0] == (('plc/out','12.0'), {'qos':1,'retain':True})
    engine.on_message(client,None,SimpleNamespace(topic='sensor/temp',payload=b'bad'))
    engine.tick(False)
    assert not writes
    engine.on_disconnect(client,None,None,1,None)
    engine.tick()
    assert not writes and len(client.published)==1
    engine.on_connect(client,None,None,0,None)
    assert len(client.subscribed)==2


def test_register_preserves_existing_configuration(tmp_path):
    import importlib.util
    source = Path(__file__).resolve().parents[4] / 'tools/register_mqtt.py'
    spec = importlib.util.spec_from_file_location('register_mqtt', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    plugin = tmp_path / 'core/src/drivers/plugins/python/mqtt/mqtt_plugin.py'
    plugin.parent.mkdir(parents=True); plugin.write_text('')
    original = '# existing settings\nmodbus_master,custom.py,1,0,custom.json,customvenv\n'
    (tmp_path / 'plugins.conf').write_text(original)
    module.register(tmp_path, check=True)
    assert (tmp_path / 'plugins.conf').read_text() == original
    module.register(tmp_path)
    registered = (tmp_path / 'plugins.conf').read_text()
    assert registered == original + module.ENTRY + '\n'
    module.register(tmp_path)
    assert (tmp_path / 'plugins.conf').read_text() == registered
    assert len(list(tmp_path.glob('plugins.conf.backup.*'))) == 1


def test_register_migrates_old_entry_and_keeps_enabled_flag(tmp_path):
    import importlib.util
    source = Path(__file__).resolve().parents[4] / 'tools/register_mqtt.py'
    spec = importlib.util.spec_from_file_location('register_mqtt', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    plugin = tmp_path / 'core/src/drivers/plugins/python/mqtt/mqtt_plugin.py'
    plugin.parent.mkdir(parents=True)
    plugin.write_text('')
    old_line = ('mqtt,./core/src/drivers/plugins/python/mqtt/plugin.py,1,0,'
                './core/src/drivers/plugins/python/mqtt/mqtt.json,./venvs/mqtt')
    other_line = 'modbus_master,custom.py,1,0,custom.json,customvenv'
    conf = tmp_path / 'plugins.conf'
    conf.write_text(other_line + '\n' + old_line + '\n')
    module.register(tmp_path, check=True)
    assert old_line in conf.read_text()
    assert not list(tmp_path.glob('plugins.conf.backup.*'))
    module.register(tmp_path)
    assert conf.read_text() == other_line + '\n' + module.ENTRY.replace(',0,0,', ',1,0,') + '\n'
    assert len(list(tmp_path.glob('plugins.conf.backup.*'))) == 1
    module.register(tmp_path)
    assert len(list(tmp_path.glob('plugins.conf.backup.*'))) == 1


def test_mqtt_plugin_module_name_is_unique():
    root = Path(__file__).resolve().parents[4]
    defaults = (root / 'plugins_default.conf').read_text()
    mqtt_entry = next(line for line in defaults.splitlines() if line.startswith('mqtt,'))
    opc_entry = next(line for line in defaults.splitlines() if line.startswith('opcua,'))
    mqtt_module = Path(mqtt_entry.split(',')[1]).stem
    opc_module = Path(opc_entry.split(',')[1]).stem
    assert mqtt_module == 'mqtt_plugin'
    assert mqtt_module != opc_module
    assert (root / mqtt_entry.split(',')[1]).is_file()
