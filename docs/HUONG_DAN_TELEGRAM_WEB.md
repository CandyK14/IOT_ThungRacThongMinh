# Nhận Telegram từ thùng tương tác trên web

## 1. Chuẩn bị bot

Dừng backend đang chạy bằng Ctrl+C trước khi lấy chat ID. Nếu chỉ muốn thử thùng trên web, dừng terminal `backend.cli demo --watch` để tránh sinh thêm cảnh báo từ thùng nền.

Trong Telegram, mở **@BotFather** chính thức, gửi `/newbot`, đặt tên và username kết thúc bằng `bot`. BotFather cấp token. Giữ token riêng trên máy, không gửi vào chat, không đưa vào JavaScript/firmware hoặc Git.

Mở bot vừa tạo, bấm **Start** hoặc gửi `/start`. Chỉ nhắn BotFather chưa đủ: cần mở cuộc trò chuyện với chính bot của bạn.

Tài liệu chính thức: https://core.telegram.org/bots/tutorial và https://core.telegram.org/bots/api#getupdates.

## 2. Nhập token riêng trên máy và lấy ID

Trong PowerShell tại thư mục dự án:

```powershell
cd D:\S\IOT\Nhom10_DA_IoT_update
$telegramSecret = Read-Host -AsSecureString "Dan bot token vao day roi Enter"
$env:TELEGRAM_TOKEN = [System.Net.NetworkCredential]::new("", $telegramSecret).Password
.venv\Scripts\python.exe -m tools.telegram_setup
```

Lệnh in tên bot và các cặp `CHAT_ID=... USER_ID=...` của chat riêng. Chọn đúng chat của bạn. Công cụ chỉ gọi getMe/getWebhookInfo/getUpdates, không gửi tin, không in token/nội dung tin, không xóa webhook và không sửa DB. Nếu chưa thấy ID, gửi `/start` một lần nữa cho bot rồi chạy lại. Nếu polling xung đột, dừng ứng dụng khác dùng bot; nếu bot đã dùng webhook, dùng bot riêng cho dự án.

## 3. Bật backend gửi thật

Giữ nguyên terminal vừa nhập token; thay hai giá trị ví dụ bằng ID công cụ vừa in:

