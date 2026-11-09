# SPDX-License-Identifier: GPL-3.0-only
import copy
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from targetvisu.model import Model, load_json
from targetvisu.backend import Demo, Runtime
from targetvisu.service import Engine, Client
from targetvisu.render import geometry, hit

ROOT = Path(__file__).parents[1]


def fixture():
    return Model(load_json(ROOT / 'example.targetvisu.json'), load_json(ROOT / 'example.debug-map.json'))


def action_element(model, kind, target='Pump1.StartRequest'):
    e = next(e for e in model.elements.values() if e['kind'] == 'button')
    e['action'] = dict(kind=kind, target=target, value=True)
    return e


class ModelTests(unittest.TestCase):
    def test_example_and_case_insensitive_resolution(self):
        m = fixture()
        self.assertEqual(m.leaf('PUMP1.pReSsUrE')['type'], 'REAL')
        self.assertEqual(m.decode('Pump1.Pressure', m.encode('Pump1.Pressure', 12.5)), 12.5)

    def test_invalid_schema(self):
        original = fixture()
        for modify in (lambda d: d.update(version=2), lambda d: d.update(startScreen='missing'),
                       lambda d: d['screens'][0].update(width=10),
                       lambda d: d['screens'][0]['elements'][0].update(x=9999),
                       lambda d: d['screens'][0]['elements'][0].update(fontSize=0),
                       lambda d: d['screens'][0]['elements'][0].update(fill='red')):
            doc = copy.deepcopy(original.doc)
            modify(doc)
            with self.assertRaises(ValueError):
                Model(doc, load_json(ROOT / 'example.debug-map.json'))

    def test_number_dynamic_colors_and_legacy_defaults(self):
        from targetvisu.render import bound_color, rounded_rect
        original = fixture()
        doc = copy.deepcopy(original.doc)
        e = next(e for e in doc['screens'][0]['elements'] if e['kind'] == 'number')
        # Missing new fields remain supported by the Runtime.
        e.pop('borderRadius', None)
        e['bindings'].pop('fill', None)
        e['bindings'].pop('stroke', None)
        e['bindings'].pop('textColor', None)
        debug_map = load_json(ROOT / 'example.debug-map.json')
        Model(doc, debug_map)
        e['borderRadius'] = 12
        self.assertEqual(bound_color(original, e, 'fill', {}), e['fill'])
        e['bindings']['fill'] = 'Pump1.Pressure'
        with self.assertRaisesRegex(ValueError, 'integer PLC variable'):
            Model(doc, debug_map)
        leaf = next(leaf for leaf in debug_map['leaves'] if leaf['path'].lower() == 'pump1.pressure')
        leaf['type'], leaf['size'] = 'DWORD', 4
        model = Model(doc, debug_map)
        self.assertEqual(bound_color(model, e, 'fill', {'pump1.pressure': 0x12AB34}), '#12ab34')
        self.assertEqual(bound_color(model, e, 'fill', {}), e['fill'])
        e['borderRadius'] = 101
        with self.assertRaisesRegex(ValueError, 'borderRadius'):
            Model(doc, debug_map)

    def test_transparent_button_and_number_keep_full_hit_area(self):
        m = fixture()
        doc = copy.deepcopy(m.doc)
        debug_map = load_json(ROOT / 'example.debug-map.json')
        screen = doc['screens'][0]
        button = next(e for e in screen['elements'] if e['kind'] == 'button')
        numeric = next(e for e in screen['elements'] if e['kind'] == 'number')
        button['fillTransparent'] = True
        button['strokeTransparent'] = True
        numeric['fillTransparent'] = True
        numeric['strokeTransparent'] = False
        screen['elements'] = [numeric, button]
        model = Model(doc, debug_map)
        button['action'] = dict(kind='toggle', target='Pump1.StartRequest', value=True)
        # Every point inside the rectangular button (including corners) can trigger its action.
        for x, y in ((button['x'] + 1, button['y'] + 1),
                     (button['x'] + button['width'] / 2, button['y'] + button['height'] / 2),
                     (button['x'] + button['width'] - 1, button['y'] + button['height'] - 1)):
            self.assertIs(hit(model, screen, {}, x, y), button)
        button.pop('fillTransparent')
        button.pop('strokeTransparent')
        Model(doc, debug_map)  # older projects are compatible
        button['fillTransparent'] = 'true'
        with self.assertRaisesRegex(ValueError, 'fillTransparent'):
            Model(doc, debug_map)
        button['fillTransparent'] = True
        numeric['kind'] = 'text'
        with self.assertRaisesRegex(ValueError, 'fillTransparent'):
            Model(doc, debug_map)

    def test_number_mode_write_target_must_match_displayed_variable(self):
        doc = copy.deepcopy(fixture().doc)
        debug_map = load_json(ROOT / 'example.debug-map.json')
        number = next(e for e in doc['screens'][0]['elements'] if e['id'] == 'Setpoint')
        number['numberMode'] = 'input-output'
        model = Model(doc, debug_map)
        self.assertEqual(model.elements['Setpoint']['action']['target'], 'Pump1.Setpoint')
        number['action']['target'] = 'Pump1.Pressure'
        with self.assertRaisesRegex(ValueError, 'displayed value variable'):
            Model(doc, debug_map)
        number['action']['target'] = 'Pump1.Setpoint'
        number['numberMode'] = 'output'
        with self.assertRaisesRegex(ValueError, 'Output mode'):
            Model(doc, debug_map)
        number.pop('numberMode')
        Model(doc, debug_map)  # Older projects with a write action stay usable.
        number['numberMode'] = 'input-output'
        number['bindings']['value'] = ''
        with self.assertRaisesRegex(ValueError, 'displayed value variable'):
            Model(doc, debug_map)
        number['bindings']['value'] = 'Pump1.Setpoint'
        data = copy.deepcopy(debug_map)
        next(leaf for leaf in data['leaves'] if leaf['path'] == 'Pump1.Setpoint')['readOnly'] = True
        with self.assertRaisesRegex(ValueError, 'read-only'):
            Model(doc, data)
        number['numberMode'] = 'something'
        with self.assertRaisesRegex(ValueError, 'Number mode'):
            Model(doc, debug_map)

    def test_12_color_indicator_accepts_integer_but_preserves_classic_bool(self):
        original = fixture()
        doc = copy.deepcopy(original.doc)
        data = load_json(ROOT / 'example.debug-map.json')
        indicator = next(e for e in doc['screens'][0]['elements'] if e['kind'] == 'indicator')
        # Legacy Indicator without style remains BOOL-based.
        Model(doc, data)
        indicator['indicatorStyle'] = 'lamp12'
        indicator['bindings']['value'] = 'Pump1.Setpoint'
        with self.assertRaisesRegex(ValueError, '32-bit or smaller integer'):
            Model(doc, data)
        leaf = next(leaf for leaf in data['leaves'] if leaf['path'] == 'Pump1.Setpoint')
        leaf.update(type='INT', size=2)
        Model(doc, data)
        indicator['bindings']['value'] = ''
        with self.assertRaisesRegex(ValueError, 'requires a PLC value variable'):
            Model(doc, data)
        indicator['bindings']['value'] = 'Pump1.Setpoint'
        indicator['action'] = dict(kind='toggle', target='Pump1.StartRequest', value=True)
        with self.assertRaisesRegex(ValueError, 'display-only'):
            Model(doc, data)
        indicator['action'] = dict(kind='none', target='', value=True)
        indicator['indicatorStyle'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'Invalid Indicator style'):
            Model(doc, data)
        indicator['indicatorStyle'] = 'classic'
        indicator['bindings']['value'] = 'Pump1.Running'
        Model(doc, data)
        indicator.pop('indicatorStyle')
        Model(doc, data)

    def test_unknown_symbol_no_address_guess(self):
        m = fixture()
        doc = copy.deepcopy(m.doc)
        doc['screens'][0]['elements'][0]['bindings']['value'] = 'main.Pressure'
        with self.assertRaisesRegex(ValueError, 'Unknown compiled'):
            Model(doc, load_json(ROOT / 'example.debug-map.json'))

    def test_bad_compiler_size(self):
        data = load_json(ROOT / 'example.debug-map.json')
        data['leaves'][0]['size'] = 8
        with self.assertRaisesRegex(ValueError, 'size mismatch'):
            Model(fixture().doc, data)

    def test_readonly_target_rejected(self):
        data = load_json(ROOT / 'example.debug-map.json')
        data['leaves'][2]['readOnly'] = True
        with self.assertRaisesRegex(ValueError, 'read-only'):
            Model(fixture().doc, data)

    def test_boolean_and_numeric_types(self):
        m = fixture()
        for path, value in [('Pump1.StartRequest', 1), ('Pump1.Setpoint', True),
                            ('Pump1.Setpoint', float('nan')), ('Pump1.Setpoint', 1e100)]:
            with self.assertRaises(ValueError):
                m.encode(path, value)
        self.assertEqual(m.encode('Pump1.StartRequest', True), b'\1')

    def test_integer_limits_and_exact_64bit(self):
        m = fixture()
        leaf = m.leaf('Pump1.Pressure')
        leaf.update(type='ULINT', size=8)
        value = 18446744073709551615
        self.assertEqual(m.decode('Pump1.Pressure', m.encode('Pump1.Pressure', value)), value)
        with self.assertRaises(ValueError):
            m.encode('Pump1.Pressure', value + 1)
        with self.assertRaises(ValueError):
            m.encode('Pump1.Pressure', 1.5)

    def test_transform_and_hit(self):
        m = fixture(); screen = m.doc['screens'][0]
        self.assertEqual(geometry(screen, 1600, 1000), (2, 0, 20))
        e = action_element(m, 'toggle')
        # Put on the top layer for deterministic hit testing.
        screen['elements'].remove(e); screen['elements'].append(e)
        self.assertIs(hit(m, screen, {}, e['x']+1, e['y']+1), e)
        e['bindings']['visible'] = 'Pump1.Running'
        self.assertIsNone(hit(m, screen, {'pump1.running': False}, e['x']+1, e['y']+1))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.model = fixture(); self.backend = Demo(self.model)
        self.engine = Engine(self.model, self.backend); self.engine.tick()

    def test_set_toggle_and_numeric_write(self):
        e = action_element(self.model, 'set')
        self.engine.request(dict(op='action', id=e['id']), 1)
        self.assertTrue(self.backend.values['pump1.startrequest'])
        e['action']['kind'] = 'toggle'
        self.engine.request(dict(op='action', id=e['id']), 1)
        self.assertFalse(self.backend.values['pump1.startrequest'])
        numeric = next(e for e in self.model.elements.values() if e['action']['kind'] == 'write')
        self.engine.request(dict(op='action', id=numeric['id'], value=23.5), 1)
        self.engine.tick()
        self.assertEqual(self.engine.values['pump1.pressure'], 23.5)
        with self.assertRaises(ValueError):
            self.engine.request(dict(op='action', id=numeric['id'], value=numeric['maximum']+1), 1)

    def test_momentary_release_and_ownership(self):
        e = action_element(self.model, 'momentary')
        self.engine.request(dict(op='action', id=e['id'], pressed=True), 1)
        self.assertTrue(self.backend.values['pump1.startrequest'])
        with self.assertRaisesRegex(ValueError, 'another client'):
            self.engine.request(dict(op='action', id=e['id'], pressed=True), 2)
        self.engine.release(1)
        self.assertFalse(self.backend.values['pump1.startrequest'])
        self.assertFalse(self.engine.leases)

    def test_momentary_releases_when_disabled(self):
        e = action_element(self.model, 'momentary')
        self.engine.request(dict(op='action', id=e['id'], pressed=True), 1)
        e['bindings']['enabled'] = 'Pump1.Running'
        snapshot = dict(self.engine.values, **{'pump1.running': False})
        with patch.object(self.backend, 'poll', return_value=snapshot):
            self.engine.tick()
        self.assertFalse(self.backend.values['pump1.startrequest'])
        self.assertFalse(self.engine.leases)

    def test_momentary_lease_timeout(self):
        e = action_element(self.model, 'momentary')
        self.engine.request(dict(op='action', id=e['id'], pressed=True), 1)
        self.engine.leases['pump1.startrequest'] = (1, 0)
        self.engine.tick()
        self.assertFalse(self.backend.values['pump1.startrequest'])

    def test_release_retry_after_backend_recovers(self):
        e = action_element(self.model, 'momentary')
        self.engine.request(dict(op='action', id=e['id'], pressed=True), 1)
        with patch.object(self.backend, 'poll', side_effect=OSError('Disconnected')):
            self.engine.release(1)
            self.assertIn('pump1.startrequest', self.engine.leases)
            self.assertFalse(self.engine.online())
        self.engine.tick()
        self.assertFalse(self.backend.values['pump1.startrequest'])
        self.assertFalse(self.engine.leases)

    def test_offline_and_stale_block_actions(self):
        e = action_element(self.model, 'set')
        self.engine.updated -= 10
        with self.assertRaises(ValueError):
            self.engine.request(dict(op='action', id=e['id']), 1)
        self.assertEqual(self.engine.request(dict(op='poll'), 1)['values'], {})

    def test_disabled_binding_rechecked_server_side(self):
        e = action_element(self.model, 'set')
        e['bindings']['enabled'] = 'Pump1.Running'
        with self.assertRaises(ValueError):
            self.engine.request(dict(op='action', id=e['id']), 1)


