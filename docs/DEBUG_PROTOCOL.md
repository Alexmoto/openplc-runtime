# Debug Protocol

## Overview

OpenPLC Runtime v4 provides a WebSocket-based debug interface for real-time variable inspection and modification. This allows debuggers (like OpenPLC Editor) to monitor and control PLC execution without the overhead of repeated HTTPS connections.

For detailed WebSocket connection and authentication information, see [webserver/DEBUG_WEBSOCKET.md](../webserver/DEBUG_WEBSOCKET.md).

## Connection Details

**Endpoint:** `wss://<host>:8443/api/debug`

**Authentication:** JWT token (via query parameter or auth dict)

**Protocol:** Socket.IO over WebSocket

## Debug Command Format

Debug commands are sent as hex strings representing binary protocol messages. The format follows the Modbus-style function code pattern.

### Command Structure

```
[Function Code] [Data Bytes...]
```

All commands and responses are represented as space-separated hex bytes (e.g., `"41 DE AD 00 00"`).

## Function Codes

### 0x41 - DEBUG_INFO

Get debug information about the PLC program.

**Request:**
```
41 DE AD 00 00
```

**Response:**
```
7E [info bytes...]
```

**Purpose:** Retrieve metadata about the loaded PLC program, including variable count and program hash.

---

### 0x42 - DEBUG_SET

Set trace flags for variables.

**Request:**
```
42 [variable index] [trace flag] [additional data...]
```

**Purpose:** Enable or disable tracing for specific variables. When tracing is enabled, variable values are logged or transmitted for monitoring.

**Trace Flags:**
- `0x00` - Disable tracing
- `0x01` - Enable tracing

---

### 0x43 - DEBUG_GET

Get trace data for variables.

**Request:**
```
43 [variable index] [count] [additional data...]
```

**Response:**
```
7E [trace data bytes...]
```

**Purpose:** Retrieve current values and trace information for specified variables.

---

### 0x44 - DEBUG_GET_LIST

Get values for a list of variables.

**Request:**
```
44 [count high] [count low] [index1 high] [index1 low] [index2 high] [index2 low] ...
```

**Example:**
```
44 00 03 00 00 00 01 00 02
```
(Get 3 variables: indexes 0, 1, 2)

**Response:**
```
7E [variable data...]
```

**Response Format:**
Each variable in the response includes:
- Variable index (2 bytes)
- Variable value (size depends on type)
- Variable type indicator

**Purpose:** Efficiently retrieve multiple variable values in a single request. This is the primary method used for polling variables during debug sessions.

---

### 0x45 - DEBUG_GET_MD5

Get MD5 hash of the loaded PLC program.

**Request:**
```
45 DE AD 00 00
```

**Response:**
```
7E [32 hex characters representing MD5 hash] 00
```

**Example Response:**
```
7E 61 62 63 64 65 66 31 32 33 34 35 36 37 38 39 30 31 32 33 34 35 36 37 38 39 30 31 32 33 34 35 36 00
```
(MD5: abcdef1234567890123456789012345678)

**Purpose:** Verify that the debugger is connected to the expected PLC program. The hash changes when a new program is loaded.

---

## Response Format

All successful responses start with `0x7E` (126 decimal, `~` character) as a success indicator.

Error responses may return different status codes or empty responses.

## Variable Types

Variables in the PLC program have different types based on IEC 61131-3 standard:

### Boolean Types
- `BOOL` - 1 bit (transmitted as 1 byte)

### Integer Types
- `SINT` - 8-bit signed integer
- `USINT` - 8-bit unsigned integer
- `INT` - 16-bit signed integer
- `UINT` - 16-bit unsigned integer
- `DINT` - 32-bit signed integer
- `UDINT` - 32-bit unsigned integer
- `LINT` - 64-bit signed integer
- `ULINT` - 64-bit unsigned integer

### Real Types
- `REAL` - 32-bit floating point
- `LREAL` - 64-bit floating point

### Time Types
- `TIME` - Duration
- `DATE` - Calendar date
- `TIME_OF_DAY` / `TOD` - Time of day
- `DATE_AND_TIME` / `DT` - Date and time

### String Types
- `STRING` - Variable-length string

### Bit String Types
- `BYTE` - 8 bits
- `WORD` - 16 bits
- `DWORD` - 32 bits
- `LWORD` - 64 bits

## Usage Examples

### Python Client

```python
import socketio

# Obtain JWT token first (see webserver/DEBUG_WEBSOCKET.md)
TOKEN = "your_jwt_token_here"

sio = socketio.Client(ssl_verify=False)

@sio.event(namespace='/api/debug')
def debug_response(data):
    if data.get('success'):
        print(f"Response: {data.get('data')}")
    else:
        print(f"Error: {data.get('error')}")

# Connect
sio.connect(
    'https://localhost:8443',
    auth={'token': TOKEN},
    namespaces=['/api/debug'],
    transports=['websocket']
)

# Get MD5 hash
sio.emit('debug_command', {
    'command': '45 DE AD 00 00'
}, namespace='/api/debug')

# Get variable list (variables 0, 1, 2)
sio.emit('debug_command', {
    'command': '44 00 03 00 00 00 01 00 02'
}, namespace='/api/debug')

sio.sleep(2)
sio.disconnect()
```

