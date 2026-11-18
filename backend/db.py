import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager


SCHEMA = '''
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS bins(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,
 capacity_l REAL NOT NULL CHECK(capacity_l>0), source TEXT NOT NULL CHECK(source IN ('real','simulated')));
CREATE TABLE IF NOT EXISTS boots(
 bin_id TEXT NOT NULL REFERENCES bins(id), boot_no INTEGER NOT NULL, boot_id TEXT NOT NULL,
 PRIMARY KEY(bin_id,boot_no), UNIQUE(bin_id,boot_id));
CREATE TABLE IF NOT EXISTS telemetry(
 id INTEGER PRIMARY KEY, bin_id TEXT NOT NULL REFERENCES bins(id), boot_id TEXT NOT NULL,
 boot_no INTEGER NOT NULL, seq INTEGER NOT NULL, measured_at REAL, received_at REAL NOT NULL,
 source TEXT NOT NULL, quality TEXT NOT NULL, fill_pct REAL, payload TEXT NOT NULL,
 UNIQUE(bin_id,boot_id,seq));
CREATE INDEX IF NOT EXISTS history_idx ON telemetry(bin_id,measured_at);
CREATE TABLE IF NOT EXISTS events(
 telemetry_id INTEGER PRIMARY KEY REFERENCES telemetry(id), type TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bin_state(
 bin_id TEXT PRIMARY KEY REFERENCES bins(id), telemetry_id INTEGER NOT NULL REFERENCES telemetry(id),
 boot_no INTEGER NOT NULL, seq INTEGER NOT NULL, last_seen REAL NOT NULL,
 full INTEGER NOT NULL DEFAULT 0, high_count INTEGER NOT NULL DEFAULT 0, low_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS predictions(
 bin_id TEXT PRIMARY KEY REFERENCES bins(id), created_at REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(
 id INTEGER PRIMARY KEY, dedup_key TEXT NOT NULL UNIQUE, text TEXT NOT NULL, chat_id TEXT,
 status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_at REAL NOT NULL DEFAULT 0, last_error TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,password_hash TEXT NOT NULL,role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,username TEXT NOT NULL REFERENCES users(username),expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
'''


