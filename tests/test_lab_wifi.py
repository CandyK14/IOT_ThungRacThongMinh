import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth import create_user
from backend.connectivity import OFFLINE_SECONDS
from backend.lab import LabService
from backend.telegram import TelegramWorker


def ready(db, cfg):
    cfg.telegram_token = 'mock-only'; cfg.telegram_chat = '123456789'; cfg.telegram_dry_run = False
    return LabService(db, cfg)


def texts(db):
    with db.connect() as c:
        return [row['text'] for row in c.execute('SELECT text FROM outbox ORDER BY id')]


def test_wifi_messages_are_separate_and_each_outage_notifies_once(db, cfg):
    service = ready(db, cfg); session = service.start('owner'); sid = session['session_id']
    service.connection('owner', sid, 1, now=1000)
    with patch('backend.lab.time.time', return_value=1000):
        service.set_notifications('owner', sid, True, 0)
    assert len(texts(db)) == 1 and 'ĐÃ KẾT NỐI WI-FI' in texts(db)[0]
    service.check_connections(1011.99); assert len(texts(db)) == 1
    service.check_connections(1012); service.check_connections(1050)
    assert len(texts(db)) == 2 and 'MẤT KẾT NỐI WI-FI' in texts(db)[1]
    service.connection('owner', sid, 2, now=1051)
    service.connection('owner', sid, 2, now=1052)
    assert len(texts(db)) == 3 and 'ĐÃ KẾT NỐI LẠI WI-FI' in texts(db)[2]
    service.check_connections(1063); service.connection('owner', sid, 3, now=1064)
    assert len(texts(db)) == 5
    for text in texts(db):
        assert '[WI-FI]' in text and 'SmartBin_Demo' in text and '(UTC+7)' in text
        assert not any(field in text for field in ['Mức đầy đo được:', 'Cảm biến tay:', 'Cảm biến mức rác:', 'Lỗi khác:', '(FULL)'])
    sent=[]
    def transport(request):
        sent.append(json.loads(request.content)); return httpx.Response(200, json={'ok':True})
    worker=TelegramWorker(db, cfg, httpx.MockTransport(transport))
    try: worker.deliver(); worker.deliver()
    finally: worker.close()
    assert len(sent) == 5 and all(m['chat_id'] == '123456789' for m in sent)


def test_preview_and_dry_run_do_not_send_wifi_jobs(db, cfg):
    service=LabService(db,cfg); session=service.start('owner'); sid=session['session_id']
    service.connection('owner',sid,1,now=1000); service.check_connections(1020)
    service.connection('owner',sid,2,now=1021)
    assert texts(db) == []
    cfg.telegram_dry_run=False; cfg.telegram_token='mock-only';cfg.telegram_chat='123'
    with patch('backend.lab.time.time', return_value=1021):service.set_notifications('owner',sid,True,0)
    cfg.telegram_dry_run=True
    service.check_connections(1040);service.connection('owner',sid,3,now=1041)
    assert len(texts(db)) == 1


def test_old_heartbeat_and_telemetry_replay_cannot_keep_wifi_online(db,cfg,message):
    service=ready(db,cfg);session=service.start('owner');sid=session['session_id']
    service.connection('owner',sid,5,now=1000)
    with patch('backend.lab.time.time', return_value=1000):service.set_notifications('owner',sid,True,0)
    service.connection('owner',sid,4,now=1010)
    m=message(bin_id=session['bin_id'],boot_id=session['boot_id'],boot_no=session['boot_no'])
    service.ingest('owner',sid,m)
    service.check_connections(1012)
    service.ingest('owner',sid,m)
    service.check_connections(1100)
    assert len(texts(db)) == 2
    bin_state=next(b for b in db.states(now=1013) if b['id']==session['bin_id'])
    assert not bin_state['online'] and bin_state['wifi_state']=='offline' and not bin_state['usable']
    assert service.connection('owner',sid,6,now=1101)['connection_state']=='connected'
    assert len(texts(db)) == 3


def test_heartbeat_recovers_even_if_watchdog_tick_was_delayed(db,cfg):
    service=ready(db,cfg);session=service.start('owner');sid=session['session_id']
    with patch('backend.lab.time.time', return_value=1000):service.set_notifications('owner',sid,True,0)
    service.connection('owner',sid,1,now=1000)
    service.connection('owner',sid,2,now=1020)
    assert len(texts(db)) == 3
    assert 'MẤT KẾT NỐI' in texts(db)[1] and 'ĐÃ KẾT NỐI LẠI' in texts(db)[2]


