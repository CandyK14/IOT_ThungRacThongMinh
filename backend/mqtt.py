import json
import logging
import threading
import time
from collections import defaultdict, deque

import paho.mqtt.client as mqtt

from .schema import parse_message


class Ingestor:
    def __init__(self,db,settings):
        self.db=db;self.settings=settings;self.rates=defaultdict(deque)
        self.accepted=0;self.rejected=0;self.connected=False
        self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='smartbin-backend')
        self.client.username_pw_set(settings.mqtt_user,settings.mqtt_password)
        if not settings.mqtt_dev:self.client.tls_set(ca_certs=settings.mqtt_ca)
        self.client.reconnect_delay_set(min_delay=1,max_delay=60)
        self.client.max_queued_messages_set(256)
        self.client.on_connect=self.on_connect;self.client.on_message=self.on_message
        self.client.on_disconnect=lambda *args:setattr(self,'connected',False)

    def on_connect(self,client,userdata,flags,reason,properties):
        self.connected=reason==0
        if self.connected:client.subscribe([('v1/bins/+/telemetry',1),('v1/bins/+/events',1)])

    def handle(self,topic,payload):
        parts=topic.split('/')
        if len(parts)!=4 or parts[:2]!=['v1','bins'] or parts[3] not in ('telemetry','events'):raise ValueError('Topic sai')
        m=parse_message(payload,self.settings.max_payload)
        if m.bin_id!=parts[2] or (parts[3]=='events')!=(m.kind=='event'):raise ValueError('Topic không khớp payload')
        # Bound key cardinality by checking registered devices before allocating a limiter.
        with self.db.connect() as c:
            if not c.execute('SELECT 1 FROM bins WHERE id=?',(m.bin_id,)).fetchone():raise ValueError('Chưa đăng ký')
        q=self.rates[m.bin_id];now=time.monotonic()
        while q and q[0]<now-60:q.popleft()
        if len(q)>=120:raise ValueError('Giới hạn 120 bản tin/phút/thùng')
        q.append(now)
        return self.db.ingest(m)

    def on_message(self,client,userdata,message):
        try:
            ack=self.handle(message.topic,message.payload)
            # ingest() commits before it returns. PUBACK is not this ACK.
            client.publish(f'v1/bins/{ack["bin_id"]}/ack',json.dumps(ack,separators=(',',':')),qos=1,retain=False)
            self.accepted+=1
        except Exception:
            self.rejected+=1
            logging.getLogger(__name__).warning('Từ chối bản tin MQTT; không ghi payload/credential vào log')

    def start(self):
        self.client.connect_async(self.settings.mqtt_host,self.settings.mqtt_port,60)
        self.client.loop_start()

    def stop(self):
        self.client.disconnect();self.client.loop_stop()
