# LED mức đầy trên thùng web và Telegram chi tiết — 18/11/2026

## Sử dụng

1. Dừng backend bằng Ctrl+C, chạy lại trong PowerShell có cấu hình Telegram của bạn. Giữ TELEGRAM_DRY_RUN=0 nếu muốn nhận tin thật. Chỉ chạy một backend.
2. Mở web, Ctrl+F5. Trên thân thùng mô phỏng có màn LED số: mức đầy đo được, trạng thái đo và lỗi cảm biến đã xác nhận.
3. Muốn thử tin: Đồng bộ với dashboard → bật Gửi cảnh báo Telegram cho phiên này → chạy chu kỳ mới. Lựa chọn gửi được làm mới về xem trước khi reload.
4. Thử lỗi trong Thử lỗi & kết nối dashboard: bật lỗi mức rác, chờ xác nhận; bật thêm lỗi tay để thấy cả hai; tắt lỗi tay, rút tay xa, chờ mẫu rồi xác nhận phục hồi nắp. Lỗi mức rác vẫn phải còn cho đến khi được phục hồi và có đủ mẫu mới.

## Ràng buộc LED

- LED đọc cùng snapshot.fill với chỉ số Mức đầy đo được, sau lọc/hiệu chuẩn; không đọc trực tiếp physicalFill từ thanh kéo.
- Khi không có số đo hợp lệ, LED hiện —, không thay bằng0 hoặc giữ một phần trăm cũ như số đo hiện tại. Khi nắp mở/chờ ổn định, hiện CHỜ ĐÓNG NẮP; đang gom mẫu hiện CHỜ ĐO.
- Khi đủ xác nhận đầy, hiện ĐẦY · CẦN THU GOM. Lỗi thiết bị được ưu tiên hiển thị; trạng thái FULL vẫn được giữ độc lập, không giả xóa cảnh báo khi mất số đo.
- Cảm biến mức rác mất dữ liệu sẽ xóa cửa sổ mẫu; phục hồi phải gom đủ7 mẫu mới. Không lẫn mẫu trước lỗi để tuyên bố đo hợp lệ sớm.
- Đây là màn hiển thị trên mô phỏng web. Không thay chân GPIO, firmware hoặc thêm màn hình vật lý vào mạch.

## Mẫu tin

```text
[MÔ PHỎNG] THÙNG ĐÃ ĐẦY — CẦN THU GOM (FULL)
Thùng: Thùng lab tương tác (lab-...)
Mức đầy đo được: 88.0%
Cảm biến tay: Chưa ghi nhận lỗi
Cảm biến mức rác: Đang có số đo hợp lệ
Nắp: Đã đóng
Lỗi khác: Chưa ghi nhận
Ngưỡng đầy: 80% · Cần bố trí thu gom.
Giờ đo: 18/11/2026 15:13:09 (UTC+7)
Thông tin tại thời điểm đo.
```

FAULT cho biết cảm biến tay/mức rác nào được chẩn đoán lỗi và mức đầy chưa biết. Nếu bộ lỗi thay đổi (thêm lỗi hoặc chỉ phục hồi một phần), tạo thông báo FAULT mới với danh sách lỗi còn lại; chỉ phát RECOVERED khi không còn lỗi đã xác nhận. Thông báo không hứa thiết bị sẽ không phát sinh lỗi mới.

Tin backstop sau3 bản đo cao liên tục cũng dùng cùng mẫu. Tin CLEARED ghi mức đo thấp và xóa cảnh báo đầy; số đo thấp không tự chứng minh có người đến thu gom. Tin cũ đã lưu trong outbox không được viết lại hoặc gửi lại tự động. Chỉ tin tạo mới dùng mẫu mới.

Giờ đo đổi sang UTC+7. Chỉ gắn nhãn gửi bù/lịch sử khi có bằng chứng: giờ đo chậm ít nhất60giây, bản tin thuộc thứ tự/boot cũ, hoặc số liệu offline/replay tương ứng. Số liệu trong tin là snapshot lúc đo; không đồng nghĩa trạng thái mới nhất lúc điện thoại nhận.

## Chẩn đoán tương thích

Schema thêm trường tùy chọn fault_codes với mã HAND_SENSOR, FILL_SENSOR, LID_CONTROL, STORAGE, POWER. Web chỉ phát HAND_SENSOR/FILL_SENSOR sau khi logic xác nhận; không tự tạo lỗi nguồn/bộ nhớ. Nếu bản tin có các mã lỗi khác được hỗ trợ thì tin sẽ nêu tên tương ứng. Bộ đếm dropped_records>0 được ghi rõ là số bản đã bỏ tích lũy, không khẳng định lỗi còn đang xảy ra.

fault_codes=null hoặc thiếu nghĩa là chưa có chẩn đoán riêng, không phải thiết bị đã được kiểm tra và hoàn toàn bình thường. Với firmware/bản tin cũ, quality=fault được ghi “Số đo lỗi; chưa xác định nguyên nhân”, lid_state=FAULT ghi “Nắp chốt lỗi; chưa xác định nguyên nhân”; không suy diễn chắc chắn cảm biến tay hỏng. Không tự suy ra servo hỏng, nguồn yếu hoặc mất mạng chỉ từ việc nắp chốt lỗi.

Payload cũ được chuẩn hóa trường mặc định khi kiểm tra bản tin trùng, giữ khả năng replay/ACK sau nâng cấp. Không thay schema SQLite hoặc dữ liệu lịch sử. Giữ nguyên opt-in Telegram, dedup job, điều khiển nắp, FULL/CLEARED80/75 và quy tắc chất lượng dữ liệu.

Kiểm thử dùng CSDL tạm/HTTP mock, không gửi tin Telegram thật trong lúc sửa. Chưa có công cụ browser nên chưa nghiệm thu trực quan/responsive; kiểm tra controller bằng DOM mock, ID từ HTML thật và asset HTTP.

Kết quả lần kiểm tra này: **83 passed**, không failed/skipped, 6 cảnh báo dependency, 25.96giây. Có16 testcase Node được chạy trong pytest để kiểm tra mô hình/controller (DOM mock), bao gồm LED và lỗi đồng thời. Cú pháp3 file JavaScript đạt node --check. Bằng chứng: artifacts/led-notification-tests.log và artifacts/led-notification-tests.xml.