class Database:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=FULL')
        c.execute('PRAGMA foreign_keys=ON')
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def register(self, bin_id, name, lat, lon, capacity_l, source):
        with self.connect() as c:
            old = c.execute('SELECT source FROM bins WHERE id=?', (bin_id,)).fetchone()
            if old and old['source'] != source:
                raise ValueError('Không được đổi nguồn dữ liệu của thùng đã đăng ký')
            c.execute('INSERT INTO bins VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,lat=excluded.lat,lon=excluded.lon,capacity_l=excluded.capacity_l',
                      (bin_id, name, lat, lon, capacity_l, source))

    def ingest(self, msg, now=None):
        now = time.time() if now is None else now
        payload = json.dumps(msg.model_dump(), separators=(',', ':'), sort_keys=True)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            b = c.execute('SELECT * FROM bins WHERE id=?', (msg.bin_id,)).fetchone()
            if not b or b['source'] != msg.source:
                raise ValueError('Thùng chưa đăng ký hoặc sai nguồn dữ liệu')
            old = c.execute('SELECT payload FROM telemetry WHERE bin_id=? AND boot_id=? AND seq=?',
                            (msg.bin_id, msg.boot_id, msg.seq)).fetchone()
            if old:
                # Normalize additive schema defaults from earlier v1 snapshots.
                from .schema import Message
                old_normalized=json.dumps(Message.model_validate(json.loads(old['payload'])).model_dump(),separators=(',',':'),sort_keys=True)
                if old_normalized != payload:
                    raise ValueError('ID đã tồn tại với nội dung khác')
                return {'bin_id': msg.bin_id, 'boot_id': msg.boot_id, 'seq': msg.seq, 'stored': True, 'duplicate': True}
            boot = c.execute('SELECT boot_id FROM boots WHERE bin_id=? AND boot_no=?', (msg.bin_id, msg.boot_no)).fetchone()
            if boot and boot['boot_id'] != msg.boot_id:
                raise ValueError('boot_no xung đột: cần cấp lại mã thùng khi xóa NVS')
            named_boot=c.execute('SELECT boot_no FROM boots WHERE bin_id=? AND boot_id=?',(msg.bin_id,msg.boot_id)).fetchone()
            if named_boot and named_boot['boot_no']!=msg.boot_no:
                raise ValueError('boot_id không được đổi boot_no')
            c.execute('INSERT OR IGNORE INTO boots VALUES(?,?,?)', (msg.bin_id, msg.boot_no, msg.boot_id))
            cursor = c.execute('INSERT INTO telemetry(bin_id,boot_id,boot_no,seq,measured_at,received_at,source,quality,fill_pct,payload) VALUES(?,?,?,?,?,?,?,?,?,?)',
                               (msg.bin_id,msg.boot_id,msg.boot_no,msg.seq,msg.measured_epoch,now,msg.source,msg.quality,msg.fill_pct,payload))
            row_id = cursor.lastrowid
            s = c.execute('SELECT * FROM bin_state WHERE bin_id=?', (msg.bin_id,)).fetchone()
            if msg.kind == 'event':
                c.execute('INSERT INTO events VALUES(?,?)', (row_id, msg.event_type))
                label = 'MÔ PHỎNG' if msg.source == 'simulated' else 'THIẾT BỊ'
                # A telemetry backstop may already have announced this full state.
                if msg.event_type!='FULL' or not s or not s['full']:
                    self.enqueue(c, f'event:{msg.bin_id}:{msg.boot_id}:{msg.seq}',
                                 f'[{label}] Sự kiện {msg.event_type} tại {msg.bin_id}; giờ đo: {msg.sampled_at or "chưa đồng bộ"}. Có thể là lịch sử gửi bù; xem trạng thái mới nhất trên dashboard.', now)
            # boot_no is persisted monotonically on device. Never compare random UUIDs.
            newer = not s or (msg.boot_no, msg.seq) > (s['boot_no'], s['seq'])
            if newer:
                full = s['full'] if s else 0
                prior_payload=json.loads(c.execute('SELECT payload FROM telemetry WHERE id=?',(s['telemetry_id'],)).fetchone()[0]) if s else {}
                same_thresholds=(prior_payload.get('full_on_pct',80)==msg.full_on_pct and prior_payload.get('full_off_pct',75)==msg.full_off_pct)
                continuous=s and same_thresholds and s['boot_no']==msg.boot_no and now-s['last_seen']<=360
                high = (s['high_count'] if continuous else 0) + 1 if msg.quality == 'valid' and msg.fill_pct >= msg.full_on_pct else 0
                low = (s['low_count'] if continuous else 0) + 1 if msg.quality == 'valid' and msg.fill_pct <= msg.full_off_pct else 0
                old_full = full
                if high >= 3 or msg.event_type == 'FULL': full = 1
                if low >= 3 or msg.event_type == 'CLEARED': full = 0
                c.execute('INSERT INTO bin_state VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(bin_id) DO UPDATE SET telemetry_id=excluded.telemetry_id,boot_no=excluded.boot_no,seq=excluded.seq,last_seen=excluded.last_seen,full=excluded.full,high_count=excluded.high_count,low_count=excluded.low_count',
                          (msg.bin_id,row_id,msg.boot_no,msg.seq,now,full,high,low))
                if full and not old_full and msg.kind != 'event':
                    self.enqueue(c, f'threshold:{row_id}', f'[{msg.source}] {msg.bin_id}: mức đầy đo được ≥{msg.full_on_pct}% qua 3 bản tin hợp lệ; giờ đo {msg.sampled_at or "chưa đồng bộ"}. Có thể là dữ liệu gửi bù.', now)
            return {'bin_id': msg.bin_id, 'boot_id': msg.boot_id, 'seq': msg.seq, 'stored': True, 'duplicate': False}

    @staticmethod
    def enqueue(c, key, text, now, chat_id=None):
        c.execute('INSERT OR IGNORE INTO outbox(dedup_key,text,chat_id,created_at) VALUES(?,?,?,?)', (key, text, chat_id, now))

    def states(self, stale_seconds=360, now=None):
        now = time.time() if now is None else now
        with self.connect() as c:
            rows = c.execute('SELECT b.*,s.last_seen,s.full,t.payload,t.measured_at,t.received_at FROM bins b LEFT JOIN bin_state s ON s.bin_id=b.id LEFT JOIN telemetry t ON t.id=s.telemetry_id ORDER BY b.id').fetchall()
            result = []
            for r in rows:
                d = dict(r)
                p = json.loads(d.pop('payload') or '{}')
                d.update({k: p.get(k) for k in ('fill_pct','quality','lid_state','time_quality','boot_id','boot_no','seq','lid_open_count','queue_depth','dropped_records','reconnects','offline_ms','replay_delay_ms')})
                d['full_on_pct']=p.get('full_on_pct',80);d['full_off_pct']=p.get('full_off_pct',75)
                d['online'] = bool(d['last_seen'] and now - d['last_seen'] <= stale_seconds)
                # Unknown device time is not silently replaced by received_at.
                d['age_seconds'] = max(0, now-d['measured_at']) if d['measured_at'] is not None else None
                d['delivery_delay_seconds'] = max(0,d['received_at']-d['measured_at']) if d['measured_at'] is not None else None
                d['stale'] = d['age_seconds'] is None or d['age_seconds'] > stale_seconds
                d['usable'] = d['online'] and not d['stale'] and d['quality'] == 'valid' and d['lid_state']!='FAULT'
                prediction = c.execute('SELECT payload FROM predictions WHERE bin_id=?', (d['id'],)).fetchone()
                d['prediction'] = json.loads(prediction[0]) if prediction else {'status': 'unavailable'}
                result.append(d)
            return result

    def history(self, bin_id, start=0, end=1e20, limit=500):
        with self.connect() as c:
            rows = c.execute('SELECT payload,received_at,measured_at FROM telemetry WHERE bin_id=? AND COALESCE(measured_at,received_at) BETWEEN ? AND ? ORDER BY COALESCE(measured_at,received_at) DESC,id DESC LIMIT ?', (bin_id,start,end,limit)).fetchall()
            return [dict(json.loads(r['payload']), received_at=r['received_at'], measured_at=r['measured_at']) for r in reversed(rows)]
