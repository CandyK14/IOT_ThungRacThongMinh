# Wi-Fi mô phỏng và tin Telegram riêng

## Thử trên web

1. Ctrl+C backend cũ, chạy lại trong PowerShell đã đặt token/chat ID và TELEGRAM_DRY_RUN=0. Chỉ chạy một backend. Máy tính vẫn cần Internet thật để gửi Telegram.
2. Ctrl+F5 web, đăng nhập quản lý, bấm Đồng bộ với dashboard.
3. Bảng Wi-Fi mô phỏng hiển thị mạng giả lập SmartBin_Demo và trạng thái chờ/đã kết nối. Bật Gửi cảnh báo Telegram cho phiên này để nhận tin Wi-Fi riêng xác nhận kết nối.
4. Bấm Ngắt Wi-Fi mô phỏng. Giữ tab mở và chờ khoảng12–14giây, cộng thời gian xử lý Telegram/mạng. Backend nhận thiếu heartbeat, tạo một tin MẤT KẾT NỐI WI-FI. Không phải thùng đã mất Wi-Fi tự gửi tin ra ngoài.
5. Thùng vẫn mở nắp/đo/hiển thị LED khi ngắt. Bản tin đầy/lỗi được giữ trong queue RAM32 bản, rồi gửi bù khi kết nối lại trong khả năng bộ đệm.
6. Bấm Kết nối lại Wi-Fi mô phỏng. Backend nhận heartbeat mới và gửi ĐÃ KẾT NỐI LẠI WI-FI nếu đợt mất kết nối trước đã được thông báo. Ngắt dưới12giây được coi là gián đoạn ngắn; không tạo cặp cảnh báo mất/phục hồi.

Ô Giả lập mất Wi-Fi của thùng trong phần nâng cao và nút Wi-Fi phía trên dùng cùng một trạng thái.

## Mẫu tin độc lập

```text
[MÔ PHỎNG WI-FI] ĐÃ KẾT NỐI WI-FI
Thùng: Thùng lab tương tác (lab-...)
Mạng mô phỏng: SmartBin_Demo
Đã nhận heartbeat từ thùng mô phỏng; giám sát kết nối đã bật.
Thời gian: 18/11/2026 16:00:00 (UTC+7)
```

```text
[MÔ PHỎNG WI-FI] MẤT KẾT NỐI WI-FI
Thùng: Thùng lab tương tác (lab-...)
Mạng mô phỏng: SmartBin_Demo
Backend không nhận heartbeat trong ít nhất 12 giây.
Có thể do mất đường kết nối hoặc trang mô phỏng ngừng hoạt động; chưa xác định lỗi phần cứng.
Thời gian: 18/11/2026 16:00:15 (UTC+7)
```

```text
[MÔ PHỎNG WI-FI] ĐÃ KẾT NỐI LẠI WI-FI
Thùng: Thùng lab tương tác (lab-...)
Mạng mô phỏng: SmartBin_Demo
Đã nhận lại heartbeat. Thời gian từ lúc phát hiện mất kết nối: 10 giây.
Đang tiếp tục đồng bộ và gửi bù bản tin còn trong bộ đệm.
Thời gian: 18/11/2026 16:00:25 (UTC+7)
```

Các tin trên không ghép các dòng Mức đầy đo được/Cảm biến tay/Cảm biến mức rác/Lỗi khác của mẫu FULL hoặc FAULT. Tin đầy/lỗi thiết bị vẫn đi riêng theo snapshot của sự kiện.

## Ràng buộc

