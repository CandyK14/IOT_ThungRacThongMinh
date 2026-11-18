# Giao diện mô phỏng tương tác — 18/11/2026

## Chạy và thao tác

Khởi động lại backend để nạp API lab mới, sau đó tải lại web bằng Ctrl+F5:

```powershell
cd D:\S\IOT\Nhom10_DA_IoT_update
$env:MQTT_ENABLED = "0"
$env:TELEGRAM_DRY_RUN = "1"
.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Đăng nhập tài khoản hiện có tại http://127.0.0.1:8000. Mục **Phòng thử nghiệm tương tác** xuất hiện phía trên tổng quan. Không cần chạy Wokwi để dùng màn hình này; đây là mô hình logic trong trình duyệt.

- **Chạy chu kỳ tự động:** khoảng25giây ở tốc độ1×, đi qua đưa tay → mở nắp → bỏ rác → rút tay → đóng nắp → FULL → mở để thu gom → đóng/đo lại → CLEARED. Có thể dừng để tiếp tục thao tác bằng tay.
- **Đưa tay lại gần / Rút tay ra xa:** khoảng cách đặt10/100cm. Slider cho phép thử ngưỡng20cm và25cm. Servo được minh họa chuyển động0–90°; nắp giữ mở3giây sau lần nhận tay cuối.
- **Bỏ rác +8%:** chỉ có hiệu lực khi nắp đã mở và mô hình không ở trạng thái lỗi. Mức rác vật lý đặt và mức đo được hiển thị riêng; bộ lọc tạo độ trễ có chủ đích.
- **Thu gom:** mô hình tự mở, lấy rác ra, đóng nắp rồi chờ số đo xác nhận. Khi thu gom thùng chưa từng đầy, không giả tạo FULL/CLEARED.
- **Slider mức rác:** dùng đặt điều kiện thử cảm biến; không phải thao tác đo từ phần cứng. 90% để thử FULL,77% kiểm tra giữ latch,70% kiểm tra CLEARED. Đợi vài giây và giữ nắp đóng để đo mức đầy.
- **Tạm dừng:** dừng đồng hồ mô hình. Mô hình cũng tạm dừng khi tab bị ẩn, không chạy bù một chu kỳ cực nhanh khi quay lại.

## Mô hình và nhãn chất lượng

`dashboard/simulation-core.js` là mô hình hành vi JavaScript, không chạy firmware ESP32 và không là mô phỏng lực/dòng/âm học. Slot70ms, 4 mẫu tay rồi1 mẫu rác; Median3 tay, TrimmedMean7 mức rác, xác nhận3 mẫu, hysteresis80/75. Công thức hiệu chuẩn30/4cm. Chờ ổn định1giây sau đóng nắp; khi nắp mở không kết luận số đo đầy. Thời gian giao diện không chứng minh độ trễ hoặc an toàn trên thiết bị thật.

Mặt cắt thùng cho thấy mức rác **đặt để mô phỏng**; chỉ số **Mức đầy đo được** lấy từ cửa sổ lọc. Chưa đủ mẫu/lỗi/đang mở nắp hiển thị dấu —, không đổi thành0%. LED và trạng thái được tính từ logic. Nhật ký FULL/CLEARED xuất hiện theo trạng thái đo, không được nút hoạt ảnh ép tạo. Thông báo cạnh thùng là **bản xem trước**, không xác nhận gửi Telegram.

Trong **Thử lỗi & kết nối dashboard**, có lỗi cảm biến tay, lỗi mức rác và nhiễu. Cảm biến tay lỗi làm chốt FAULT; rút tay ra xa, tắt lỗi, đợi mẫu hợp lệ rồi bấm **Xác nhận phục hồi lỗi nắp**. Lỗi mức rác không được coi là thùng rỗng hoặc tự phục hồi trong khi phép đo còn tạm dừng.

## Đồng bộ tùy chọn

Người quản lý có thể bấm **Đồng bộ với dashboard**. Người xem vẫn thử mô hình trên máy, không được ghi dữ liệu lab vào server.

- Backend tạo mã thùng `lab-<hash tài khoản>` nguồn simulated, boot_no tăng trong transaction và boot_id riêng cho mỗi phiên.
- Session API gắn chủ sở hữu. Bản tin khác owner/ID/boot/source bị từ chối. Không nhận dữ liệu real và không ghi đè registry real.
- Mỗi bản tin có ID bất biến khi retry. Queue RAM giới hạn32, telemetry được gộp, giữ telemetry đang chờ ACK. FULL/CLEARED được giữ theo thứ tự trong khả năng bộ đệm.
- Bật **Ngắt kết nối mô phỏng**, chạy chu kỳ rồi nối lại để xem gửi bù. Đây là ngắt đường đồng bộ HTTP của lab, không phải cắt Wi-Fi thật hoặc phép đo mạng ESP32.
- ACK trả sau DB commit; gửi lại không thêm event/job trùng. Phiên cũ không ghi đè state từ boot mới.
- Mặc định backend tắt notifications cho lab và chặn cảnh báo sớm AI. Có thể cấu hình bot rồi bật **Gửi cảnh báo Telegram cho phiên này** để gửi các sự kiện mới. Xem [hướng dẫn Telegram](HUONG_DAN_TELEGRAM_WEB.md). Không gửi lại sự kiện trước ranh giới lúc bật; tắt không hủy job đã xếp hàng.
- Có nút **Xem lịch sử thùng lab** để đối chiếu dữ liệu đã lưu trong phần dashboard cũ.

Queue là RAM của trang, chưa bền qua reload/đóng trang. Những bản đã ACK vẫn nằm trong SQLite; bản chưa ACK có thể mất khi đóng trang. Không dùng mô hình này thay cho kiểm thử NVS/MQTT của firmware. Sau đăng xuất/đổi tài khoản, mô hình và queue trang được làm mới; phản hồi HTTP cũ không được gán vào tài khoản/phiên mới.

Đồng bộ dùng API HTTP cùng origin, không tuyên bố đã đi qua MQTT hoặc Wokwi. Không đưa physicalFill ẩn của mô hình vào payload ML. Dự báo vẫn cần lịch sử đúng điều kiện; chu kỳ25giây không tạo bằng chứng dự báo60phút đã được xác thực.

## API và file

| Thành phần | Vai trò |
|---|---|
| dashboard/index.html, simulation.css | Mặt cắt thùng SVG, bố cục responsive, điều khiển có label |
| dashboard/simulation-core.js | State machine, bộ lọc, ngưỡng, kịch bản và queue |
| dashboard/simulation.js | Hoạt ảnh, trạng thái UI, cảnh báo xem trước và sync/retry |
| backend/lab.py | Session owner, mã lab riêng, boot counter, source guard |
| POST /api/lab/sessions | Manager tạo phiên nguồn simulated, thông báo preview_only |
| POST /api/lab/sessions/{id}/notifications | Manager đúng owner bật/tắt gửi mới; yêu cầu backend Telegram thật sẵn sàng |
| POST /api/lab/sessions/{id}/messages | Manager đúng owner lưu snapshot/sự kiện đã xác thực |
| backend/db.py | Ingest có tùy chọn notifications nội bộ; default của luồng cũ được giữ |
| backend/ml.py | Không tạo job cảnh báo sớm cho lab |

## Bằng chứng và giới hạn kiểm tra

Đã chạy **53 test pytest**, không failed/skipped; gồm12 testcase Node cho mô hình và controller thật với DOM mock dùng ID từ HTML thật. Kiểm tra được cả chu kỳ, ràng buộc bỏ rác, unknown/fault, giữ latch, khôi phục, ngắt kết nối/gửi bù, retry cùng payload, viewer chỉ xem, tab ẩn tạm dừng và cách ly phản hồi cũ sau login. Các test API xác minh role/owner/source, mặc định không Telegram ngay cả cấu hình global bật, không thay registry real và ordering nhiều boot. Cú pháp ba file JS đã qua node --check.

Log/JUnit mới nhất: artifacts/telegram-lab-tests.log và artifacts/telegram-lab-tests.xml (53 passed, 6 cảnh báo dependency, 28.97giây). Bản frontend trước: artifacts/frontend-lab-tests.log và artifacts/frontend-lab-tests.xml. Test API dùng CSDL tạm, không sửa dữ liệu thiết bị thật. Không cài thêm thư viện frontend, không cần Node để chạy dashboard; Node18+ dùng cho test khi phát triển.

Chưa có công cụ điều khiển trình duyệt trong phiên làm việc này nên **chưa kiểm tra screenshot/responsive bằng browser thật**. Đã xác minh HTTP200 của trang/asset và toàn bộ logic/API. Nhóm cần mở web trên laptop/điện thoại để nghiệm thu trực quan. Phần mở nắp là minh họa, chưa đo lực/chống kẹp hoặc dòng servo.

Bổ sung Telegram: test mock xác minh opt-in/cutoff, không chuyển nhầm người nhận, API owner/role/validation, gửi FULL/CLEARED qua worker và không tạo job trùng; công cụ setup chỉ đọc API. Bằng chứng mới: artifacts/telegram-lab-tests.log và artifacts/telegram-lab-tests.xml.

Cập nhật LED và nội dung tin: [LED mức đầy và Telegram chi tiết](LED_VA_THONG_BAO_THIET_BI.md). Màn hình dùng số đo đã lọc, hiển thị chờ/lỗi khi chưa có giá trị hợp lệ. Schema thêm fault_codes tùy chọn; bản tin cũ vẫn được nhận với nhãn chưa có chẩn đoán riêng.

Bằng chứng cập nhật LED/Telegram: **83 test pytest đạt**, gồm16 testcase Node trong test frontend; không failed/skipped, 6 cảnh báo dependency. Xem artifacts/led-notification-tests.log và artifacts/led-notification-tests.xml. Các số53/12 phía trên ghi nhận mốc kiểm tra trước khi thêm LED.

Wi-Fi mô phỏng: bảng SSID giả lập, nút ngắt/kết nối lại và heartbeat tách khỏi đồng hồ cảm biến. Backend báo mất sau12giây và dùng mẫu Telegram riêng. Xem [quy tắc và cách thử](WIFI_MO_PHONG.md).

Mốc Wi-Fi mới nhất: **93 test pytest đạt**, gồm19 testcase Node trong kiểm thử frontend; không failed/skipped. Log/JUnit: artifacts/wifi-lab-tests.log và artifacts/wifi-lab-tests.xml.