class BackendTests(unittest.TestCase):
    def test_read_and_write_protocol(self):
        m = fixture(); runtime = Runtime(m, '/unused')
        def request(command):
            payload = bytes.fromhex(command[6:])
            if len(payload) > 1:
                self.assertIn(' ', command, 'Runtime decoder requires space-separated hex bytes')
            if payload[0] == 0x52:
                response = b'\x52\x7e' + m.md5.encode() + b'\xad\xde'
            elif payload[0] == 0x50:
                self.assertEqual(payload[1:33], m.md5.encode())
                body = b''.join(m.encode(p, True if m.leaf(p)['type'] == 'BOOL' else 12.5) for p in m.paths)
                response = b'\x50\x7e' + struct.pack('>HIH', len(m.paths)-1, 5, len(body)) + body
            else:
                self.assertEqual(payload[0], 0x51)
                self.assertEqual(payload[38:], struct.pack('<f', 42.0))
                response = b'\x51\x7e'
            return 'DEBUG:' + response.hex()
        with patch.object(runtime, 'request', side_effect=request):
            values = runtime.poll()
            self.assertEqual(values['pump1.pressure'], 12.5)
            runtime.write('Pump1.Setpoint', 42.0)

    def test_md5_mismatch(self):
        runtime = Runtime(fixture(), '/unused')
        with patch.object(runtime, 'request', return_value='DEBUG:' + (b'\x52\x7e' + b'f'*32 + b'\xad\xde').hex()):
            with self.assertRaisesRegex(ConnectionError, 'MD5 mismatch'):
                runtime.poll()

    def test_old_runtime_rejected(self):
        runtime = Runtime(fixture(), '/unused')
        with patch.object(runtime, 'request', return_value='DEBUG:ERROR_PROCESSING'):
            with self.assertRaisesRegex(ConnectionError, 'core patch'):
                runtime.poll()

    def test_bad_snapshot_rejected(self):
        runtime = Runtime(fixture(), '/unused')
        with patch.object(runtime, 'handshake'), patch.object(runtime, 'pdu', return_value=b'\x50\x7e' + b'\0'*8):
            with self.assertRaisesRegex(ConnectionError, 'Incomplete'):
                runtime.poll()


