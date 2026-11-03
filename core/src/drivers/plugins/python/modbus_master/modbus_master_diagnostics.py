# SPDX-License-Identifier: MIT
"""Opt-in, per-I/O-group Modbus diagnostics. No direct PLC memory writes.

The observer sees individual requests, never serial-port-open as device health.
The publisher ages state independently of blocking requests/reconnects.
"""
import json
import os
import threading
import time
from dataclasses import dataclass
from functools import wraps

from pymodbus.exceptions import ConnectionException, ModbusIOException
from pymodbus.pdu import ExceptionResponse

try:
    from .modbus_master_utils import get_read_count_for_io_point, parse_modbus_offset
except ImportError:
    from modbus_master_utils import get_read_count_for_io_point, parse_modbus_offset

UINT32_MAX = 0xFFFFFFFF
INITIAL, OK, NO_REPLY, PROTOCOL_ERROR, STALE, STOPPED, LOCAL_ERROR = range(7)
ERR_NONE, ERR_NO_REPLY, ERR_TRANSPORT, ERR_INVALID_RESPONSE, ERR_STALE, ERR_STOPPED, ERR_LOCAL = range(7)
# Names, required memory bank, SBA writer. UINT/UDINT counters saturate.
FIELDS = {
    "ok": ("X", "write_bool_memory", "BOOL"),
    "response_ok": ("X", "write_bool_memory", "BOOL"),
    "status": ("W", "write_int_memory", "UINT"),
    "last_error": ("W", "write_int_memory", "UINT"),
    "success_count": ("D", "write_dint_memory", "UDINT"),
    "error_count": ("D", "write_dint_memory", "UDINT"),
    "consecutive_errors": ("D", "write_dint_memory", "UDINT"),
    "age_ms": ("D", "write_dint_memory", "UDINT"),
    "publish_counter": ("D", "write_dint_memory", "UDINT"),
}
METHOD_FC = {"read_coils": 1, "read_discrete_inputs": 2, "read_holding_registers": 3,
             "read_input_registers": 4, "write_coil": 5, "write_register": 6,
             "write_coils": 15, "write_registers": 16}


def iec_name(address):
    return f"%{address.area}{address.size}{address.byte}" + (f".{address.bit}" if address.size == "X" else "")


def signature(point):
    return {"fc": point.fc, "offset": parse_modbus_offset(point.offset),
            "location": iec_name(point.iec_location), "length": point.length}


def _integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"diagnostics: {label} must be {minimum}..{maximum}")
    return value


@dataclass(frozen=True)
class Mapping:
    device: str
    point: object
    stale_ms: int
    locations: dict


@dataclass
class GroupState:
    started: float
    status: int = INITIAL
    last_error: int = ERR_NONE
    last_success: object = None
    last_response: object = None
    success_count: int = 0
    error_count: int = 0
    consecutive_errors: int = 0

    def success(self, now):
        self.status, self.last_error = OK, ERR_NONE
        self.last_success = self.last_response = now
        self.success_count = min(UINT32_MAX, self.success_count + 1)
        self.consecutive_errors = 0

    def failure(self, now, status, error, response=False):
        self.status, self.last_error = status, error
        if response:
            self.last_response = now
        else:
            self.last_response = None
        self.error_count = min(UINT32_MAX, self.error_count + 1)
        self.consecutive_errors = min(UINT32_MAX, self.consecutive_errors + 1)

    def snapshot(self, now, stale_ms, active, tick):
        age = UINT32_MAX if self.last_success is None else min(UINT32_MAX, max(0, int((now - self.last_success) * 1000)))
        # A fresh protocol exception confirms a responding device but not valid data.
        response_ok = self.last_response is not None and (now - self.last_response) * 1000 < stale_ms
        status, error = self.status, self.last_error
        since = self.last_response if self.last_response is not None else self.started
        expired = (now - since) * 1000 >= stale_ms
        if not active:
            status, error = STOPPED, ERR_STOPPED
        elif expired and status in (INITIAL, OK, PROTOCOL_ERROR):
            status, error = STALE, ERR_STALE
        return {"ok": active and status == OK and age < stale_ms,
                "response_ok": active and response_ok,
                "status": status, "last_error": error,
                "success_count": self.success_count, "error_count": self.error_count,
                "consecutive_errors": self.consecutive_errors, "age_ms": age,
                "publish_counter": tick}


