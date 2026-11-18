import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth import create_user
from backend.db import Database
from backend.mqtt import Ingestor
from backend.runtime import SingleWorker
from backend.schema import parse_message


def test_dedup_durable_ack_and_payload_conflict(db,message):
    m=message(kind='event',event_type='FULL',fill_pct=85.0)
    ack=db.ingest(m);assert ack['stored'] and not ack['duplicate']
    restarted=Database(db.path);assert restarted.ingest(m)['duplicate']
    with restarted.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM events').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
    with pytest.raises(ValueError):restarted.ingest(m.model_copy(update={'fill_pct':90.0}))


def test_offline_full_clear_replay_and_old_boot(db,message):
    current=message(boot_no=2,boot_id='new',seq=2,fill_pct=10.0,kind='event',event_type='CLEARED')
    db.ingest(current)
    db.ingest(message(kind='event',event_type='FULL',fill_pct=90.0))
    db.ingest(message(seq=2,kind='event',event_type='CLEARED',fill_pct=20.0))
    assert db.states()[0]['fill_pct']==10.0
    assert not db.states()[0]['full']
    assert len(db.history('sim-001'))==3
    with pytest.raises(ValueError):db.ingest(message(boot_no=2,boot_id='different'))
    with pytest.raises(ValueError):db.ingest(message(boot_no=3,boot_id='new',seq=3))


def test_unknown_time_and_stale_not_zero(db,message):
    db.ingest(message(fill_pct=None,distance_cm=None,quality='fault',sampled_at=None,time_quality='unknown'),now=1000)
    b=db.states(now=1001)[0]
    assert b['online'] and b['stale'] and not b['usable'] and b['fill_pct'] is None and b['age_seconds'] is None
    assert not db.states(now=1400)[0]['online']


def test_replay_does_not_restore_online(db,message):
    m=message();db.ingest(m,now=1000);db.ingest(m,now=2000)
    assert not db.states(now=2000)[0]['online']


def test_backend_threshold_confirmation_and_invalid(db,message):
    for seq in range(1,3):db.ingest(message(seq=seq,fill_pct=85.0))
    assert not db.states()[0]['full']
    db.ingest(message(seq=3,fill_pct=None,distance_cm=None,quality='fault'))
    assert not db.states()[0]['full']
    for seq in range(4,7):db.ingest(message(seq=seq,fill_pct=85.0))
    assert db.states()[0]['full']
    db.ingest(message(seq=7,fill_pct=77.0));assert db.states()[0]['full']
    for seq in range(8,11):db.ingest(message(seq=seq,fill_pct=74.0))
    assert not db.states()[0]['full']


def test_custom_threshold_contract(db,message):
    for seq in range(1,4):db.ingest(message(seq=seq,fill_pct=72.0,full_on_pct=70.0,full_off_pct=60.0))
    b=db.states()[0];assert b['full'] and b['full_on_pct']==70
    db.ingest(message(seq=4,fill_pct=60.0,full_on_pct=70.0,full_off_pct=60.0,kind='event',event_type='CLEARED'))
    assert not db.states()[0]['full']
    with pytest.raises(ValueError):message(full_on_pct=60.0,full_off_pct=70.0)


@pytest.mark.parametrize('changes',[
    {'fill_pct':101.0},{'fill_pct':float('nan')},{'fill_pct':None},
    {'quality':'fault'},{'sampled_at':None},{'sampled_at':'2026-01-01T00:00:00'},
    {'kind':'event'},{'event_type':'FULL'},{'boot_no':0},{'seq':True},
    {'kind':'event','event_type':'FULL','fill_pct':50.0},
    {'kind':'event','event_type':'CLEARED','fill_pct':90.0}])
def test_schema_rejects_inconsistent(message,changes):
    with pytest.raises(ValueError):message(**changes)


def test_mqtt_contract_rate_size_and_source(db,cfg,message):
    cfg.mqtt_dev=True;ingest=Ingestor(db,cfg);raw=message().model_dump_json().encode()
    with pytest.raises(ValueError):ingest.handle('v1/bins/other/telemetry',raw)
    with pytest.raises(ValueError):parse_message(b' '*2049)
    with pytest.raises(ValueError):db.ingest(message(source='real',time_quality='sntp'))
    assert ingest.handle('v1/bins/sim-001/telemetry',raw)['stored']
    assert ingest.handle('v1/bins/sim-001/telemetry',raw)['duplicate']
    for _ in range(118):ingest.handle('v1/bins/sim-001/telemetry',raw)
    with pytest.raises(ValueError):ingest.handle('v1/bins/sim-001/telemetry',raw)


def test_sessions_roles_csrf_size_and_export(db,cfg,message):
    create_user(db,'admin','test-password-admin','manager');create_user(db,'reader','test-password-view','viewer')
    with TestClient(create_app(cfg,background=False)) as c:
        assert c.get('/health').status_code==200
        assert c.get('/').status_code==200
        assert c.get('/api/bins').status_code==401
        assert c.post('/api/login',json={'username':'reader','password':'wrong-password'}).status_code==401
        invalid_password='x'*257
        invalid=c.post('/api/login',json={'username':'reader','password':invalid_password})
        assert invalid.status_code==422 and invalid_password not in invalid.text
        r=c.post('/api/login',json={'username':'reader','password':'test-password-view'})
        assert r.status_code==200 and 'httponly' in r.headers['set-cookie'].lower()
        assert c.get('/api/bins').status_code==200
        assert c.post('/api/routes',json={}).status_code==403
        assert c.get('/api/export?bin_id=sim-001').status_code==403
        c.post('/api/logout');assert c.get('/api/me').status_code==401
        c.post('/api/login',json={'username':'admin','password':'test-password-admin'})
        assert c.post('/api/routes',json={},headers={'Origin':'https://evil.example'}).status_code==403
        assert c.post('/api/demo/ingest',content=b' '*4097).status_code==413
        assert c.post('/api/demo/ingest',json=message().model_dump()).status_code==200
        assert c.post('/api/demo/ingest',json=message(source='real',time_quality='sntp').model_dump()).status_code==422
        result=c.get('/api/export?bin_id=sim-001');assert result.status_code==200
        assert json.loads(result.text)['message']['source']=='simulated'
        assert c.post('/api/routes',json={'seconds':1}).status_code==200


def test_password_and_worker_lock(db,cfg):
    with pytest.raises(ValueError):create_user(db,'weak','short','manager')
    a=SingleWorker(cfg.db);b=SingleWorker(cfg.db);a.acquire()
    try:
        with pytest.raises((RuntimeError,OSError)):b.acquire()
    finally:a.release()


def test_tls_no_silent_fallback(cfg):
    cfg.mqtt_enabled=True;cfg.mqtt_ca='';cfg.mqtt_password='local-test'
    with pytest.raises(ValueError):cfg.validate()
    cfg.mqtt_dev=True;cfg.mqtt_host='example.org'
    with pytest.raises(ValueError):cfg.validate()