### JavaScript Client

```javascript
import io from 'socket.io-client';

// Obtain JWT token first
const token = 'your_jwt_token_here';

const socket = io('wss://localhost:8443/api/debug', {
  transports: ['websocket'],
  query: { token: token },
  rejectUnauthorized: false
});

socket.on('connected', (data) => {
  console.log('Connected:', data);

  // Get MD5 hash
  socket.emit('debug_command', {
    command: '45 DE AD 00 00'
  });
});

socket.on('debug_response', (response) => {
  if (response.success) {
    console.log('Data:', response.data);
  } else {
    console.error('Error:', response.error);
  }
});
```

## Polling Strategy

For continuous monitoring of variables:

1. **Connect** to WebSocket with JWT authentication
2. **Get MD5** to verify program identity
3. **Poll variables** using DEBUG_GET_LIST at regular intervals (e.g., every 100ms)
4. **Parse responses** to extract variable values
5. **Disconnect** when debug session ends

**Benefits over REST API:**
- Single TLS handshake for entire session
- Lower latency (no HTTP overhead)
- Bidirectional communication
- Persistent connection

## Implementation Details

### Runtime Side

The debug protocol is implemented in the PLC runtime core:

**Handler:** `core/src/plc_app/debug_handler.c`

**Key Functions:**
- `process_debug_data()` - Main dispatcher for function codes
- `debugInfo()` - Handles DEBUG_INFO (0x41)
- `debugSetTrace()` - Handles DEBUG_SET (0x42)
- `debugGetTrace()` - Handles DEBUG_GET (0x43)
- `debugGetList()` - Handles DEBUG_GET_LIST (0x44)
- `debugGetMD5()` - Handles DEBUG_GET_MD5 (0x45)

### Web Server Side

The WebSocket interface is implemented in the web server:

**Handler:** `webserver/debug_websocket.py`

**Key Functions:**
- `init_debug_websocket()` - Initialize Socket.IO server
- `handle_connect()` - Authenticate connections
- `handle_debug_command()` - Forward commands to runtime via Unix socket

### Communication Flow

```
[Debugger] --WebSocket--> [Web Server] --Unix Socket--> [PLC Runtime]
                                                              |
                                                         [Debug Handler]
                                                              |
                                                         [Variable Access]
```

## Security

### Authentication
- JWT token required for WebSocket connection
- Token obtained via REST API login endpoint
- Token validated on connection and can be revoked

### Authorization
- Debug access requires authenticated user
- Commands validated before execution
- Buffer overflow protection in command parsing

### Data Protection
- All communication encrypted via WSS (WebSocket Secure)
- Variable data transmitted in binary format
- No sensitive information in error messages

## Performance Considerations

### Latency
- WebSocket: ~1-5ms per command (local network)
- REST API: ~10-50ms per request (includes TLS handshake)

### Throughput
- Can handle hundreds of variable reads per second
- Limited by scan cycle time (typically 50ms)
- Batch requests with DEBUG_GET_LIST for efficiency

### Resource Usage
- One WebSocket connection per debug session
- Minimal CPU overhead (<1% for typical polling rates)
- Memory usage proportional to number of traced variables

## Troubleshooting

### Connection Refused

**Cause:** Invalid JWT token or authentication failure

**Solution:**
1. Obtain fresh JWT token via `/api/login`
2. Verify token is passed correctly (query param or auth dict)
3. Check token expiration

### No Response

**Cause:** Runtime not responding or command malformed

**Solution:**
1. Check PLC runtime status via `/api/status`
2. Verify command format (hex string with spaces)
3. Check runtime logs for errors

### Invalid Data

**Cause:** Variable index out of range or type mismatch

**Solution:**
1. Verify variable indexes with DEBUG_INFO
2. Check variable types in PLC program
3. Ensure program is loaded and running

### Disconnection

**Cause:** Network issue, timeout, or runtime restart

**Solution:**
1. Implement reconnection logic in client
2. Re-authenticate after reconnection
3. Verify program MD5 after reconnection

## Related Documentation

- [Editor Integration](EDITOR_INTEGRATION.md) - How OpenPLC Editor connects to runtime
- [webserver/DEBUG_WEBSOCKET.md](../webserver/DEBUG_WEBSOCKET.md) - WebSocket connection details
- [API Reference](API.md) - REST API endpoints
- [Architecture](ARCHITECTURE.md) - System overview
- [Security](SECURITY.md) - Authentication and authorization
