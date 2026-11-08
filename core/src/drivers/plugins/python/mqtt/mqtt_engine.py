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
        self.connected.clear()
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
        for b in self.config['bindings']:
            if b['direction'] != 'publish':
                continue
            try:
                raw = self.read(b)
                if raw is None:
                    continue
                payload = encode_message(raw, b)
                result = self.client.publish(b['topic'], payload, qos=b['qos'], retain=b['retain'])
                if result.rc != 0:
                    self.warn(b['id'], f"MQTT: publish unavailable for binding {b['id']}")
            except (ValueError, TypeError, OverflowError):
                self.warn(b['id'], f"MQTT: invalid PLC value for binding {b['id']}")

    def start(self):
        if self.worker is not None:
            return
        self.stop_event.clear()
        self.client.connect_async(self.config['host'], self.config['port'], self.config['keepalive'])
        self.client.loop_start()
        def run():
            due = 0.0
            while not self.stop_event.wait(0.05):
                now = time.monotonic()
                try:
                    self.tick(now >= due)
                except Exception:
                    self.warn('worker', 'MQTT: exchange failed; retrying')
                if now >= due:
                    due = now + self.config['intervalMs'] / 1000
        self.worker = threading.Thread(target=run, name='mqtt-plc', daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        if self.worker is not None:
            self.worker.join()
            self.worker = None
        self.client.disconnect()
        self.client.loop_stop()
        self.connected.clear()
        with self.lock:
            self.pending.clear()
