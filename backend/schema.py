import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    version: Literal[1]
    bin_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    boot_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    boot_no: int = Field(ge=1, le=9007199254740991)
    seq: int = Field(ge=1, le=4294967295)
    kind: Literal['telemetry', 'event']
    event_type: Literal['FULL', 'CLEARED', 'FAULT', 'RECOVERED'] | None = None
    source: Literal['real', 'simulated']
    sampled_at: str | None
    time_quality: Literal['sntp', 'simulated', 'unknown']
    uptime_ms: int = Field(ge=0, le=9007199254740991)
    fill_pct: float | None = Field(ge=0, le=100)
    full_on_pct: float = Field(default=80.0,gt=0,le=100)
    full_off_pct: float = Field(default=75.0,ge=0,lt=100)
    distance_cm: float | None = Field(ge=2, le=400)
    quality: Literal['valid', 'warming', 'stale', 'fault', 'lid_open']
    lid_state: Literal['CLOSED', 'OPENING', 'OPEN', 'CLOSING', 'FAULT']
    lid_open_count: int = Field(ge=0, le=4294967295)
    battery_mv: int | None = Field(default=None, ge=0, le=60000)
    queue_depth: int = Field(default=0, ge=0, le=128)
    dropped_records: int = Field(default=0, ge=0)
    reconnects: int = Field(default=0, ge=0)
    offline_ms: int = Field(default=0, ge=0)
    replay_delay_ms: int = Field(default=0, ge=0)

    @model_validator(mode='after')
    def consistent(self):
        if (self.kind == 'event') != (self.event_type is not None):
            raise ValueError('event cần event_type; telemetry không có event_type')
        if self.quality == 'valid' and (self.fill_pct is None or self.distance_cm is None):
            raise ValueError('Số đo valid phải có khoảng cách và mức đầy')
        if self.quality != 'valid' and self.fill_pct is not None:
            raise ValueError('Số đo không hợp lệ phải có fill_pct=null')
        if (self.sampled_at is None) != (self.time_quality == 'unknown'):
            raise ValueError('Giờ không biết phải là null')
        if self.sampled_at:
            dt = datetime.fromisoformat(self.sampled_at.replace('Z', '+00:00'))
            if dt.tzinfo is None or dt.timestamp() > datetime.now(timezone.utc).timestamp() + 300:
                raise ValueError('Timestamp cần timezone và không vượt tương lai 5 phút')
        if self.source == 'real' and self.time_quality == 'simulated':
            raise ValueError('Thiết bị thật không được dùng giờ giả lập')
        if self.event_type in ('FULL', 'CLEARED') and self.quality != 'valid':
            raise ValueError('FULL/CLEARED cần số đo hợp lệ')
        if self.full_off_pct>=self.full_on_pct:
            raise ValueError('Ngưỡng xóa phải nhỏ hơn ngưỡng đầy')
        if self.event_type=='FULL' and self.fill_pct<self.full_on_pct:
            raise ValueError('FULL cần mức đo đạt ngưỡng đầy của bản tin')
        if self.event_type=='CLEARED' and self.fill_pct>self.full_off_pct:
            raise ValueError('CLEARED cần mức đo không vượt ngưỡng xóa của bản tin')
        return self

    @property
    def measured_epoch(self):
        return (datetime.fromisoformat(self.sampled_at.replace('Z', '+00:00')).timestamp()
                if self.sampled_at else None)


def parse_message(raw: bytes, max_size=2048):
    if len(raw) > max_size:
        raise ValueError('Payload vượt giới hạn')
    return Message.model_validate(json.loads(raw))
