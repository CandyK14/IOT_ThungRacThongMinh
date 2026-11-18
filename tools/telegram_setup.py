"""Inspect bot/private-chat setup without sending messages or exposing credentials.
Run from the project root: python -m tools.telegram_setup
"""
import re

from backend.config import Settings
from backend.telegram import TelegramWorker


def validate_token(token):
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
        raise ValueError('Token chưa đúng dạng số:chữ. Nhập NGUYÊN chuỗi từ BotFather, gồm dấu hai chấm và phần chữ; không kèm dấu nháy, backtick hoặc tiền tố bot.')


def failure_message(worker, fallback):
    status = getattr(worker, 'last_http_status', None)
    if status == 401:
        return 'HTTP 401: Telegram không chấp nhận token. Có thể token sai hoặc đã bị thu hồi; nhập lại token mới nhất từ BotFather.'
    if status == 404:
        return 'HTTP 404: Không tìm thấy API bot. Kiểm tra đã nhập nguyên token mới nhất, không thêm tiền tố bot hoặc dấu nháy.'
    if status == 409:
        return 'HTTP 409: Xung đột nhận cập nhật. Dừng backend/ứng dụng khác đang polling cùng bot rồi thử lại.'
    if status == 429:
        return 'HTTP 429: Quá nhiều yêu cầu; chờ một lúc rồi thử lại.'
    error = getattr(worker, 'last_error', None)
    if error == 'timeout':
        return 'Kết nối Telegram quá thời gian chờ. Kiểm tra Internet hoặc thử mạng khác rồi chạy lại.'
    if error in ('connection', 'network'):
        return 'Không kết nối được api.telegram.org. Có thể do DNS, TLS, proxy hoặc đường mạng; thử mạng khác rồi chạy lại.'
    if error == 'invalid_response':
        return 'Phản hồi không đúng định dạng Telegram. Có thể kết nối đang qua proxy/trang chặn của mạng; thử mạng khác.'
    return fallback + (f' HTTP {status}.' if isinstance(status, int) else '')


def inspect_bot(worker):
    ok, data, _ = worker.request('getMe', {})
    if not ok:
        raise ValueError(failure_message(worker, 'Không kiểm tra được bot. Kiểm tra token và Internet; token không được in ra.'))
    username = data.get('result', {}).get('username', '')
    ok, data, _ = worker.request('getWebhookInfo', {})
    if not ok:
        raise ValueError(failure_message(worker, 'Không đọc được cấu hình webhook; thử lại sau.'))
    if data.get('result', {}).get('url'):
        raise ValueError('Bot đang dùng webhook. Hãy dùng bot riêng cho dự án; công cụ không tự xóa webhook.')
    ok, data, _ = worker.request('getUpdates', {'timeout': 0, 'limit': 100, 'allowed_updates': ['message']})
    if not ok:
        raise ValueError(failure_message(worker, 'Không đọc được tin nhắn. Dừng backend hoặc ứng dụng khác đang dùng bot rồi thử lại.'))
    chats = set()
    for update in data.get('result', []):
        message = update.get('message', {})
        chat, sender = message.get('chat', {}), message.get('from', {})
        if chat.get('type') == 'private' and isinstance(chat.get('id'), int) and isinstance(sender.get('id'), int):
            chats.add((chat['id'], sender['id']))
    return username, sorted(chats)


def main():
    cfg = Settings()
    if not cfg.telegram_token:
        print('Chưa có TELEGRAM_TOKEN trong terminal này. Nhập token riêng trên máy trước.')
        return 1
    try:
        validate_token(cfg.telegram_token)
    except ValueError as error:
        print(str(error))
        return 1
    worker = TelegramWorker(None, cfg)
    try:
        username, chats = inspect_bot(worker)
        print('Bot: @' + username)
        if not chats:
            print('Chưa thấy chat riêng. Mở bot, bấm Start/gửi /start, rồi chạy lại lệnh này. Dừng backend trước.')
            return 1
        for chat, user in chats:
            print(f'CHAT_ID={chat}  USER_ID={user}')
        print('Chọn đúng chat của bạn để đặt TELEGRAM_CHAT_ID và TELEGRAM_USER_IDS. Không có tin nhắn nào được gửi bởi công cụ này.')
        return 0
    except ValueError as error:
        print(str(error))
        return 1
    finally:
        worker.close()


if __name__ == '__main__':
    raise SystemExit(main())