```powershell
$env:TELEGRAM_CHAT_ID = "123456789"
$env:TELEGRAM_USER_IDS = "123456789"
$env:TELEGRAM_DRY_RUN = "0"
$env:MQTT_ENABLED = "0"
$env:BIN_DB = "data/bins.sqlite3"
.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Chỉ chạy một backend trên DB/bot. Nếu báo worker đã có, quay về terminal cũ và Ctrl+C; không xóa file lock để lách. Biến môi trường chỉ tồn tại trong terminal này; mở PowerShell mới cần cấu hình lại. Backend không tự đọc `.env`.

Có thể gửi `/status` cho bot để thử kết nối (worker đọc khoảng10giây/lần). Token không cần nhập trên web.

## 4. Thử đúng thùng web

1. Mở http://127.0.0.1:8000, Ctrl+F5, đăng nhập tài khoản manager.
2. Trong **Phòng thử nghiệm tương tác**, mở **Thử lỗi & kết nối dashboard**.
3. Bấm **Đồng bộ với dashboard**. Kiểm tra chat đích dạng che bớt số.
4. Tích **Gửi cảnh báo Telegram cho phiên này**, chờ xác nhận đã bật.
5. Bấm **Chạy chu kỳ tự động**, giữ tab mở. Khi số đo đã lọc xác nhận đầy (FULL), bot gửi tin có nhãn **[MÔ PHỎNG]**. Sau thu gom/đóng nắp/đo lại, có tin CLEARED. Chu kỳ khoảng25giây, cộng thời gian đồng bộ và mạng.

Có thể thử tay: mở nắp → Bỏ rác hoặc đặt slider90% → rút tay → chờ nắp đóng và xác nhận FULL → Thu gom → chờ CLEARED. Mức77% giữ cảnh báo;70% cho phép xóa sau xác nhận.

## Nếu lệnh telegram_setup báo lỗi

Công cụ kiểm tra token có dạng `số:chữ` trước khi gọi mạng; không chấp nhận chỉ phần số, tiền tố `bot`, dấu nháy/backtick hoặc khoảng trắng. Nhập token mới nhất vào đúng PowerShell đang chạy lệnh. Không in `$env:TELEGRAM_TOKEN` ra để chụp/gửi lỗi.

- **Token chưa đúng dạng:** nhập nguyên chuỗi từ BotFather, gồm dấu `:` và phần chữ phía sau.
- **HTTP 401:** Telegram không chấp nhận token; kiểm tra token mới nhất sau khi revoke.
- **HTTP 404:** kiểm tra token đầy đủ và không thêm tiền tố/dấu nháy. Chưa đủ bằng chứng để khẳng định nguyên nhân chỉ từ mã này.
- **Quá thời gian / Không kết nối được:** có thể do mạng, DNS, TLS hoặc proxy. Thử mạng khác (ví dụ hotspot điện thoại) rồi chạy lại; không tắt xác minh TLS.
- **HTTP 409:** dừng backend/ứng dụng khác đang polling cùng bot.
- **HTTP 429:** chờ một lúc rồi thử lại.

Chỉ gửi lại dòng lỗi mới, không gửi token hoặc URL chứa token. Worker giữ nhóm lỗi/mã HTTP, không giữ hoặc in nguyên exception/response body có thể chứa credential. Tham khảo định dạng phản hồi chính thức: https://core.telegram.org/bots/api#making-requests.

Kiểm thử chẩn đoán: `python -m pytest -q tests/test_telegram_setup_diagnostics.py tests/test_telegram.py tests/test_lab_telegram.py` — 30 passed, dùng HTTP mock; chưa kiểm tra token/mạng thực tế trong terminal người dùng.

## Quy tắc gửi

- Mặc định mỗi phiên chỉ xem trước, kể cả backend đã bật Telegram thật. Chỉ manager sở hữu phiên được đổi lựa chọn; viewer không được gửi.
- Bật chỉ áp dụng bản tin có seq sau ranh giới hiện tại của trình duyệt/DB. FULL/CLEARED cũ đã xếp trong queue trước lúc bật không được gửi lại. Muốn nhận FULL hãy chạy chu kỳ mới; nếu thùng đang đầy, thu gom trước.
- Tắt chặn job mới; job đã xếp hàng/đang gửi vẫn có thể đến. Reload/đăng nhập lại tạo phiên xem trước mới. Nếu mất phản hồi lúc đổi lựa chọn, UI dừng đồng bộ và yêu cầu tải lại để tránh gửi khi chưa rõ trạng thái.
- Mỗi job lab lưu chat đích tại lúc bật. Đổi chat cấu hình không tự đổi đích cho phiên cũ; phiên phải được bật lại. Không lộ token/full chat trong API lab.
- Retry cùng ID không tạo thêm job DB. Telegram sendMessage không có khóa idempotency: timeout sau khi Telegram nhận tin có thể dẫn đến nhận lặp khi worker retry; không hứa exactly-once ở phía Telegram.
- Cảm biến lỗi/phục hồi cũng tạo sự kiện nếu bạn chủ động thử lỗi. AI vẫn không tự tạo cảnh báo sớm cho mã lab. API demo chung không được dùng để bỏ qua opt-in của mã lab.
- Nhãn “TELEGRAM ĐÃ BẬT” chỉ xác nhận cấu hình gửi, không chứng minh điện thoại đã nhận. Nếu chưa nhận: kiểm tra đã Start bot/chưa chặn bot, Internet, đúng chat ID, backend còn chạy và TELEGRAM_DRY_RUN=0.
- Bản `dry_run` cũ không tự gửi lại. Các job `pending` đã tồn tại từ luồng khác vẫn có thể được worker gửi khi bật toàn cục. Công cụ không tự xóa lịch sử/job.

Kiểm thử tính năng dùng HTTP mock/CSDL tạm; chưa gửi Telegram thật từ phiên làm việc Codex. Chưa kiểm tra UI bằng trình duyệt thật.
