import json
from datetime import datetime, timezone

import httpx
import pytest

from backend.db import Database
from backend.lab import LabService
from backend.notifications import format_notification
from backend.telegram import TelegramWorker


def test_full_notification_has_measured_percent_name_and_local_time(db, message):
    m = message(kind='event', event_type='FULL', fill_pct=88.0, fault_codes=[],
                sampled_at='2026-11-18T08:13:09.036Z')
    text = format_notification(m, 'Thùng tương tác', m.measured_epoch)
    assert '[MÔ PHỎNG]' in text and '(FULL)' in text
    assert 'Mức đầy đo được: 88.0%' in text and 'Thùng tương tác (sim-001)' in text
    assert '18/11/2026 15:13:09 (UTC+7)' in text
    assert 'Cảm biến tay: Chưa ghi nhận lỗi' in text
    assert 'Cảm biến mức rác: Đang có số đo hợp lệ' in text
    assert 'Gửi bù/lịch sử' not in text
    assert 'Gửi bù/lịch sử' in format_notification(m, 'Thùng', m.measured_epoch + 61)


@pytest.mark.parametrize('codes,lid,quality,expected', [
    (['HAND_SENSOR'], 'FAULT', 'lid_open', 'Cảm biến tay: LỖI'),
    (['FILL_SENSOR'], 'CLOSED', 'fault', 'Cảm biến mức rác: LỖI'),
    (['HAND_SENSOR', 'FILL_SENSOR'], 'FAULT', 'lid_open', 'Cảm biến mức rác: LỖI'),
    (['STORAGE', 'POWER', 'LID_CONTROL'], 'FAULT', 'warming', 'Bộ nhớ/lưu trữ; Nguồn điện; Điều khiển nắp'),
])
def test_fault_notification_only_claims_reported_diagnoses(message, codes, lid, quality, expected):
    m = message(kind='event', event_type='FAULT', fill_pct=None, distance_cm=None,
                quality=quality, lid_state=lid, fault_codes=codes, dropped_records=2)
    text = format_notification(m, 'Thùng', m.measured_epoch)
    assert '(FAULT)' in text and expected in text
    assert 'Mức đầy đo được: Chưa có số đo hợp lệ' in text
    assert '0.0%' not in text and 'Đã bỏ 2 bản tin' in text
    if 'HAND_SENSOR' in codes:
        assert 'Cảm biến tay: LỖI' in text


def test_legacy_payload_does_not_invent_sensor_diagnosis(message):
    m = message(kind='event', event_type='FAULT', fill_pct=None, distance_cm=None,
                quality='fault', lid_state='FAULT')
    text = format_notification(m, 'Thùng cũ', m.measured_epoch)
    assert 'Cảm biến tay: Chưa có chẩn đoán riêng' in text
    assert 'Cảm biến mức rác: Số đo lỗi; chưa xác định nguyên nhân' in text
    assert 'Nắp chốt lỗi; chưa xác định nguyên nhân' in text
    assert 'Cảm biến tay: LỖI' not in text


@pytest.mark.parametrize('codes', [['UNKNOWN'], ['HAND_SENSOR', 'HAND_SENSOR'], ['FILL_SENSOR']])
def test_diagnostic_contract_rejects_unknown_duplicate_or_valid_fill_fault(message, codes):
    with pytest.raises(ValueError): message(fault_codes=codes)


def test_legacy_duplicate_without_new_field_still_deduplicates(db, message):
    m = message(); db.ingest(m)
    with db.connect() as c:
        row = c.execute('SELECT id,payload FROM telemetry').fetchone()
        payload = json.loads(row['payload']); payload.pop('fault_codes')
        c.execute('UPDATE telemetry SET payload=? WHERE id=?', (json.dumps(payload), row['id']))
    assert Database(db.path).ingest(m)['duplicate']


def test_threshold_backstop_uses_same_detailed_format(db, message):
    for seq in range(1,4): db.ingest(message(seq=seq, fill_pct=85.0, fault_codes=[]))
    with db.connect() as c:
        rows = c.execute('SELECT text FROM outbox').fetchall()
        assert len(rows) == 1 and 'Mức đầy đo được: 85.0%' in rows[0]['text']
        assert 'Cảm biến tay:' in rows[0]['text'] and '[MÔ PHỎNG]' in rows[0]['text']


def test_live_lab_sensor_fault_recovery_is_delivered_with_snapshot_details(db, cfg, message):
    cfg.telegram_dry_run = False; cfg.telegram_token = 'test-only-never-contacted'; cfg.telegram_chat = '123'
    service = LabService(db, cfg); session = service.start('owner')
    service.set_notifications('owner', session['session_id'], True, 0)
    base = dict(bin_id=session['bin_id'], boot_id=session['boot_id'], boot_no=session['boot_no'], kind='event')
    faulty = message(**base, seq=1, event_type='FAULT', fault_codes=['HAND_SENSOR', 'FILL_SENSOR'],
                     quality='lid_open', lid_state='FAULT', fill_pct=None, distance_cm=None)
    healthy = message(**base, seq=2, event_type='RECOVERED', fault_codes=[], fill_pct=42.0)
    service.ingest('owner', session['session_id'], faulty)
    service.ingest('owner', session['session_id'], healthy)
    assert service.ingest('owner', session['session_id'], faulty)['duplicate']
    sent = []
    def transport(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={'ok': True})
    worker = TelegramWorker(db, cfg, httpx.MockTransport(transport))
    try: worker.deliver(); worker.deliver()
    finally: worker.close()
    assert len(sent) == 2 and all(item['chat_id'] == '123' for item in sent)
    assert 'Cảm biến tay: LỖI' in sent[0]['text'] and 'Cảm biến mức rác: LỖI' in sent[0]['text']
    assert 'Mức đầy đo được: 42.0%' in sent[1]['text'] and '(RECOVERED)' in sent[1]['text']
