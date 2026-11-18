"""Human-readable, evidence-based notification snapshots (no network access)."""
from datetime import datetime, timedelta, timezone

VIETNAM = timezone(timedelta(hours=7))
FAULT_NAMES = {'HAND_SENSOR': 'Cảm biến tay', 'FILL_SENSOR': 'Cảm biến mức rác',
               'LID_CONTROL': 'Điều khiển nắp', 'STORAGE': 'Bộ nhớ/lưu trữ', 'POWER': 'Nguồn điện'}
LID_NAMES = {'CLOSED': 'Đã đóng', 'OPENING': 'Đang mở', 'OPEN': 'Đang mở', 'CLOSING': 'Đang đóng', 'FAULT': 'Chốt lỗi; cần kiểm tra'}


def health_lines(data):
    codes = data.get('fault_codes')
    known = codes is not None
    codes = codes or []
    hand = 'LỖI; cần kiểm tra' if 'HAND_SENSOR' in codes else 'Chưa ghi nhận lỗi' if known else 'Chưa có chẩn đoán riêng'
    if 'FILL_SENSOR' in codes:
        fill = 'LỖI; không dùng số đo để kết luận mức đầy'
    elif data.get('quality') == 'fault':
        fill = 'Số đo lỗi; chưa xác định nguyên nhân'
    elif data.get('quality') == 'valid':
        fill = 'Đang có số đo hợp lệ'
    else:
        fill = 'Đang chờ số đo hợp lệ'
    other = [FAULT_NAMES[code] for code in codes if code not in ('HAND_SENSOR', 'FILL_SENSOR')]
    if data.get('lid_state') == 'FAULT' and 'HAND_SENSOR' not in codes and 'LID_CONTROL' not in codes:
        other.append('Nắp chốt lỗi; chưa xác định nguyên nhân')
    if data.get('dropped_records', 0):
        other.append(f"Đã bỏ {data['dropped_records']} bản tin (bộ đếm tích lũy)")
    return [f'Cảm biến tay: {hand}', f'Cảm biến mức rác: {fill}',
            'Nắp: ' + LID_NAMES.get(data.get('lid_state'), 'Chưa có thông tin'),
            'Lỗi khác: ' + ('; '.join(other) if other else 'Không xác định' if known else 'Chưa có thông tin chẩn đoán')]


def format_notification(message, name, now, *, threshold=False, historical=False):
    label = 'MÔ PHỎNG' if message.source == 'simulated' else 'THIẾT BỊ'
    kind = 'FULL' if threshold else message.event_type
    titles = {'FULL': 'THÙNG ĐÃ ĐẦY — CẦN THU GOM', 'CLEARED': 'MỨC RÁC ĐÃ GIẢM — XÓA CẢNH BÁO ĐẦY',
              'FAULT': 'CẢNH BÁO LỖI THIẾT BỊ', 'RECOVERED': 'ĐÃ PHỤC HỒI LỖI ĐÃ BÁO'}
    measured = f'{message.fill_pct:.1f}%' if message.quality == 'valid' and message.fill_pct is not None else 'Chưa có số đo hợp lệ'
    lines = [f'[{label}] {titles.get(kind, "THÔNG BÁO")} ({kind})',
             f'Thùng: {name} ({message.bin_id})', f'Mức đầy đo được: {measured}']
    lines.extend(health_lines(message.model_dump()))
    if kind == 'FULL':
        lines.append(f'Ngưỡng đầy: {message.full_on_pct:g}% · Cần bố trí thu gom.')
    if message.measured_epoch is None:
        lines.append('Giờ đo: Chưa đồng bộ thời gian')
    else:
        stamp = datetime.fromtimestamp(message.measured_epoch, VIETNAM).strftime('%d/%m/%Y %H:%M:%S')
        lines.append(f'Giờ đo: {stamp} (UTC+7)')
    delay = max(0, now - message.measured_epoch) if message.measured_epoch is not None else 0
    if historical or delay >= 60 or message.replay_delay_ms >= 60000 or message.offline_ms >= 60000:
        lines.append('Gửi bù/lịch sử: đây là trạng thái tại lúc đo; xem trạng thái mới nhất trên web.')
    else:
        lines.append('Thông tin tại thời điểm đo.')
    return '\n'.join(lines)
