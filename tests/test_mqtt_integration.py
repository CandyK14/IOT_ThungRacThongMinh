"""Real loopback TLS sockets, authenticated broker, no external services or hardware."""
import asyncio
import json
import socket
import threading
import time

import paho.mqtt.client as mqtt
from amqtt.broker import Broker
from pwdlib import PasswordHash

from backend.config import Settings
from backend.db import Database
from backend.ml import Predictor,update_predictions
from backend.mqtt import Ingestor
from backend.routing import RouteRequest,solve
from backend.telegram import TelegramWorker
from simulator.publish import publish_records
from tools.create_local_certs import create


class TestBroker:
    __test__=False
    def __init__(self,directory):
        self.loop=asyncio.new_event_loop();self.ready=threading.Event();self.error=None
        with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
        certs=create(directory/'certs')
        self.ca=str(certs/'ca.crt')
        password_file=directory/'passwords'
        hasher=PasswordHash.recommended()
        password_file.write_text('\n'.join(f'{user}:{hasher.hash("local-test-only-password")}' for user in ['backend','sim-001']),encoding='utf-8')
        self.config={'listeners':{'default':{'type':'tcp','bind':f'127.0.0.1:{self.port}','ssl':True,
                                            'certfile':str(certs/'server.crt'),'keyfile':str(certs/'server.key'),
                                            'cafile':str(certs/'ca.crt'),'client_cert':'none'}},
                     'plugins':{'amqtt.plugins.authentication.FileAuthPlugin':{'password_file':str(password_file)},
                                'amqtt.plugins.topic_checking.TopicAccessControlListPlugin':{
                                    'acl':{'backend':['v1/bins/+/telemetry','v1/bins/+/events'],'sim-001':['v1/bins/sim-001/ack']},
                                    'publish_acl':{'backend':['v1/bins/+/ack'],'sim-001':['v1/bins/sim-001/telemetry','v1/bins/sim-001/events']}}}}
        self.thread=threading.Thread(target=self.run,daemon=True)

    def run(self):
        asyncio.set_event_loop(self.loop)
        async def start():
            try:self.broker=Broker(self.config);await self.broker.start()
            except Exception as e:self.error=e
            finally:self.ready.set()
        self.loop.run_until_complete(start())
        if self.error:return
        self.loop.run_forever()
        self.loop.close()

    def __enter__(self):
        self.thread.start();assert self.ready.wait(10)
        if self.error:raise self.error
        return self

    def __exit__(self,*args):
        if not self.error:
            asyncio.run_coroutine_threadsafe(self.broker.shutdown(),self.loop).result(10)
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)


def wait_for(predicate,timeout=8):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.05)
    raise AssertionError('Hết thời gian chờ trạng thái MQTT')


def test_tls_simulator_db_ack_restart_ai_routing(db,cfg,message,tmp_path):
    with TestBroker(tmp_path) as broker:
        cfg.mqtt_enabled=True;cfg.mqtt_host='127.0.0.1';cfg.mqtt_port=broker.port
        cfg.mqtt_password='local-test-only-password';cfg.mqtt_ca=broker.ca;cfg.mqtt_dev=False
        ingest=Ingestor(db,cfg);ingest.start();wait_for(lambda:ingest.connected)
        # Simulate losing the first application ACK after the DB commit.
        publish=ingest.client.publish;lost_ack=[False]
        def drop_first_ack(topic,*args,**kwargs):
            if topic.endswith('/ack') and not lost_ack[0]:lost_ack[0]=True;return None
            return publish(topic,*args,**kwargs)
        ingest.client.publish=drop_first_ack
        device=Settings(db=cfg.db,mqtt_enabled=True,mqtt_host='127.0.0.1',mqtt_port=broker.port,
                        mqtt_user='sim-001',mqtt_password=cfg.mqtt_password,mqtt_ca=broker.ca,mqtt_dev=False)
        full=message(kind='event',event_type='FULL',fill_pct=90.0)
        clear=message(seq=2,kind='event',event_type='CLEARED',fill_pct=10.0)
        try:
            assert publish_records([{'message':full.model_dump()},{'message':clear.model_dump()}],device,'sim-001',pace=0)==2
            assert lost_ack[0] and ingest.accepted>=3
        finally:ingest.stop()
        # Restart backend. Replay old FULL; latest state must remain CLEARED and no duplicate event/outbox.
        ingest=Ingestor(Database(db.path),cfg);ingest.start();wait_for(lambda:ingest.connected)
        try:
            assert publish_records([{'message':full.model_dump()}],device,'sim-001',pace=0)==1
        finally:ingest.stop()
        assert db.states()[0]['fill_pct']==10.0
        with db.connect() as c:
            assert c.execute('SELECT COUNT(*) FROM telemetry').fetchone()[0]==2
            assert c.execute('SELECT COUNT(*) FROM events').fetchone()[0]==2
        update_predictions(db,Predictor(cfg.model),cfg)
        assert db.states()[0]['prediction']['status']=='unavailable'
        result=solve(db.states(),RouteRequest(seconds=1));assert not result['points']
        worker=TelegramWorker(db,cfg);worker.deliver();worker.close()
        with db.connect() as c:assert {r[0] for r in c.execute('SELECT status FROM outbox')}=={'dry_run'}


def test_broker_rejects_wrong_credentials_ca_and_device_acl(db,cfg,message,tmp_path):
    with TestBroker(tmp_path) as broker:
        rejected=threading.Event();reason=[]
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='wrong-credential')
        client.tls_set(ca_certs=broker.ca);client.username_pw_set('sim-001','wrong-password')
        def connect(c,u,f,r,p):reason.append(r);rejected.set()
        client.on_connect=connect
        client.connect('127.0.0.1',broker.port);client.loop_start()
        try:assert rejected.wait(8) and reason[0]!=0
        finally:client.disconnect();client.loop_stop()
        # System trust must not accept our private lab CA.
        import pytest,ssl
        untrusted=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2);untrusted.tls_set()
        with pytest.raises(ssl.SSLError):untrusted.connect('127.0.0.1',broker.port)
        cfg.mqtt_enabled=True;cfg.mqtt_port=broker.port;cfg.mqtt_ca=broker.ca;cfg.mqtt_password='local-test-only-password'
        ingest=Ingestor(db,cfg);ingest.start();wait_for(lambda:ingest.connected)
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='acl-test')
        client.username_pw_set('sim-001',cfg.mqtt_password);client.tls_set(ca_certs=broker.ca)
        ready=threading.Event();client.on_connect=lambda *args:ready.set()
        client.connect('127.0.0.1',broker.port);client.loop_start()
        try:
            assert ready.wait(8)
            info=client.publish('v1/bins/sim-999/telemetry',message(bin_id='sim-999').model_dump_json(),qos=1)
            info.wait_for_publish(5);time.sleep(.2)
            assert ingest.accepted==0 and ingest.rejected==0 # broker ACL blocks before ingest
        finally:client.disconnect();client.loop_stop();ingest.stop()