def test_retired_session_and_backend_restart_do_not_invent_outages(db,cfg):
    service=ready(db,cfg);first=service.start('owner');sid=first['session_id']
    service.connection('owner',sid,1,now=1000)
    with patch('backend.lab.time.time', return_value=1000):service.set_notifications('owner',sid,True,0)
    service.reset_connection_monitors();service.check_connections(5000)
    assert len(texts(db))==1
    service.connection('owner',sid,2,now=5001);service.check_connections(5002)
    assert len(texts(db))==1
    second=service.start('owner');service.check_connections(6000)
    with pytest.raises(ValueError): service.connection('owner',sid,3,now=6001)
    assert len(texts(db))==1
    service.connection('owner',second['session_id'],1,now=6001)
    service.close_owner('owner');service.check_connections(7000)
    assert len(texts(db))==1


def test_network_recipient_and_disable_gate_match_session_opt_in(db,cfg):
    service=ready(db,cfg);session=service.start('owner');sid=session['session_id']
    service.connection('owner',sid,1,now=1000)
    with patch('backend.lab.time.time', return_value=1000):service.set_notifications('owner',sid,True,0)
    cfg.telegram_chat='different'
    service.check_connections(1020);service.connection('owner',sid,2,now=1021)
    assert len(texts(db))==1
    cfg.telegram_chat='123456789'
    service.set_notifications('owner',sid,False,0)
    service.check_connections(1040);service.connection('owner',sid,3,now=1041)
    assert len(texts(db))==1


def test_concurrent_watchdog_and_recovery_only_queue_one_outage_pair(db,cfg):
    service=ready(db,cfg);session=service.start('owner');sid=session['session_id']
    service.connection('owner',sid,1,now=1000)
    with patch('backend.lab.time.time', return_value=1000):service.set_notifications('owner',sid,True,0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(service.check_connections,1020) for _ in range(3)]
        futures.append(pool.submit(service.connection,'owner',sid,2,'heartbeat',1020))
        for future in futures:future.result()
    assert len(texts(db))==3


def test_connection_api_requires_owner_manager_and_valid_sequence(db,cfg):
    ready(db,cfg)
    for name,role in [('a','manager'),('b','manager'),('reader','viewer')]:create_user(db,name,'private-test-password',role)
    app=create_app(cfg,background=False)
    with TestClient(app) as client:
        client.post('/api/login',json={'username':'a','password':'private-test-password'})
        session=client.post('/api/lab/sessions').json();url='/api/lab/sessions/'+session['session_id']+'/connection'
        for body in [{'seq':True},{'seq':0},{'seq':1,'action':'disconnect'},{'seq':1,'chat_id':'forged'}]:
            assert client.post(url,json=body).status_code==422
        ack=client.post(url,json={'seq':1}).json();assert ack['connection_state']=='connected' and ack['heartbeat_seq']==1
        assert 'owner' not in ack and 'notification_chat_id' not in ack
        client.post('/api/logout');assert client.post(url,json={'seq':2}).status_code==401
        client.post('/api/login',json={'username':'b','password':'private-test-password'})
        assert client.post(url,json={'seq':2}).status_code==403
        client.post('/api/logout');client.post('/api/login',json={'username':'reader','password':'private-test-password'})
        assert client.post(url,json={'seq':2}).status_code==403


def test_watchdog_thread_enqueues_loss_while_telegram_worker_is_blocked(db,cfg):
    # No real HTTP: hold delivery, then expire the lease and wait for the independent monitor.
    import threading
    ready(db,cfg);release=threading.Event();entered=threading.Event()
    def blocked_deliver(self,*args,**kwargs):entered.set();release.wait(5)
    app=create_app(cfg,background=True)
    with patch.object(TelegramWorker,'deliver',blocked_deliver),patch.object(TelegramWorker,'poll',lambda self:None),patch('backend.app.update_predictions',lambda *args:None):
        try:
            with TestClient(app):
                assert entered.wait(2)
                service=app.state.lab;session=service.start('owner');sid=session['session_id']
                service.connection('owner',sid,1)
                service.set_notifications('owner',sid,True,0)
                with service.lock,db.connect() as c:
                    saved=service._owned('owner',sid);saved['connection_last_seen']=time.time()-OFFLINE_SECONDS-1
                    service._save(c,saved)
                deadline=time.monotonic()+3
                while time.monotonic()<deadline and len(texts(db))<2:time.sleep(.05)
                assert len(texts(db))==2 and 'MẤT KẾT NỐI WI-FI' in texts(db)[1]
                release.set()
        finally:release.set()


def test_live_heartbeat_does_not_make_an_old_level_measurement_fresh(db,cfg,message):
    service=ready(db,cfg);session=service.start('owner');sid=session['session_id']
    m=message(bin_id=session['bin_id'],boot_id=session['boot_id'],boot_no=session['boot_no'])
    service.ingest('owner',sid,m)
    now=m.measured_epoch+500
    service.connection('owner',sid,1,now=now)
    state=next(b for b in db.states(now=now+1) if b['id']==session['bin_id'])
    assert state['online'] and state['wifi_state']=='connected'
    assert state['stale'] and not state['usable']
    assert state['fill_pct']==m.fill_pct