- Heartbeat HTTP độc lập với telemetry và đồng hồ cảm biến, gửi mỗi3giây theo giờ thực. Backend kết luận mất đường liên lạc sau12giây không nhận heartbeat mới.
- Khi ngắt Wi-Fi giả lập, frontend không gửi heartbeat, telemetry hoặc thông báo mất kết nối qua đường thùng. Backend có một vòng giám sát riêng, không bị chặn bởi thời gian chờ HTTP Telegram; tin được xếp hàng rồi worker gửi khi mạng Telegram cho phép.
- Mỗi phiên dùng số thứ tự heartbeat tăng độc lập với seq telemetry. Heartbeat cũ/trùng không gia hạn thời gian sống. Replay telemetry cũng không làm thùng được coi là vừa kết nối lại.
- Mỗi đợt chỉ tạo một job mất và một job phục hồi sau đợt mất đã báo. Tin kết nối ban đầu được tạo một lần khi đã có heartbeat và người dùng bật Telegram. Tắt Telegram/dry-run/sai người nhận không được tạo tin Wi-Fi mới gửi thật.
- Giữ chat đích theo opt-in của phiên; không tự chuyển người nhận. Mặc định vẫn xem trước. Job đã xếp hàng có thể được gửi sau khi tắt.
- Tạo phiên mới sẽ kết thúc giám sát phiên cũ cùng tài khoản, tránh phiên cũ tạo cảnh báo giả. Đăng xuất cũng kết thúc phiên. Khi tải lại/đóng trang đang online, trình duyệt cố gửi yêu cầu kết thúc; nếu trình duyệt bị tắt đột ngột hoặc request không đến backend, có thể phát hiện mất heartbeat. Mất heartbeat không chứng minh riêng radio Wi-Fi hỏng.
- Heartbeat chạy khi tạm dừng mô hình. Tab ẩn vẫn cố gửi bằng timer, nhưng trình duyệt/hệ điều hành có thể hạn chế timer hoặc ngủ máy; khi đó cũng có thể xuất hiện cảnh báo. Giữ tab hiện khi demo để kiểm tra ổn định.
- Sau restart backend, chờ heartbeat mới để tái bật giám sát; không suy diễn khoảng backend ngừng chạy thành lỗi Wi-Fi của thiết bị. Khi backend không chạy hoặc máy mất Internet thật, không thể bảo đảm nhận Telegram tức thì.
- Dashboard tách trạng thái kết nối và độ mới số đo: heartbeat còn sống không biến mức đầy cũ thành số đo mới. Lỗi cảm biến không tự suy ra Wi-Fi mất, và mất Wi-Fi không tự suy ra cảm biến hỏng.
- Đây là mô phỏng logic truyền thông HTTP, chưa phải đo RSSI/radio Wi-Fi hoặc MQTT trên ESP32 thật. Không thay cấu hình Wi-Fi thật của máy hoặc firmware.

## API/kiểm thử

POST /api/lab/sessions/{id}/connection nhận seq tăng và action heartbeat/stop. Cần manager đúng owner, kiểm tra dữ liệu nghiêm ngặt/rate-limit; không nhận chat ID từ client. Worker định kỳ dùng cùng khóa/transaction để chặn tạo job trùng khi heartbeat và timeout xảy ra đồng thời.

Kiểm thử HTTP mock và CSDL tạm: tin Wi-Fi riêng, timeout12giây, phục hồi, replay không gia hạn lease, preview/dry-run/đích gửi, owner/role, nhiều thao tác đồng thời và giám sát vẫn chạy khi Telegram worker bị giữ. Test frontend dùng controller thật/DOM mock để kiểm tra ngắt không phát HTTP, gửi bù, timer khi tạm dừng/tab ẩn và bỏ ACK đến muộn sau ngắt.

Chưa dùng browser thật để nghiệm thu trực quan. Không gửi Telegram thật trong quá trình sửa/kiểm thử.

Kết quả cuối: **93 passed**, không failed/skipped, 6 cảnh báo dependency, 27.79giây; bao gồm19 testcase Node trong pytest frontend. Cú pháp3 file JavaScript đạt node --check. Log/JUnit: artifacts/wifi-lab-tests.log và artifacts/wifi-lab-tests.xml.
