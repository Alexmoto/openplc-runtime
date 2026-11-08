import math
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded latest-value MQTT exchange, independent from PLC scan timing."""
import threading
import time
try:
    from .mqtt_model import decode_message, encode_message
except ImportError:
    from mqtt_model import decode_message, encode_message


class MqttEngine:
    def __init__(self, config, client, read, write, log):
        self.config, self.client = config, client
        self.read, self.write, self.log = read, write, log
        self.lock = threading.Lock()
        self.pending = {}
        self.connected = threading.Event()
        self.stop_event = threading.Event()
        self.worker = None
        self.last_warning = {}
        self.subscriptions = {}
        # Successful publications only: rejected/failed sends must be retried.
        # Reset on reconnect so an on-change publisher sends its current value.
        self.last_published = {}
        self.last_published_at = {}
        self.connection_generation = 0
        for binding in config['bindings']:
            if binding['direction'] == 'subscribe':
                self.subscriptions.setdefault(binding['topic'], []).append(binding)
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message
        client.on_subscribe = self.on_subscribe
        client.on_connect_fail = self.on_connect_fail

    def warn(self, key, message):
        now = time.monotonic()
        if now - self.last_warning.get(key, -100) >= 10:
            self.last_warning[key] = now
            self.log('warn', message)

    def on_connect(self, client, userdata, flags, reason, properties):
        if reason != 0:
            self.log('warn', 'MQTT: broker rejected connection')
            return
        with self.lock:
            self.connection_generation += 1
            self.last_published.clear()
            self.last_published_at.clear()
            self.connected.set()
        if self.subscriptions:
            topics = [(topic, max(b['qos'] for b in bindings)) for topic, bindings in self.subscriptions.items()]
            result, _ = client.subscribe(topics)
            if result != 0:
                self.log('warn', 'MQTT: subscription request failed')
        self.log('info', 'MQTT: connected')

    def on_connect_fail(self, client, userdata):
        self.warn('connect', 'MQTT: broker unavailable; reconnecting')

    def on_subscribe(self, client, userdata, mid, reasons, properties):
        if any(getattr(reason, 'is_failure', False) for reason in reasons):
            self.log('warn', 'MQTT: broker denied one or more subscriptions')

    def on_disconnect(self, client, userdata, flags, reason, properties):
        with self.lock:
            self.connected.clear()
            self.connection_generation += 1
            self.last_published.clear()
            self.last_published_at.clear()
        self.log('info', 'MQTT: disconnected; keeping last PLC values')

    def on_message(self, client, userdata, message):
        if self.stop_event.is_set():
            return
        for b in self.subscriptions.get(message.topic, []):
            try:
                raw = decode_message(message.payload, b)
            except (ValueError, KeyError, IndexError, TypeError, RecursionError, OverflowError):
                self.warn(b['id'], f"MQTT: rejected invalid payload for binding {b['id']}")
                continue
            with self.lock:
                # At most one value per configured subscription, no unbounded message queue.
                self.pending[b['id']] = (b, raw)

    def tick(self, publish=True):
        with self.lock:
            pending, self.pending = self.pending, {}
        for key, (b, raw) in pending.items():
            if not self.write(b, raw):
                self.warn(key, f'MQTT: PLC write unavailable for binding {key}')
                with self.lock:
                    self.pending.setdefault(key, (b, raw))
        if not publish or not self.connected.is_set():
            return
        now = time.monotonic()
        for b in self.config['bindings']:
            if b['direction'] != 'publish':
                continue
            key = b['id']
            mode = b.get('publishMode', 'interval')
            with self.lock:
                if not self.connected.is_set():
                    return
                generation = self.connection_generation
                previous = self.last_published.get(key)
                last_at = self.last_published_at.get(key)
            # Preserve old projects: no per-binding interval means the
            # existing global intervalMs. In on-change mode, poll every 50 ms.
            interval = b.get('publishIntervalMs', self.config['intervalMs']) / 1000
            if mode == 'interval' and last_at is not None and now - last_at < interval and not math.isclose(now - last_at, interval, rel_tol=0, abs_tol=1e-9):
                continue
            try:
                raw = self.read(b)
                if raw is None:
                    self.warn(key, f'MQTT: PLC read unavailable for binding {key}')
                    continue
                payload = encode_message(raw, b)
                if mode == 'on-change' and previous == payload:
                    continue
                if not self.connected.is_set():
                    return
                result = self.client.publish(b['topic'], payload, qos=b['qos'], retain=b['retain'])
                if result.rc != 0:
                    self.warn(key, f'MQTT: publish unavailable for binding {key}')
                    continue
                # A successful Paho return means queued for sending, not
                # broker acknowledgment (especially at QoS 0).
                with self.lock:
                    if self.connected.is_set() and self.connection_generation == generation:
                        self.last_published[key] = payload
                        self.last_published_at[key] = now
            except (ValueError, TypeError, OverflowError):
                self.warn(key, f'MQTT: invalid PLC value for binding {key}')

    def start(self):
        if self.worker is not None:
            return
        self.stop_event.clear()
        self.client.connect_async(self.config['host'], self.config['port'], self.config['keepalive'])
        self.client.loop_start()
        def run():
            while not self.stop_event.wait(0.05):
                try:
                    self.tick()
                except Exception:
                    self.warn('worker', 'MQTT: exchange failed; retrying')
        self.worker = threading.Thread(target=run, name='mqtt-plc', daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        if self.worker is not None:
            self.worker.join()
            self.worker = None
        self.client.disconnect()
        self.client.loop_stop()
        with self.lock:
            self.connected.clear()
            self.connection_generation += 1
            self.last_published.clear()
            self.last_published_at.clear()
            self.pending.clear()
