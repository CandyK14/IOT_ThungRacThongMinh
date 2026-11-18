import hashlib
import hmac
import secrets
import time


def hash_password(password, salt=None):
    if len(password) < 12 or len(password) > 256:
        raise ValueError('Mật khẩu cần 12–256 ký tự')
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password, encoded):
    try:
        _, salt, _ = encoded.split('$')
        return hmac.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def create_user(db, username, password, role):
    if role not in ('viewer', 'manager'):
        raise ValueError('Vai trò không hợp lệ')
    with db.connect() as c:
        c.execute('INSERT INTO users VALUES(?,?,?)', (username, hash_password(password), role))


def login(db, username, password, lifetime):
    with db.connect() as c:
        row = c.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        # Perform the same expensive hash when user does not exist.
        encoded = row['password_hash'] if row else hash_password('dummy-password-only', '00'*16)
        if not verify_password(password, encoded) or not row:
            return None
        token = secrets.token_urlsafe(32)
        c.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        c.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(),username,time.time()+lifetime))
        return token


def session_user(db, token):
    if not token: return None
    with db.connect() as c:
        row = c.execute('SELECT u.username,u.role FROM sessions s JOIN users u ON u.username=s.username WHERE token_hash=? AND expires>?', (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        return dict(row) if row else None