def load_mappings(path, devices, buffer_size, data=None):
    """Absent sidecar disables diagnostics. Invalid present sidecar fails startup."""
    from shared.plugin_config_decode.modbus_master_config_model import parse_iec_address
    if data is None:
        try:
            with open(path, encoding="utf-8") as source:
                data = json.load(source)
        except FileNotFoundError:
            return None
    if not isinstance(data, dict) or set(data) - {"version", "publish_ms", "groups"}:
        raise ValueError("diagnostics: invalid root fields")
    if type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("diagnostics: version must be 1")
    interval = _integer(data.get("publish_ms", 100), 20, 10000, "publish_ms")
    groups = data.get("groups")
    if not isinstance(groups, list) or not 1 <= len(groups) <= 256:
        raise ValueError("diagnostics: groups must contain 1..256 mappings")
    names = {}
    for device in devices:
        if device.name in names:
            raise ValueError("diagnostics: device names must be unique")
        names[device.name] = device
    occupied = set()
    for device in devices:
        for point in device.io_points:
            address = point.iec_location
            for index in range(point.length):
                if address.size == "X":
                    bit = address.byte * 8 + address.bit + index
                    occupied.add((address.area, "X", bit // 8, bit % 8))
                else:
                    occupied.add((address.area, address.size, address.byte + index, None))
    selected, used, mappings = set(), set(), []
    for entry in groups:
        if not isinstance(entry, dict) or set(entry) != {"device", "group", "expected", "stale_ms", "locations"}:
            raise ValueError("diagnostics: invalid group fields")
        name = entry["device"]
        if not isinstance(name, str) or name not in names:
            raise ValueError("diagnostics: unknown device")
        points = names[name].io_points
        group = _integer(entry["group"], 0, len(points) - 1, "group index")
        if (name, group) in selected:
            raise ValueError("diagnostics: duplicate group mapping")
        selected.add((name, group))
        point = points[group]
        if entry["expected"] != signature(point):
            raise ValueError(f"diagnostics: stale mapping for {name} group {group}; regenerate sidecar")
        stale_ms = _integer(entry["stale_ms"], max(interval * 2, point.cycle_time_ms), UINT32_MAX - 1, "stale_ms")
        locations = entry["locations"]
        if not isinstance(locations, dict) or not locations or "ok" not in locations or set(locations) - set(FIELDS):
            raise ValueError("diagnostics: locations must include ok and use known field names")
        resolved = {}
        for field, text in locations.items():
            if not isinstance(text, str):
                raise ValueError("diagnostics: locations must be IEC address strings")
            address = parse_iec_address(text)
            if address.area != "M" or address.size != FIELDS[field][0]:
                raise ValueError(f"diagnostics: {field} requires %M{FIELDS[field][0]}")
            if not 0 <= address.byte < buffer_size:
                raise ValueError("diagnostics: address exceeds Runtime buffer size")
            key = (address.area, address.size, address.byte, address.bit)
            if key in occupied or key in used:
                raise ValueError(f"diagnostics: address collision at {text}")
            used.add(key)
            resolved[field] = address
        mappings.append(Mapping(name, point, stale_ms, resolved))
    return interval, mappings


class Diagnostics:
    def __init__(self, sba, logger, interval_ms, mappings, clock=time.monotonic):
        self.sba, self.logger, self.clock = sba, logger, clock
        self.interval = interval_ms / 1000.0
        self.mappings = mappings
        self.lock = threading.Lock()
        self.states = {(m.device, id(m.point)): GroupState(clock()) for m in mappings}
        self.active = True
        self.tick = 0
        self.event = threading.Event()
        self.thread = None
        self._write_fault_logged = False

    @classmethod
    def from_sidecar(cls, config_path, devices, sba, logger):
        # Editor 4.3.3 integration embeds diagnostics in the master config.
        # Runtime's plugin manager copies only that config into the plugin dir.
        # The version marker is authoritative even when every group is disabled,
        # preventing an old manually installed sidecar from reviving diagnostics.
        with open(config_path, encoding="utf-8") as source:
            master = json.load(source)
        embedded = any("diagnostics_version" in entry.get("config", {}) for entry in master)
        path = os.path.join(os.path.dirname(config_path), "modbus_master_diagnostics.json")
        if embedded:
            groups = []
            for entry in master:
                config = entry.get("config", {})
                if type(config.get("diagnostics_version")) is not int or config["diagnostics_version"] != 1:
                    raise ValueError("diagnostics: mixed or unsupported embedded version")
                for index, point in enumerate(config.get("io_points", [])):
                    settings = point.get("diagnostics")
                    if settings is None:
                        continue
                    if not isinstance(settings, dict) or set(settings) != {"stale_ms", "locations"}:
                        raise ValueError("diagnostics: invalid embedded settings")
                    model = next((device for device in devices if device.name == entry.get("name")), None)
                    if model is None or index >= len(model.io_points):
                        raise ValueError("diagnostics: embedded group has no runtime model")
                    groups.append({"device": entry["name"], "group": index,
                                   "expected": signature(model.io_points[index]),
                                   "stale_ms": settings["stale_ms"], "locations": settings["locations"]})
            if not groups:
                return None
            loaded = load_mappings(path, devices, sba.runtime_args.buffer_size,
                                   {"version": 1, "publish_ms": 100, "groups": groups})
        else:
            loaded = load_mappings(path, devices, sba.runtime_args.buffer_size)
        return None if loaded is None else cls(sba, logger, *loaded)

    def record(self, device, point, status, error=0, response=False):
        with self.lock:
            state = self.states.get((device, id(point)))
            if not self.active or state is None:
                return
            now = self.clock()
            if status == OK:
                state.success(now)
            else:
                state.failure(now, status, error, response)

    def for_request(self, device, point, client):
        if (device, id(point)) not in self.states:
            return client
        return ObservedClient(self, device, point, client)

    def snapshots(self):
        with self.lock:
            now = self.clock()
            return [(m, self.states[(m.device, id(m.point))].snapshot(now, m.stale_ms, self.active, self.tick))
                    for m in self.mappings]

    def publish(self):
        with self.lock:
            self.tick = (self.tick + 1) & UINT32_MAX
        failed = False
        for mapping, values in self.snapshots():
            # Status flags LAST: do not claim fresh status before auxiliary fields
            # have even been accepted. Writes use the existing bounded journal.
            fields = sorted((name for name in mapping.locations if name != "publish_counter"),
                            key=lambda name: name in ("ok", "response_ok"))
            group_failed = False
            for name in fields:
                address = mapping.locations[name]
                writer = getattr(self.sba, FIELDS[name][1])
                if address.size == "X":
                    accepted, _ = writer(address.byte, address.bit, values[name] and not group_failed)
                else:
                    accepted, _ = writer(address.byte, values[name])
                group_failed |= not accepted
            # A moving counter certifies that the whole group was enqueued,
            # not merely that this Python thread is still alive.
            if not group_failed and "publish_counter" in mapping.locations:
                address = mapping.locations["publish_counter"]
                accepted, _ = self.sba.write_dint_memory(address.byte, values["publish_counter"])
                group_failed |= not accepted
            failed |= group_failed
        if failed and not self._write_fault_logged:
            self.logger.error("[DIAGNOSTICS] Some diagnostic writes were rejected; check located variables and journal capacity")
        self._write_fault_logged = failed

    def _run(self):
        while not self.event.wait(self.interval):
            try:
                self.publish()
            except Exception as exc:
                self.logger.error(f"[DIAGNOSTICS] Publication failed: {exc}")

    def start(self):
        self.publish()  # UNKNOWN/BAD before device threads issue requests.
        self.thread = threading.Thread(target=self._run, name="ModbusDiagnostics", daemon=True)
        self.thread.start()

    def stop(self):
        with self.lock:
            self.active = False  # Late completions cannot revive stopped status.
        self.event.set()
        if self.thread is not None:
            self.thread.join()  # No network work in this thread.
        try:
            self.publish()
        except Exception as exc:
            self.logger.error(f"[DIAGNOSTICS] Could not publish STOP status: {exc}")


class ObservedClient:
    """Observe actual FC calls, preserving return values/exceptions for the plugin."""
    def __init__(self, diagnostics, device, point, client):
        self.diagnostics, self.device, self.point, self.client = diagnostics, device, point, client

    def __getattr__(self, name):
        method = getattr(self.client, name)
        if name not in METHOD_FC:
            return method

        @wraps(method)
        def call(*args, **kwargs):
            try:
                response = method(*args, **kwargs)
            except ModbusIOException:
                self.diagnostics.record(self.device, self.point, NO_REPLY, ERR_NO_REPLY)
                raise
            except (ConnectionException, OSError):
                self.diagnostics.record(self.device, self.point, NO_REPLY, ERR_TRANSPORT)
                raise
            except Exception:
                self.diagnostics.record(self.device, self.point, LOCAL_ERROR, ERR_LOCAL)
                raise
            if isinstance(response, ExceptionResponse):
                self.diagnostics.record(self.device, self.point, PROTOCOL_ERROR,
                                        0x100 + int(response.exception_code), response=True)
            elif response is None or isinstance(response, ModbusIOException):
                self.diagnostics.record(self.device, self.point, NO_REPLY, ERR_NO_REPLY)
            elif not callable(getattr(response, "isError", None)) or response.isError():
                self.diagnostics.record(self.device, self.point, LOCAL_ERROR, ERR_INVALID_RESPONSE)
            else:
                fc = METHOD_FC[name]
                valid = getattr(response, "function_code", fc) == fc
                if fc in (1, 2, 3, 4):
                    payload = getattr(response, "bits" if fc in (1, 2) else "registers", None)
                    valid = valid and payload is not None and len(payload) >= get_read_count_for_io_point(self.point)
                if valid:
                    self.diagnostics.record(self.device, self.point, OK)
                else:
                    self.diagnostics.record(self.device, self.point, LOCAL_ERROR, ERR_INVALID_RESPONSE)
            return response
        return call


def observed_client(diagnostics, device, point, client):
    return client if diagnostics is None else diagnostics.for_request(device, point, client)
