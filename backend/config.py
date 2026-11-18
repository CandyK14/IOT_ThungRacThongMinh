import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    db: Path = field(default_factory=lambda: Path(os.getenv('BIN_DB', 'data/bins.sqlite3')))
    model: Path = field(default_factory=lambda: Path(os.getenv('BIN_MODEL', 'data/model.joblib')))
    mqtt_host: str = field(default_factory=lambda: os.getenv('MQTT_HOST', '127.0.0.1'))
    mqtt_port: int = field(default_factory=lambda: int(os.getenv('MQTT_PORT', '8883')))
    mqtt_user: str = field(default_factory=lambda: os.getenv('MQTT_USER', 'backend'))
    mqtt_password: str = field(default_factory=lambda: os.getenv('MQTT_PASSWORD', ''))
    mqtt_ca: str = field(default_factory=lambda: os.getenv('MQTT_CA', ''))
    mqtt_enabled: bool = field(default_factory=lambda: os.getenv('MQTT_ENABLED', '0') == '1')
    mqtt_dev: bool = field(default_factory=lambda: os.getenv('MQTT_DEV_LOOPBACK', '0') == '1')
    telegram_dry_run: bool = field(default_factory=lambda: os.getenv('TELEGRAM_DRY_RUN', '1') != '0')
    telegram_token: str = field(default_factory=lambda: os.getenv('TELEGRAM_TOKEN', ''))
    telegram_chat: str = field(default_factory=lambda: os.getenv('TELEGRAM_CHAT_ID', ''))
    telegram_users: str = field(default_factory=lambda: os.getenv('TELEGRAM_USER_IDS', ''))
    secure_cookie: bool = field(default_factory=lambda: os.getenv('COOKIE_SECURE', '0') == '1')
    stale_seconds: int = 360
    session_seconds: int = 8 * 3600
    max_payload: int = 2048

    def validate(self):
        if self.mqtt_enabled:
            if self.mqtt_dev and self.mqtt_host not in ('127.0.0.1', 'localhost', '::1'):
                raise ValueError('MQTT phát triển chỉ được dùng loopback')
            if not self.mqtt_dev and not self.mqtt_ca:
                raise ValueError('MQTT TLS cần MQTT_CA; không tự hạ cấp TLS')
            if not self.mqtt_password:
                raise ValueError('Cần MQTT_PASSWORD')
        if not self.telegram_dry_run and not (self.telegram_token and self.telegram_chat):
            raise ValueError('Telegram thật cần token và chat ID')
