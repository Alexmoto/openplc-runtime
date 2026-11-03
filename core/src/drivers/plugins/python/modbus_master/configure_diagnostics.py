#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create diagnostics sidecar and IEC variable declarations from compiled config."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.plugin_config_decode.modbus_master_config_model import ModbusMasterConfig, parse_iec_address
try:
    from .modbus_master_diagnostics import FIELDS, load_mappings, signature
except ImportError:
    from modbus_master_diagnostics import FIELDS, load_mappings, signature

LABELS = {"ok": "CommOK", "response_ok": "ResponseOK", "status": "Status", "last_error": "LastError",
          "success_count": "SuccessCount", "error_count": "ErrorCount", "consecutive_errors": "ConsecutiveErrors",
          "age_ms": "AgeMs", "publish_counter": "UpdateCounter"}


def make_entry(device, group, base, stale_ms=None):
    if type(base) is not int or base < 0:
        raise ValueError("base must be a non-negative integer")
    if type(group) is not int or not 0 <= group < len(device.io_points):
        raise ValueError("group index out of range")
    point = device.io_points[group]
    locations = {"ok": f"%MX{base}.0", "response_ok": f"%MX{base}.1",
                 "status": f"%MW{base}", "last_error": f"%MW{base + 1}",
                 "success_count": f"%MD{base}", "error_count": f"%MD{base + 1}",
                 "consecutive_errors": f"%MD{base + 2}", "age_ms": f"%MD{base + 3}",
                 "publish_counter": f"%MD{base + 4}"}
    threshold = max(3000, point.cycle_time_ms * 3, device.timeout_ms * 2) if stale_ms is None else stale_ms
    return {"device": device.name, "group": group, "expected": signature(point),
            "stale_ms": threshold, "locations": locations}


def declarations(data):
    lines = ["(* Diagnostic variables: add as located globals in OpenPLC Editor. *)", "VAR_GLOBAL"]
    for index, group in enumerate(data["groups"]):
        name = group["device"].replace("(*", "").replace("*)", "").replace("\n", " ").replace("\r", " ")
        lines.append(f"    (* MB{index}: {name}, io_points[{group['group']}] *)")
        for field, location in group["locations"].items():
            lines.append(f"    MB{index}_{LABELS[field]} AT {location} : {FIELDS[field][2]};")
    lines.append("END_VAR")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="compiled modbus_master.json used by Runtime")
    parser.add_argument("--list", action="store_true", help="list devices and zero-based io_points indices")
    parser.add_argument("--device")
    parser.add_argument("--group", type=int, default=0)
    parser.add_argument("--base", type=int, default=100)
    parser.add_argument("--stale-ms", type=int)
    parser.add_argument("--buffer-size", type=int, default=1024, help="must match Runtime buffer size")
    parser.add_argument("--append", action="store_true", help="append a different group to an existing sidecar")
    parser.add_argument("--output", type=Path, help="default: next to --config")
    args = parser.parse_args()
    try:
        config = ModbusMasterConfig()
        config.import_config_from_file(str(args.config))
        config.validate()
        if args.list:
            for device in config.devices:
                for index, point in enumerate(device.io_points):
                    print(f"{device.name}: group={index} slave={device.slave_id} {signature(point)} cycle={point.cycle_time_ms}ms")
            return
        found = [d for d in config.devices if d.name == args.device]
        if len(found) != 1:
            raise ValueError("Pass --device with one exact unique name (use --list first)")
        output = args.output or args.config.parent / "modbus_master_diagnostics.json"
        if output.resolve() == args.config.resolve():
            raise ValueError("diagnostics output must not replace the Modbus configuration")
        data = {"version": 1, "publish_ms": 100, "groups": []}
        if output.exists():
            if not args.append:
                raise ValueError("output already exists; use --append for another group or back up/remove it first")
            data = json.loads(output.read_text(encoding="utf-8"))
        data["groups"].append(make_entry(found[0], args.group, args.base, args.stale_ms))
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".modbus-diagnostics-", suffix=".json", dir=output.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(data, target, indent=2, ensure_ascii=False)
                target.write("\n")
            load_mappings(temporary, config.devices, args.buffer_size)
            st_path = output.with_suffix(".variables.st")
            if st_path.resolve() == args.config.resolve():
                raise ValueError("variable output conflicts with input")
            st_path.write_text(declarations(data), encoding="utf-8")
            os.replace(temporary, output)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        print(f"Created {output} and {st_path}")
        print("Declare these variables in the PLC and reserve their memory addresses before enabling diagnostics.")
        required = {"X": 0, "W": 0, "D": 0}
        for group in data["groups"]:
            for location in group["locations"].values():
                address = parse_iec_address(location)
                count = address.byte * 8 + address.bit + 1 if address.size == "X" else address.byte + 1
                required[address.size] = max(required[address.size], count)
        print("Required diagnostics memory extent (allocated automatically by the modified Editor):")
        print(f"MX >= {required['X']} bits; MW >= {required['W']} elements; MD >= {required['D']} elements.")
        print("In modified Editor 4.3.3 use Remote Device > IO Tag Mapping > Diagnostics; an extra Modbus server is not required.")
        print("Restart Runtime after deploying the new program/configuration.")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(1, f"Diagnostics configuration failed: {exc}\n")


if __name__ == "__main__":
    main()
