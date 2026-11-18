"""Browser-lab connectivity rules and dedicated Wi-Fi messages."""
from datetime import datetime, timedelta, timezone

HEARTBEAT_SECONDS = 3
OFFLINE_SECONDS = 12
SSID = 'SmartBin_Demo'


def format_wifi_notice(session, event, now):
    titles = {'CONNECTED': 'ĐÃ KẾT NỐI WI-FI', 'OFFLINE': 'MẤT KẾT NỐI WI-FI', 'RESTORED': 'ĐÃ KẾT NỐI LẠI WI-FI'}
    stamp = datetime.fromtimestamp(now, timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M:%S')
    lines = [f'[WI-FI] {titles[event]}',
             f"Thùng: Thùng lab tương tác ({session['bin_id']})", f'Mạng mô phỏng: {SSID}']
    if event == 'OFFLINE':
        lines.append(f'Backend không nhận heartbeat trong ít nhất {OFFLINE_SECONDS} giây.')
        lines.append('Có thể do mất đường kết nối hoặc trang mô phỏng ngừng hoạt động; chưa xác định lỗi phần cứng.')
    elif event == 'RESTORED':
        elapsed = max(0, int(now - session.get('connection_lost_at', now)))
        lines.append(f'Đã nhận lại heartbeat. Thời gian từ lúc phát hiện mất kết nối: {elapsed} giây.')
        lines.append('Đang tiếp tục đồng bộ và gửi bù bản tin còn trong bộ đệm.')
    else:
        lines.append('Đã nhận heartbeat từ thùng mô phỏng; giám sát kết nối đã bật.')
    lines.append(f'Thời gian: {stamp} (UTC+7)')
    return '\n'.join(lines)
