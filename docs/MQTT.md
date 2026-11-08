# MQTT data source (experimental v1)

Feature branch: `feature/mqtt-data-source`, based on `develop`. Requires the
matching Editor branch. This feature has not yet been validated on the Banana Pi;
keep production on `main` until a hardware test is accepted.

## Setup on an existing Runtime v4 checkout

After updating to the feature branch, from the Runtime root:

```sh
python3 tools/register_mqtt.py --check
python3 tools/register_mqtt.py
bash scripts/manage_plugin_venvs.sh create mqtt
```

The registration helper migrates any previous `mqtt/plugin.py` entry point
and stale plugin-directory `mqtt.json` path, while preserving the enabled flag
and other plugins' settings. The unique `mqtt_plugin.py` module name avoids a
Python import collision with OPC UA's `plugin.py`. The Python virtual
environment installs `paho-mqtt==2.1.0`.
No C/C++ changes or core rebuild are needed for the MQTT plugin itself. Uploading
an edited PLC project still triggers the normal project compilation.

Compile and upload a project from the matching Editor. Its `conf/mqtt.json`
enables the plugin through the existing plugin configuration loader. MQTT's
configuration stays in `core/generated/conf/mqtt.json` on the device rather
than being copied into the plugin source directory, so each new upload keeps
the configuration and compiled `debug-map.json` together. Start the
PLC project normally. MQTT starts/stops with its plugin lifecycle; the broker
need not be reachable when the PLC starts. Disabling MQTT in Editor and uploading
again omits the config and disables the plugin.

## Editor

Open **MQTT** in the project tree. Enable it, enter broker host/port (1883 for
plain TCP, usually 8883 with TLS), optional client ID and credentials. TLS verifies
both the certificate chain and hostname; an optional CA path refers to a file
on the Runtime machine. Empty CA path uses system trust. Each controller needs
its own non-empty client ID, or leave it empty for an automatic session ID.
Credentials are stored in project.json and the upload; do not publish projects
containing real broker passwords to public Git repositories.

Add one row per mapping:

| Direction | PLC variable | Topic | JSON pointer |
| --- | --- | --- | --- |
| Subscribe | MqttTemperature | plant/sensor1/temperature | empty for payload `21.5` |
| Subscribe | MqttPressure | plant/sensor1/values | `/pressure` for `{"pressure": 6.2}` |
| Publish | ValveState | plant/plc1/valve/state | empty |

Use plain global variables or scalar program-instance variables. Subscribe
requires a non-constant variable with **no located I/O address**. It does not
allocate `%MW`/`%IW` memory or override another fieldbus producer. Publish may
read a scalar located variable. Compile-time validation catches deleted names,
unsupported types and stale debug-map addresses. TargetVisu binds these same
PLC variables using its existing interface.

## Behaviour and limits

- MQTT 3.1.1, TCP/TLS, username/password, QoS 0/1/2 and retained publication.
- Exact, case-sensitive topics only (no `+`/`#`); maximum 256 bindings.
- BOOL and numeric IEC scalar types, including signed/unsigned 64-bit integers,
  REAL and LREAL. STRING, arrays, structures and binary payloads are not yet supported.
- Incoming values are JSON scalars (`true`, `false`, `0`, `1`, `21.5`) or fields
  selected by JSON Pointer (`/a/0/value`, `~1` for slash and `~0` for tilde).
  BOOL accepts only booleans or integer 0/1. Strings such as `"ON"` are rejected.
- Publications are JSON scalars. Each Publish binding has a mode:
  `interval` (periodic, 100..60000 ms per row) or `on-change` (publish only
  when the PLC scalar value changes). An on-change publisher sends its current
  value once on first connection and again after reconnecting; no periodic
  heartbeat is sent in this mode. PLC values are sampled every ~50 ms, so
  shorter changes can be missed. QoS and retain remain per row.
- Older projects without `publishMode` or `publishIntervalMs` keep their
  previous periodic behaviour with the global `intervalMs` (default 500 ms).
  Successful Paho `publish()` only confirms queueing for delivery; QoS 0
  does not guarantee broker receipt. A failed send or PLC read is retried.
- Writes are ordinary soft writes through the Runtime scan-boundary journal,
  never forces. Do not assign the subscribed variable in PLC code if it should
  keep the received value. A forced variable still respects the Runtime force.
- Latest-value semantics: bursts coalesce to one pending value per subscription;
  this is not a command/event queue. Invalid, overflowing or >64 KiB payloads
  are ignored. No automatic zeroing on disconnect or invalid data.
- Reconnection retries 1..30 seconds and restores subscriptions. Retained input
  messages are accepted, including an old retained value on reconnect. MQTT
  retain is separate from IEC RETAIN. There is no stale-data timeout or PLC
  quality/status variable yet; inspect Runtime logs for connection/parse errors.
- Outgoing QoS queues are bounded at 256. In-flight QoS messages may be replayed
  after reconnect according to Paho MQTT semantics. Do not use this initial
  implementation as an exactly-once command channel.

## Manual acceptance test

On a separate test project declare `MqttTemperature : REAL` (do not assign it
in ST), and an output variable that the PLC updates. Map input/output as above.
Publish with an MQTT test client, check the input in Debugger and TargetVisu,
and subscribe to the output topic. Test retained reception, a wrong-type value,
STOP/RUN, project re-upload, and a broker restart. Confirm the last input survives
the disconnect and that no other Modbus values change. Then test TLS and broker
credentials on the intended deployment before requesting a merge into main.

## Automated validation

```sh
python3 -m pip install pytest paho-mqtt==2.1.0 amqtt==0.11.3
python3 -m pytest tests/pytest/plugins/mqtt
```

`amqtt` is a test-only local broker, never a Runtime dependency. Tests cover
scalar/range conversion, JSON pointers, bounded coalescing, rejected messages,
real network subscription/publication, reconnect and worker cleanup. Tests use
mock PLC read/write callbacks; hardware and the complete PLC process still need
the manual check above.
