import time
from datetime import datetime,timezone

import pytest

from backend.config import Settings
from backend.db import Database
from backend.schema import Message


@pytest.fixture
def cfg(tmp_path):
    return Settings(db=tmp_path/'test.sqlite3',model=tmp_path/'missing.joblib',mqtt_enabled=False,telegram_dry_run=True)


@pytest.fixture
def db(cfg):
    value=Database(cfg.db);value.register('sim-001','Thùng kiểm thử',10.77,106.66,120,'simulated');return value


@pytest.fixture
def message():
    def make(**changes):
        m=dict(version=1,bin_id='sim-001',boot_id='boot-a',boot_no=1,seq=1,kind='telemetry',source='simulated',
               sampled_at=datetime.now(timezone.utc).isoformat(),time_quality='simulated',uptime_ms=1000,
               fill_pct=50.0,distance_cm=17.0,quality='valid',lid_state='CLOSED',lid_open_count=0)
        m.update(changes);return Message.model_validate(m)
    return make
