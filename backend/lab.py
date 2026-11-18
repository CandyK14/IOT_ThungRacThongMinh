"""Owner-scoped browser simulation sessions. Telegram requires explicit per-session opt-in."""
import hashlib
import json
import secrets
import time
import threading
from collections import defaultdict, deque

from .connectivity import HEARTBEAT_SECONDS, OFFLINE_SECONDS, SSID, format_wifi_notice


class LabService:
    def __init__(self, db, settings=None):
        self.db = db
        self.settings = settings
        self.lock = threading.RLock()
        self.rates = defaultdict(deque)

    def _limit(self, key, maximum):
        now = time.monotonic()
        queue = self.rates[key]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= maximum:
            raise ValueError('Thao tác quá nhanh; vui lòng chờ một phút')
        queue.append(now)

    def start(self, username):
        with self.lock:
            return self._start(username)

    def _start(self, username):
        self._limit(('start', username), 10)
        bin_id = 'lab-' + hashlib.sha256(username.encode()).hexdigest()[:16]
        session_id = secrets.token_hex(16)
        boot_id = 'web-' + secrets.token_hex(12)
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            existing = c.execute('SELECT source FROM bins WHERE id=?', (bin_id,)).fetchone()
            if existing and existing['source'] != 'simulated':
                raise ValueError('Mã lab đã thuộc dữ liệu thật; không thể tạo mô phỏng')
            c.execute('INSERT OR IGNORE INTO bins VALUES(?,?,?,?,?,?)',
                      (bin_id, 'Thùng lab tương tác', 10.77, 106.66, 120, 'simulated'))
            boot_no = c.execute('SELECT COALESCE(MAX(boot_no),0)+1 FROM boots WHERE bin_id=?',
                                (bin_id,)).fetchone()[0]
            c.execute('INSERT INTO boots VALUES(?,?,?)', (bin_id, boot_no, boot_id))
            session = {'session_id': session_id, 'owner': username, 'bin_id': bin_id,
                       'boot_id': boot_id, 'boot_no': boot_no, 'created_at': time.time(),
                       'source': 'simulated', 'transport': 'browser_http',
                       'notification_mode': 'preview_only', 'connection_state': 'waiting',
                       'connection_monitoring': False, 'connection_seq': 0, 'connection_episode': 0,
                       'connection_announced': False, 'connection_alerted': False,
                       'connection_retired': False}
            self._retire(c, username)
            c.execute('INSERT INTO kv VALUES(?,?)', ('lab-session:' + session_id, json.dumps(session)))
        return self._public(session)

    def _owned(self, username, session_id):
        if len(session_id) != 32 or any(c not in '0123456789abcdef' for c in session_id):
            raise ValueError('Phiên mô phỏng không hợp lệ')
        with self.db.connect() as c:
            row = c.execute('SELECT value FROM kv WHERE key=?', ('lab-session:' + session_id,)).fetchone()
        if not row:
            raise ValueError('Không tìm thấy phiên mô phỏng')
        session = json.loads(row['value'])
        if session['owner'] != username:
            raise PermissionError('Phiên mô phỏng thuộc tài khoản khác')
        return session

    def _ready(self, session=None):
        cfg = self.settings
        return bool(cfg and not cfg.telegram_dry_run and cfg.telegram_token and cfg.telegram_chat
                    and (not session or session.get('notification_chat_id') == cfg.telegram_chat))

    def _public(self, session):
        result = {k: v for k, v in session.items() if k not in ('owner', 'notification_chat_id')}
        enabled = session['notification_mode'] == 'telegram_opt_in'
        result['heartbeat_seconds'] = HEARTBEAT_SECONDS
        result['heartbeat_timeout_seconds'] = OFFLINE_SECONDS
        result['wifi_ssid'] = SSID
        result['telegram_available'] = self._ready(session if enabled else None)
        chat = session.get('notification_chat_id') if enabled else (self.settings.telegram_chat if self.settings else '')
        result['recipient_hint'] = ('…' + str(chat)[-4:]) if chat else ''
        return result

    def set_notifications(self, username, session_id, enabled, after_seq):
        # Serialize opt-in boundaries with ingest: a disable affects subsequent commits.
        with self.lock:
            session = self._owned(username, session_id)
            if enabled and session.get('connection_retired'):
                raise ValueError('Phiên đã kết thúc; hãy tạo phiên mới')
            if enabled and not self._ready():
                raise ValueError('Backend chưa bật Telegram thật; hãy cấu hình token, chat ID và TELEGRAM_DRY_RUN=0 rồi khởi động lại')
            with self.db.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                stored_seq = c.execute('SELECT COALESCE(MAX(seq),0) FROM telemetry WHERE bin_id=? AND boot_id=?',
                                       (session['bin_id'], session['boot_id'])).fetchone()[0]
                session['notification_mode'] = 'telegram_opt_in' if enabled else 'preview_only'
                session['notification_after_seq'] = max(after_seq, stored_seq)
                session['notification_chat_id'] = self.settings.telegram_chat if enabled else None
                now = time.time()
                if (enabled and session.get('connection_monitoring') and
                        now-session.get('connection_last_seen', 0) < OFFLINE_SECONDS and
                        not session.get('connection_announced')):
                    if self._network_notice(c, session, 'CONNECTED', now):
                        session['connection_announced'] = True
                self._save(c, session)
            return self._public(session)

    def ingest(self, username, session_id, message):
        with self.lock:
            return self._ingest(username, session_id, message)

    def _ingest(self, username, session_id, message):
        session = self._owned(username, session_id)
        if (message.bin_id != session['bin_id'] or message.boot_id != session['boot_id'] or
                message.boot_no != session['boot_no'] or message.source != 'simulated' or
                message.time_quality != 'simulated' or not message.bin_id.startswith('lab-')):
            raise ValueError('Bản tin không khớp phiên mô phỏng')
        self._limit(('message', username), 180)
        notify = (not session.get('connection_retired') and session['notification_mode'] == 'telegram_opt_in' and self._ready(session)
                  and message.seq > session.get('notification_after_seq', 0))
        result = self.db.ingest(message, notifications=notify,
                                notification_chat_id=session.get('notification_chat_id'))
        public = self._public(session)
        return dict(result, **{k: public[k] for k in ('notification_mode', 'telegram_available', 'recipient_hint', 'transport')})


    @staticmethod
    def _save(c, session):
        c.execute('UPDATE kv SET value=? WHERE key=?', (json.dumps(session), 'lab-session:' + session['session_id']))

    def _retire(self, c, username):
        for row in c.execute("SELECT value FROM kv WHERE key LIKE 'lab-session:%'").fetchall():
            session = json.loads(row['value'])
            if session['owner'] == username and not session.get('connection_retired'):
                session['connection_monitoring'] = False
                session['connection_retired'] = True
                session['connection_state'] = 'closed'
                self._save(c, session)

    def close_owner(self, username):
        with self.lock, self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._retire(c, username)

    def reset_connection_monitors(self):
        # Backend downtime is not evidence that a simulated device lost Wi-Fi.
        # Re-arm only after a fresh heartbeat, without inventing an outage on startup.
        with self.lock, self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for row in c.execute("SELECT value FROM kv WHERE key LIKE 'lab-session:%'").fetchall():
                session = json.loads(row['value'])
                if session.get('connection_monitoring'):
                    session['connection_monitoring'] = False
                    self._save(c, session)

    def _network_notice(self, c, session, event, now):
        if session['notification_mode'] != 'telegram_opt_in' or not self._ready(session):
            return False
        key = f"lab-wifi:{session['session_id']}:{session.get('connection_episode', 0)}:{event}"
        self.db.enqueue(c, key, format_wifi_notice(session, event, now), now, session['notification_chat_id'])
        return True

    def _expire(self, c, session, now):
        if (session.get('connection_monitoring') and not session.get('connection_retired') and
                session.get('connection_state') == 'connected' and
                now - session.get('connection_last_seen', now) >= OFFLINE_SECONDS):
            session['connection_state'] = 'offline'
            session['connection_lost_at'] = now
            session['connection_episode'] = session.get('connection_episode', 0) + 1
            session['connection_alerted'] = self._network_notice(c, session, 'OFFLINE', now)
            return True
        return False

    def check_connections(self, now=None):
        now = time.time() if now is None else now
        with self.lock, self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for row in c.execute("SELECT value FROM kv WHERE key LIKE 'lab-session:%'").fetchall():
                session = json.loads(row['value'])
                if self._expire(c, session, now):
                    self._save(c, session)

    def connection(self, username, session_id, seq, action='heartbeat', now=None):
        now = time.time() if now is None else now
        with self.lock:
            session = self._owned(username, session_id)
            if session.get('connection_retired'):
                raise ValueError('Phiên đã kết thúc; hãy tạo phiên mới')
            self._limit(('connection', username), 120)
            with self.db.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                if seq > session.get('connection_seq', 0):
                    session['connection_seq'] = seq
                    if action == 'stop':
                        session['connection_monitoring'] = False
                        session['connection_retired'] = True
                        session['connection_state'] = 'closed'
                    else:
                        # Catch a missed watchdog tick before accepting recovery.
                        self._expire(c, session, now)
                        was_offline = session.get('connection_state') == 'offline'
                        if was_offline and session.get('connection_alerted'):
                            self._network_notice(c, session, 'RESTORED', now)
                        elif not session.get('connection_announced'):
                            if self._network_notice(c, session, 'CONNECTED', now):
                                session['connection_announced'] = True
                        session['connection_alerted'] = False
                        session['connection_state'] = 'connected'
                        session['connection_monitoring'] = True
                        session['connection_last_seen'] = now
                    self._save(c, session)
            return dict(self._public(session), heartbeat_seq=seq)
