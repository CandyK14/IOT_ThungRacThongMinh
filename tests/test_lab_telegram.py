import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth import create_user
from backend.lab import LabService
from backend.telegram import TelegramWorker
from tools.telegram_setup import inspect_bot


def live(cfg):
    cfg.telegram_dry_run = False
    cfg.telegram_token = 'test-only-token'
    cfg.telegram_chat = '123456789'
    return cfg


def event(message, session, seq, kind):
    return message(bin_id=session['bin_id'], boot_id=session['boot_id'], boot_no=session['boot_no'],
                   seq=seq, kind='event', event_type=kind, fill_pct=90.0 if kind == 'FULL' else 5.0)


def test_explicit_opt_in_excludes_buffer_and_delivers_new_events_once(db, cfg, message):
    service = LabService(db, live(cfg)); session = service.start('owner'); sid = session['session_id']
    assert session['telegram_available'] and session['notification_mode'] == 'preview_only'
    assert 'notification_chat_id' not in session and session['recipient_hint'] == '…6789'
    # Events 1/2 were generated before opt-in, but can still be in the browser queue.
    enabled = service.set_notifications('owner', sid, True, 2)
    assert enabled['notification_mode'] == 'telegram_opt_in'
    service.ingest('owner', sid, event(message, session, 1, 'FULL'))
    service.ingest('owner', sid, event(message, session, 2, 'CLEARED'))
    full = event(message, session, 3, 'FULL')
    service.ingest('owner', sid, full)
    assert service.ingest('owner', sid, full)['duplicate']
    service.ingest('owner', sid, event(message, session, 4, 'CLEARED'))
    service.set_notifications('owner', sid, False, 4)
    service.ingest('owner', sid, event(message, session, 5, 'FULL'))
    with db.connect() as c:
        rows = c.execute('SELECT * FROM outbox ORDER BY id').fetchall()
        assert len(rows) == 2 and all(r['chat_id'] == cfg.telegram_chat for r in rows)
        assert 'FULL' in rows[0]['text'] and 'CLEARED' in rows[1]['text']
        assert all('[MÔ PHỎNG]' in r['text'] for r in rows)
    sent = []
    def transport(request):
        assert request.url.path.endswith('/sendMessage')
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': len(sent)}})
    worker = TelegramWorker(db, cfg, transport=httpx.MockTransport(transport))
    try:
        worker.deliver(); worker.deliver()
    finally:
        worker.close()
    assert len(sent) == 2 and all(m['chat_id'] == '123456789' for m in sent)
    with db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM outbox WHERE status='sent'").fetchone()[0] == 2


def test_gate_requires_live_config_and_never_redirects_session(db, cfg, message):
    service = LabService(db, cfg); session = service.start('owner'); sid = session['session_id']
    with pytest.raises(ValueError): service.set_notifications('owner', sid, True, 0)
    with pytest.raises(PermissionError): service.set_notifications('other', sid, True, 0)
    live(cfg)
    service.ingest('owner', sid, event(message, session, 10, 'FULL'))
    enabled = service.set_notifications('owner', sid, True, 0)
    assert enabled['notification_after_seq'] == 10
    service.ingest('owner', sid, event(message, session, 9, 'CLEARED'))
    cfg.telegram_chat = 'different-recipient'
    ack = service.ingest('owner', sid, event(message, session, 11, 'CLEARED'))
    assert not ack['telegram_available']
    cfg.telegram_chat = '123456789'; cfg.telegram_dry_run = True
    service.ingest('owner', sid, event(message, session, 12, 'FULL'))
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0] == 0


def test_notifications_api_checks_auth_owner_and_strict_boundary(db, cfg):
    live(cfg)
    for name, role in [('manager-a', 'manager'), ('manager-b', 'manager'), ('reader', 'viewer')]:
        create_user(db, name, 'private-test-password', role)
    with TestClient(create_app(cfg, background=False)) as client:
        client.post('/api/login', json={'username': 'manager-a', 'password': 'private-test-password'})
        session = client.post('/api/lab/sessions').json()
        url = '/api/lab/sessions/' + session['session_id'] + '/notifications'
        for body in [{'enabled': 'true', 'after_seq': 0}, {'enabled': True, 'after_seq': -1},
                     {'enabled': True, 'after_seq': 0, 'chat_id': 'forged'}]:
            assert client.post(url, json=body).status_code == 422
        assert client.post(url, json={'enabled': True, 'after_seq': 0}).status_code == 200
        client.post('/api/logout')
        assert client.post(url, json={'enabled': True, 'after_seq': 0}).status_code == 401
        client.post('/api/login', json={'username': 'manager-b', 'password': 'private-test-password'})
        assert client.post(url, json={'enabled': False, 'after_seq': 0}).status_code == 403
        client.post('/api/logout')
        client.post('/api/login', json={'username': 'reader', 'password': 'private-test-password'})
        assert client.post(url, json={'enabled': True, 'after_seq': 0}).status_code == 403


def test_setup_inspector_only_reads_api_and_private_ids(cfg):
    calls = []
    def transport(request):
        method = request.url.path.rsplit('/', 1)[-1]; calls.append(method)
        result = {'getMe': {'username': 'private_test_bot'}, 'getWebhookInfo': {'url': ''},
                  'getUpdates': [{'message': {'chat': {'id': 12, 'type': 'private'}, 'from': {'id': 34}, 'text': 'SECRET_MESSAGE'}},
                                 {'message': {'chat': {'id': -1, 'type': 'group'}, 'from': {'id': 34}}}]}[method]
        return httpx.Response(200, json={'ok': True, 'result': result})
    worker = TelegramWorker(None, live(cfg), transport=httpx.MockTransport(transport))
    try:
        assert inspect_bot(worker) == ('private_test_bot', [(12, 34)])
    finally:
        worker.close()
    assert calls == ['getMe', 'getWebhookInfo', 'getUpdates']


def test_setup_inspector_does_not_remove_existing_webhook(cfg):
    calls = []
    def transport(request):
        method = request.url.path.rsplit('/', 1)[-1]; calls.append(method)
        result = {'username': 'test_bot'} if method == 'getMe' else {'url': 'https://private.example/hook'}
        return httpx.Response(200, json={'ok': True, 'result': result})
    worker = TelegramWorker(None, live(cfg), transport=httpx.MockTransport(transport))
    try:
        with pytest.raises(ValueError, match='webhook'): inspect_bot(worker)
    finally:
        worker.close()
    assert calls == ['getMe', 'getWebhookInfo']


def test_generic_demo_ingest_cannot_bypass_lab_opt_in(db, cfg, message):
    live(cfg); create_user(db, 'owner', 'private-test-password', 'manager')
    with TestClient(create_app(cfg, background=False)) as client:
        client.post('/api/login', json={'username': 'owner', 'password': 'private-test-password'})
        session = client.post('/api/lab/sessions').json()
        full = event(message, session, 1, 'FULL')
        assert client.post('/api/demo/ingest', json=full.model_dump()).status_code == 422
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0] == 0
