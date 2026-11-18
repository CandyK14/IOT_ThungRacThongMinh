import httpx

from backend.db import Database
from backend.telegram import TelegramWorker


def pending(db):
    with db.connect() as c:db.enqueue(c,'unit-event','Kiểm thử mock',1000)


def test_dry_run_never_contacts_network(db,cfg):
    pending(db)
    def forbidden(request):raise AssertionError('Dry-run không được gửi mạng')
    w=TelegramWorker(db,cfg,httpx.MockTransport(forbidden));w.deliver(now=1000);w.close()
    with db.connect() as c:assert c.execute('SELECT status FROM outbox').fetchone()[0]=='dry_run'


def test_ok_false_retry_after_survives_restart(db,cfg):
    pending(db);cfg.telegram_dry_run=False;cfg.telegram_token='test-token';cfg.telegram_chat='123'
    calls=[]
    def fail(request):calls.append(1);return httpx.Response(429,json={'ok':False,'parameters':{'retry_after':123}})
    w=TelegramWorker(db,cfg,httpx.MockTransport(fail));w.deliver(now=1000);w.close()
    with db.connect() as c:
        r=c.execute('SELECT * FROM outbox').fetchone();assert r['status']=='pending' and r['next_at']==1123
    def success(request):return httpx.Response(200,json={'ok':True,'result':{'message_id':1}})
    w=TelegramWorker(Database(db.path),cfg,httpx.MockTransport(success));w.deliver(now=1100)
    with db.connect() as c:assert c.execute('SELECT attempts FROM outbox').fetchone()[0]==1
    w.deliver(now=1123);w.close()
    with db.connect() as c:assert c.execute('SELECT status FROM outbox').fetchone()[0]=='sent'


def test_json_ok_false_http_200_and_timeout(db,cfg):
    cfg.telegram_dry_run=False;cfg.telegram_token='test';cfg.telegram_chat='123'
    worker=TelegramWorker(db,cfg,httpx.MockTransport(lambda r:httpx.Response(200,json={'ok':False})))
    assert worker.request('sendMessage',{})[0] is False;worker.close()
    def timeout(r):raise httpx.ReadTimeout('timeout')
    worker=TelegramWorker(db,cfg,httpx.MockTransport(timeout));assert worker.request('sendMessage',{})[0] is False;worker.close()


def test_chat_user_allowlist_and_idempotent_commands(db,cfg):
    cfg.telegram_chat='123';cfg.telegram_users='456'
    worker=TelegramWorker(db,cfg)
    update={'update_id':1,'message':{'chat':{'id':123},'from':{'id':999},'text':'/status'}}
    assert not worker.process_update(update)
    update['message']['from']['id']=456;assert worker.process_update(update)
    assert worker.process_update(update)
    update['message']['chat']['id']=888;assert not worker.process_update(update)
    with db.connect() as c:assert c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
    worker.close()


def test_verbose_http_log_redacts_token(db,cfg,caplog):
    import logging
    cfg.telegram_token='do-not-log-this-token';cfg.telegram_dry_run=False
    caplog.set_level(logging.INFO,logger='httpx')
    worker=TelegramWorker(db,cfg,httpx.MockTransport(lambda r:httpx.Response(200,json={'ok':True})))
    assert worker.request('sendMessage',{})[0]
    worker.close()
    assert cfg.telegram_token not in caplog.text and '[REDACTED]' in caplog.text


def test_shutdown_keeps_unsent_jobs_pending(db,cfg):
    import threading
    pending(db);stop=threading.Event();stop.set()
    worker=TelegramWorker(db,cfg);worker.deliver(now=1000,stop=stop);worker.close()
    with db.connect() as c:
        row=c.execute('SELECT status,attempts FROM outbox').fetchone()
        assert row['status']=='pending' and row['attempts']==0
