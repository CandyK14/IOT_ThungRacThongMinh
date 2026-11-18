"""Gửi JSONL qua broker bằng một credential đúng bin_id. Không dùng credential backend."""
import argparse
import json
import os
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from backend.config import Settings
from backend.schema import Message


def publish_records(records,cfg,bin_id,timeout=20,pace=1):
    cfg.validate()
    if cfg.mqtt_user!=bin_id:raise ValueError('MQTT_USER phải khớp bin_id, không dùng quyền backend')
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=f'simulator-{bin_id}')
    client.username_pw_set(cfg.mqtt_user,cfg.mqtt_password)
    if not cfg.mqtt_dev:client.tls_set(ca_certs=cfg.mqtt_ca)
    acked=set();condition=threading.Condition();connected=threading.Event()
    def connect(c,u,f,reason,p):
        if reason==0:c.subscribe(f'v1/bins/{bin_id}/ack',1)
    def subscribed(*args):connected.set()
    def message(c,u,msg):
        try:
            a=json.loads(msg.payload)
            if a.get('stored') is True and a.get('bin_id')==bin_id:
                with condition:acked.add((a['boot_id'],a['seq']));condition.notify_all()
        except (ValueError,KeyError):pass
    client.on_connect=connect;client.on_subscribe=subscribed;client.on_message=message
    client.connect(cfg.mqtt_host,cfg.mqtt_port,60);client.loop_start();sent=0
    try:
        if not connected.wait(timeout):raise TimeoutError('Không đăng nhập/subscribe được broker')
        for envelope in records:
            raw=envelope['message'];m=Message.model_validate(raw)
            if m.bin_id!=bin_id or m.source!='simulated':continue
            payload=json.dumps(raw,separators=(',',':'));key=(m.boot_id,m.seq);stored=False
            if len(payload.encode())>2048:raise ValueError('Payload quá lớn')
            for attempt in range(5):
                client.publish(f'v1/bins/{bin_id}/{"events" if m.kind=="event" else "telemetry"}',payload,qos=1)
                with condition:
                    if condition.wait_for(lambda:key in acked,timeout=min(timeout,2**attempt)):
                        acked.discard(key);stored=True;break
            if not stored:raise TimeoutError('Chưa có ACK ứng dụng; chạy lại file giữ nguyên ID')
            sent+=1
            if pace:time.sleep(pace)
        return sent
    finally:client.disconnect();client.loop_stop()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('file',type=Path);p.add_argument('--bin-id',default='sim-001');p.add_argument('--pace',type=float,default=1)
    a=p.parse_args()
    if a.pace<.5:p.error('pace >=0.5s để giới hạn gửi bù')
    cfg=Settings();cfg.mqtt_enabled=True
    with a.file.open(encoding='utf-8') as f:print(publish_records((json.loads(line) for line in f),cfg,a.bin_id,pace=a.pace))