class SocketTests(unittest.TestCase):
    def test_native_unix_socket_available(self):
        try:
            sock = socket.socket(socket.AF_UNIX)
            sock.close()
        except PermissionError:
            self.skipTest('AF_UNIX disabled by test host; broker stream integration runs over loopback TCP')

    def test_broker_stream_disconnect_releases_momentary(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp = Path(temporary)
            m = fixture(); e = action_element(m, 'momentary')
            doc = tmp/'targetvisu.json'; doc.write_text(json.dumps(m.doc))
            sock = tmp/'control.sock'
            # This host denies AF_UNIX. Substitute only the listener transport;
            # the production handler, JSON framing, Engine and Client run unchanged.
            shim = """
import sys, socketserver, pathlib
from targetvisu import service
from targetvisu.__main__ import main
class TestListener(socketserver.ThreadingTCPServer):
    def __init__(self, path, handler):
        super().__init__(('127.0.0.1', 0), handler)
        pathlib.Path(path).write_text(str(self.server_address[1]))
service.socketserver.ThreadingUnixStreamServer = TestListener
main()
"""
            proc = subprocess.Popen([sys.executable, '-c', shim, 'serve', '--demo',
                                     '--document', str(doc), '--debug-map', str(ROOT/'example.debug-map.json'),
                                     '--broker-socket', str(sock)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic()+5
                while not sock.exists() and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(sock.exists(), proc.poll())
                def connect():
                    client = Client.__new__(Client)
                    client.sock = socket.create_connection(('127.0.0.1', int(sock.read_text())), timeout=2)
                    client.stream = client.sock.makefile('rwb')
                    return client
                c1, c2 = connect(), connect()
                try:
                    self.assertTrue(c1.request(dict(op='poll'))['online'])
                    c1.request(dict(op='action', id=e['id'], pressed=True))
                    c1.close()
                    deadline = time.monotonic()+3
                    while time.monotonic() < deadline:
                        reply = c2.request(dict(op='poll'))
                        if not reply['values']['pump1.startrequest']:
                            break
                        time.sleep(.05)
                    self.assertFalse(reply['values']['pump1.startrequest'])
                    # Unix socket owner-only mode is checked separately on target.
                finally:
                    c2.close()
            finally:
                proc.terminate()
                stdout, stderr = proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 0, stderr.decode())


if __name__ == '__main__':
    unittest.main()


def trend_fixture():
    doc = copy.deepcopy(fixture().doc)
    element = next(e for e in doc['screens'][0]['elements'] if e['kind'] == 'number')
    element['kind'] = 'trend'
    element.pop('numberMode', None)
    element['action'] = dict(kind='none', target='', value=True)
    element['bindings']['value'] = ''
    element['trend'] = dict(sampleMs=1000, durationSec=300, autoScale=True,
                            series=[dict(path='Pump1.Pressure', label='Pressure', color='#16a34a')])
    return doc, element


class TrendTests(unittest.TestCase):
    def test_trend_resolves_compiled_numeric_symbols(self):
        doc, element = trend_fixture()
        m = Model(doc, load_json(ROOT / 'example.debug-map.json'))
        self.assertIn('pump1.pressure', m.paths)
        element['trend']['series'][0]['path'] = 'Pump1.Running'
        with self.assertRaisesRegex(ValueError, 'numeric PLC'):
            Model(doc, load_json(ROOT / 'example.debug-map.json'))
        element['trend']['series'][0]['path'] = 'Pump1.Pressure'
        element['trend']['sampleMs'] = 250
        with self.assertRaisesRegex(ValueError, '600 samples'):
            Model(doc, load_json(ROOT / 'example.debug-map.json'))

    def test_bounded_retention_and_screen_access(self):
        from targetvisu.trends import TrendStore
        doc, element = trend_fixture()
        store = TrendStore(doc)
        start = 1700000000
        for index in range(700):
            store.capture(float(index), start + index,
                          {'pump1.pressure': index})
        history = store.for_screen(doc['screens'][0]['id'], start + 700)
        samples = history[element['id']]
        self.assertTrue(0 < len(samples) <= 301)
        self.assertEqual(samples[-1][1], 699)
        self.assertGreaterEqual(samples[0][0], start + 400)
        with self.assertRaisesRegex(ValueError, 'Unknown Trend screen'):
            store.for_screen('unknown', start + 700)

    def test_broker_exposes_history_without_accepting_arbitrary_screen(self):
        doc, element = trend_fixture()
        model = Model(doc, load_json(ROOT / 'example.debug-map.json'))
        engine = Engine(model, Demo(model))
        engine.tick()
        result = engine.request(dict(op='trends', screen=doc['screens'][0]['id']), 1)
        self.assertTrue(result['online'])
        self.assertEqual(len(result['history'][element['id']]), 1)
        with self.assertRaisesRegex(ValueError, 'Unknown Trend screen'):
            engine.request(dict(op='trends', screen='not-a-screen'), 1)

    def test_auto_scale_and_gap_segments(self):
        from targetvisu.trend_render import y_bounds, series_segments
        doc, element = trend_fixture()
        low, high = y_bounds(element, [[100, 40], [101, 40]])
        self.assertLess(low, 40)
        self.assertGreater(high, 40)
        segments = series_segments([[100, 1], [101, 2], [105, 3]],
                                   0, 110, 60, 1000)
        self.assertEqual([len(s) for s in segments], [2, 1])
