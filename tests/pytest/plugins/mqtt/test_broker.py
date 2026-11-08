# SPDX-License-Identifier: GPL-3.0-only
"""Optional real MQTT integration: pip install amqtt==0.11.3 paho-mqtt==2.1.0."""
import asyncio
import socket
import struct
import threading
import time

import pytest
mqtt = pytest.importorskip('paho.mqtt.client')
Broker = pytest.importorskip('amqtt.broker').Broker
from test_mqtt import binding, config
from mqtt_engine import MqttEngine


def wait_for(predicate, timeout=10):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate(): return
        time.sleep(.05)
    assert predicate(), 'MQTT integration timed out'


def test_real_broker_receive_publish_reconnect_and_cleanup():
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port=sock.getsockname()[1]; sock.close()
    loop=asyncio.new_event_loop()
    thread=threading.Thread(target=loop.run_forever,daemon=True); thread.start()
    async def start_broker():
        broker=Broker({'listeners': {'default': {'type':'tcp','bind':f'127.0.0.1:{port}'}}, 'plugins': {'amqtt.plugins.authentication.AnonymousAuthPlugin': {'allow_anonymous':True}}})
        await broker.start()
        return broker
    broker=asyncio.run_coroutine_threadsafe(start_broker(),loop).result(10)
    writes=[]; received=[]
    cfg=config([binding(),binding(id='publish',direction='publish',topic='plc/out',retain=True)])
    cfg.update(host='127.0.0.1',port=port)
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.reconnect_delay_set(1,2)
    engine=MqttEngine(cfg,client,lambda b: struct.pack('=f',42.5),lambda b,raw: writes.append(raw) or True,lambda *a: None)
    peer=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    peer.on_connect=lambda c,u,f,r,p: c.subscribe('plc/out',qos=1)
    peer.on_message=lambda c,u,m: received.append(m.payload)
    try:
        engine.start(); peer.connect('127.0.0.1',port); peer.loop_start()
        wait_for(lambda: engine.connected.is_set() and received)
        assert b'42.5' in received
        peer.publish('sensor/temp','21.25',qos=1).wait_for_publish(5)
        wait_for(lambda: writes)
        assert writes[-1]==struct.pack('=f',21.25)
        count=len(writes)
        peer.publish('sensor/temp','bad',qos=1).wait_for_publish(5)
        time.sleep(.2)
        assert len(writes)==count
        asyncio.run_coroutine_threadsafe(broker.shutdown(),loop).result(10)
        wait_for(lambda: not engine.connected.is_set())
        assert writes[-1]==struct.pack('=f',21.25)
        broker=asyncio.run_coroutine_threadsafe(start_broker(),loop).result(10)
        wait_for(lambda: engine.connected.is_set() and peer.is_connected())
        peer.publish('sensor/temp','99.5',qos=1).wait_for_publish(5)
        wait_for(lambda: writes[-1]==struct.pack('=f',99.5))
    finally:
        engine.stop(); peer.disconnect(); peer.loop_stop()
        asyncio.run_coroutine_threadsafe(broker.shutdown(),loop).result(10)
        loop.call_soon_threadsafe(loop.stop);thread.join(5);loop.close()
    assert engine.worker is None and not engine.pending
