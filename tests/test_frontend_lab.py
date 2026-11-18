import json
import subprocess
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth import create_user
from backend.lab import LabService
from backend.ml import update_predictions


def payload(message, session, **changes):
    value = message(bin_id=session['bin_id'], boot_id=session['boot_id'], boot_no=session['boot_no'], **changes)
    return value


def test_lab_role_owner_source_and_no_real_notifications(db, cfg, message):
    # Even when real Telegram is enabled, this endpoint only stores lab records.
    cfg.telegram_dry_run = False
    cfg.telegram_token = 'test-only-never-contacted'
    cfg.telegram_chat = '123'
    create_user(db, 'manager-a', 'test-password-manager-a', 'manager')
    create_user(db, 'manager-b', 'test-password-manager-b', 'manager')
    create_user(db, 'reader-lab', 'test-password-reader-lab', 'viewer')
    with TestClient(create_app(cfg, background=False)) as client:
        assert client.post('/api/lab/sessions').status_code == 401
        client.post('/api/login', json={'username':'reader-lab','password':'test-password-reader-lab'})
        assert client.post('/api/lab/sessions').status_code == 403
        client.post('/api/logout')
        client.post('/api/login', json={'username':'manager-a','password':'test-password-manager-a'})
        session = client.post('/api/lab/sessions').json()
        assert session['source'] == 'simulated' and session['notification_mode'] == 'preview_only'
        full = payload(message, session, kind='event', event_type='FULL', fill_pct=90.0)
        url = '/api/lab/sessions/' + session['session_id'] + '/messages'
        result = client.post(url, json=full.model_dump())
        assert result.status_code == 200 and result.json()['stored']
        assert client.post(url, json=full.model_dump()).json()['duplicate']
        forged = full.model_copy(update={'source':'real','time_quality':'sntp'})
        assert client.post(url, json=forged.model_dump()).status_code == 422
        other = full.model_copy(update={'bin_id':'sim-001'})
        assert client.post(url, json=other.model_dump()).status_code == 422
        assert client.get('/static/simulation.js').status_code == 200
        assert client.get('/static/simulation-core.js').status_code == 200
        assert client.get('/static/simulation.css').status_code == 200
        page = client.get('/').text
        assert 'id="simulation"' in page and 'lab-cycle' in page
        client.post('/api/logout')
        client.post('/api/login', json={'username':'manager-b','password':'test-password-manager-b'})
        assert client.post(url, json=full.model_dump()).status_code == 403
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 1


def test_lab_replay_full_clear_and_new_session_are_ordered(db, message):
    service = LabService(db)
    first = service.start('owner')
    full = payload(message, first, kind='event', event_type='FULL', fill_pct=90.0)
    clear = payload(message, first, seq=2, kind='event', event_type='CLEARED', fill_pct=10.0)
    service.ingest('owner', first['session_id'], full)
    service.ingest('owner', first['session_id'], clear)
    # Application ACK lost: identical replay is stored once and cannot restore FULL.
    assert service.ingest('owner', first['session_id'], full)['duplicate']
    second = service.start('owner')
    assert second['bin_id'] == first['bin_id'] and second['boot_no'] > first['boot_no']
    current = payload(message, second, fill_pct=30.0)
    service.ingest('owner', second['session_id'], current)
    service.ingest('owner', first['session_id'], clear)
    state = next(b for b in db.states() if b['id'] == first['bin_id'])
    assert state['fill_pct'] == 30 and state['boot_id'] == second['boot_id']
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 2


def test_lab_does_not_replace_real_registry(db):
    import hashlib
    username = 'reserved-owner'
    bin_id = 'lab-' + hashlib.sha256(username.encode()).hexdigest()[:16]
    db.register(bin_id, 'Existing real bin', 1, 1, 100, 'real')
    with pytest.raises(ValueError): LabService(db).start(username)
    with db.connect() as c:
        assert c.execute('SELECT source FROM bins WHERE id=?',(bin_id,)).fetchone()[0] == 'real'
        assert c.execute('SELECT COUNT(*) FROM boots WHERE bin_id=?',(bin_id,)).fetchone()[0] == 0


def test_lab_ai_preview_never_queues_early_telegram(db, cfg, message):
    import time
    from datetime import datetime, timezone
    service = LabService(db); session = service.start('owner')
    now = time.time()
    for i in range(8):
        stamp = datetime.fromtimestamp(now-(7-i)*300,timezone.utc).isoformat()
        m = payload(message, session, seq=i+1, fill_pct=60.0, sampled_at=stamp)
        service.ingest('owner', session['session_id'], m)
    class HighPrediction:
        def predict(self,*args,**kwargs):
            return {'status':'available','fill_pct':95,'method':'test-model','horizon_seconds':3600,
                    'valid_until':now+300,'source':'simulated','anomaly':False}
    update_predictions(db, HighPrediction(), cfg)
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM predictions').fetchone()[0] >= 1
        assert c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0] == 0


def test_frontend_native_node_scenarios():
    node = shutil.which('node')
    if node is None: pytest.skip('Frontend model tests require Node.js 18+; runtime dashboard has no Node dependency')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/frontend_simulation.test.cjs'], cwd=root,
                            capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout)
