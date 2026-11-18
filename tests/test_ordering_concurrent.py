from concurrent.futures import ThreadPoolExecutor
import random


def test_concurrent_duplicate_has_one_event_and_notification(db,message):
    m=message(kind='event',event_type='FULL',fill_pct=90.0)
    with ThreadPoolExecutor(max_workers=6) as pool:
        result=list(pool.map(lambda _:db.ingest(m),range(20)))
    assert sum(not a['duplicate'] for a in result)==1
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM telemetry').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1


def test_random_replay_order_cannot_replace_latest(db,message):
    messages=[message(boot_no=boot,boot_id=f'b-{boot}',seq=seq,fill_pct=float(boot*10+seq))
              for boot in range(1,5) for seq in range(1,11)]
    shuffled=messages+messages;random.Random(42).shuffle(shuffled)
    for m in shuffled:db.ingest(m)
    state=db.states()[0]
    assert state['boot_id']=='b-4' and state['fill_pct']==50
    with db.connect() as c:assert c.execute('SELECT COUNT(*) FROM telemetry').fetchone()[0]==40


def test_backstop_full_event_does_not_duplicate_alert(db,message):
    for seq in range(1,4):db.ingest(message(seq=seq,fill_pct=90.0))
    db.ingest(message(seq=4,fill_pct=90.0,kind='event',event_type='FULL'))
    with db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM events').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==1
