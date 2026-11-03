# SPDX-License-Identifier: GPL-3.0-only
"""Local Runtime socket adapter. Identity is checked inside every HMI PDU."""
import socket
import struct


class Runtime:
    def __init__(self, model, path):
        self.model, self.path, self.endian = model, path, '<'

    def request(self, command):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.7)
            sock.connect(self.path)
            sock.sendall(command.encode('ascii') + b'\n')
            data = bytearray()
            while not data.endswith(b'\n'):
                block = sock.recv(8192)
                if not block:
                    raise ConnectionError('Runtime disconnected')
                data.extend(block)
                if len(data) > 16384:
                    raise ValueError('Runtime reply exceeds limit')
            return data.decode('ascii').strip()

    def pdu(self, payload):
        result = self.request('DEBUG:' + payload.hex(' '))
        if not result.startswith('DEBUG:'):
            raise ConnectionError(result)
        try:
            raw = bytes.fromhex(result[6:])
        except ValueError as exc:
            raise ConnectionError('Runtime needs TargetVisu core patch and rebuild: ' + result) from exc
        if len(raw) < 2 or raw[0] != payload[0] or raw[1] != 0x7e:
            codes = {0x83: 'No program', 0x84: 'PLC is not RUNNING', 0x85: 'Program / debug-map MD5 mismatch',
                     0x86: 'Input variable is read-only', 0x81: 'Invalid compiled address / size', 0x82: 'Write queue full'}
            raise ConnectionError(codes.get(raw[1] if len(raw) > 1 else 0, 'Unsupported TargetVisu core protocol'))
        return raw

    def handshake(self):
        raw = self.pdu(b'\x52')
        if len(raw) != 36 or raw[2:34].decode('ascii').lower() != self.model.md5:
            raise ConnectionError('Program / debug-map MD5 mismatch')
        if raw[34:] == b'\xad\xde':
            self.endian = '<'
        elif raw[34:] == b'\xde\xad':
            raise ConnectionError('v0.1 supports little-endian Runtime targets only')
        else:
            raise ConnectionError('Unknown Runtime byte order')

    def poll(self):
        self.handshake()
        # Even an empty static screen checks the extension and RUN state.
        paths = self.model.paths
        values = {}
        batches, batch, size = [], [], 10
        for path in paths:
            n = self.model.leaf(path)['size']
            if size + n > 4000 or len(batch) >= 500:
                batches.append(batch); batch, size = [], 10
            batch.append(path); size += n
        if batch:
            batches.append(batch)
        if not batches:
            # Identity handshake plus STATUS for static documents, no write controls.
            if self.request('STATUS') != 'STATUS:RUNNING':
                raise ConnectionError('PLC is not RUNNING')
        for batch in batches:
            body = bytearray(b'\x50' + self.model.md5.encode('ascii') + struct.pack('>H', len(batch)))
            for path in batch:
                leaf = self.model.leaf(path)
                body.extend(struct.pack('>BH', leaf['arrayIdx'], leaf['elemIdx']))
            raw = self.pdu(body)
            expected = sum(self.model.leaf(p)['size'] for p in batch)
            if len(raw) != 10 + expected or int.from_bytes(raw[8:10], 'big') != expected or int.from_bytes(raw[2:4], 'big') != len(batch) - 1:
                raise ConnectionError('Incomplete Runtime snapshot')
            offset = 10
            for path in batch:
                n = self.model.leaf(path)['size']
                value = self.model.decode(path, raw[offset:offset + n], self.endian)
                # Reject NaN/Inf before JSON crosses the service boundary.
                import math
                if isinstance(value, float) and not math.isfinite(value):
                    raise ConnectionError('Non-finite PLC value: ' + path)
                values[path] = value
                offset += n
        return values

    def write(self, path, value):
        leaf = self.model.leaf(path)
        data = self.model.encode(path, value, self.endian)
        self.pdu(b'\x51' + self.model.md5.encode('ascii') + struct.pack('>BHH', leaf['arrayIdx'], leaf['elemIdx'], len(data)) + data)


class Demo:
    """Explicit simulation, never connects to Runtime."""
    def __init__(self, model):
        self.model = model
        self.values = {p: False if model.leaf(p)['type'] == 'BOOL' else 0.0 for p in model.paths}
        for p in self.values:
            if p.endswith('.setpoint') or p.endswith('.pressure'):
                self.values[p] = 15.0

    def poll(self):
        # The example program: Pressure := Setpoint; Running := StartRequest.
        for dest, source in (('pump1.pressure', 'pump1.setpoint'), ('pump1.running', 'pump1.startrequest')):
            if dest in self.values and source in self.values:
                self.values[dest] = self.values[source]
        return dict(self.values)

    def write(self, path, value):
        self.model.encode(path, value)
        self.values[path.lower()] = value
