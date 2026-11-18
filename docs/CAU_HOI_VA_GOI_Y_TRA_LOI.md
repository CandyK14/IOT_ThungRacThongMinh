# Ba câu bảo vệ và gợi ý trả lời theo mã đã làm

Giữ vai trò và mức **6 điểm/câu** của báo cáo gốc. Tất cả phân bổ dưới đây là **rubric gợi ý**, không phải thang chấm chính thức của giảng viên. Câu trả lời phải tách mã đã triển khai, test mô phỏng và phần chưa đo trên thiết bị.

## Câu 2A — SV1: Hardware & Embedded Specialist, 6 điểm

**Câu hỏi tối ưu:** Hệ thống dùng ESP32, hai HC-SR04 và servo trong môi trường ẩm. Hãy kiểm tra nguồn/mức logic, đề xuất bảo vệ cảm biến; chọn lọc và hiệu chuẩn để báo 80% ổn định mà vẫn nhận tay đủ nhanh; thiết kế và kiểm thử xử lý sensor hỏng, servo kẹt/quá dòng. Trình bày sơ đồ, lịch đo, state machine và bằng chứng trước/sau, chỉ rõ phần cần thêm linh kiện.

**Rubric gợi ý:** điện/môi trường 2; xử lý số đo 2; servo và minh chứng 2 điểm.

**Gợi ý trả lời sát project:**

- Mở `docs/hardware_wiring.svg`: hai HC-SR04 5 V, hai bộ chia 10k/15k 1%, danh định 3 V, worst-case theo giả định 2,827–3,175 V. Nêu điều kiện VOH/rail và cấp ngược khi ESP32 tắt. Servo dùng nhánh nguồn theo model/tải, chung GND; chưa biết model nên không bịa dòng hoặc tụ. Hộp/đầu nối tránh nước đọng, không phủ mặt siêu âm; cảm biến chống nước cần kiểm tra vùng mù trước đổi.
- Mở `include/bin_logic.h` và `controlTask`: slot 70 ms, 4 tay +1 rác; Median 3 tay, Trimmed Mean 7 rác. Giải thích warm-up, stale, timeout 25 ms, 3 lỗi và bỏ kết luận khi đầu đo trên nắp. Dùng `d_empty>d_full`, `30/4` chỉ là mẫu; ngưỡng 80/75, 3 lần xác nhận. Chưa đo độ trễ ≤500 ms ngoài đời.
- Trình bày CLOSED/OPENING/OPEN/CLOSING/FAULT, hold 3 giây, ngưỡng tay 20/25 cm, hand invalid không đồng nghĩa người đi khỏi. Nếu có bảo vệ: GPIO34 dòng, 32/33 hành trình, 26 driver; bỏ qua startup và xác nhận quá dòng theo thời gian, chốt lỗi/cắt nguồn, reset có điều kiện. Chưa có phần cứng nên không nói đã phát hiện kẹt thật; detach không phải ngắt nguồn.
- Chạy `pytest tests/test_firmware_native.py -q -s`: test dùng chính header production cho hiệu chuẩn, lọc, rollover, trạng thái, dòng giả lập và journal. Đưa phiếu kiểm thử thiết bị chưa điền số giả và kế hoạch đo cơ khí/dòng trước khi nghiệm thu.

## Câu 2B — SV2: Networking & Edge Specialist, 6 điểm

**Câu hỏi tối ưu:** Trong vùng Wi-Fi chập chờn, hệ thống cần tự mở nắp và lưu được FULL/CLEARED. Hãy thiết kế lịch đo/truyền gắn yêu cầu độ trễ/năng lượng; chọn MQTT hoặc CoAP với schema/ACK/retry/dedup; thiết kế queue hữu hạn, phục hồi mất điện và kiểm thử gửi bù. Phân biệt lúc đo, lúc broker nhận, lúc DB lưu và lúc Telegram nhận.

**Rubric gợi ý:** năng lượng/độ trễ 2; giao thức/bản tin 2; queue/phục hồi 2 điểm.

**Gợi ý trả lời sát project:**

- Control task độc lập network, không HTTP/polling bot trên ESP32. Heartbeat 60 giây, sự kiện gửi sớm, coalesce telemetry, backoff/jitter/trần. Không deep-sleep dài vì cần nhận tay liên tục. Trình bày phương pháp tích phân điện năng toàn hệ thống; chưa có số Wh/giảm % đo được.
- ESP-MQTT của IDF hỗ trợ publish QoS 1 thật. Topic theo bin_id, credentials/ACL riêng và TLS CA/hostname sau SNTP. QoS 1 có thể trùng; unique `(bin_id,boot_id,seq)`. Boot counter NVS tăng trước task; không so UUID. PUBACK khác ACK sau commit và khác Telegram success. JSON dễ debug, payload có giới hạn; CBOR/binary chỉ cân nhắc khi đo overhead đáng kể.
- RAM 34 records được tính từ 32 sự kiện +2 telemetry, tiết kiệm so với cấp 128 không cần thiết. Hai bank NVS kiểm tra checksum/generation, giữ bank cũ khi ghi dở. ACK sai/trùng không xóa nhầm; không ACK thì retry đúng ID/nội dung. Tràn 32 sự kiện giữ cũ, đếm mất mới; công bố cửa sổ mất điện trước persist và Flash wear chưa đo.
- Demo các test MQTT TLS, credential/ACL sai, backend restart rồi gửi lại FULL cũ sau CLEARED. Lịch sử còn, trạng thái cuối không bị đảo. CoAP Confirmable/ACK + DTLS/OSCORE có thể phù hợp mạng/datagram khác; project chọn MQTT để tận dụng broker/pub-sub/retained session và đội sinh viên dễ vận hành, không triển khai hai stack song song. [MQTT 3.1.1](https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html), [CoAP RFC 7252](https://www.rfc-editor.org/rfc/rfc7252.html).

## Câu 2C — SV3: Cloud & Security Specialist, 6 điểm

**Câu hỏi tối ưu:** Mở rộng nguyên mẫu thành hệ thống quản lý 20–100 thùng. Hãy xây dựng kiến trúc ingest/CSDL/API, xử lý bản tin trùng/cũ/không biết giờ; thiết kế xác thực/phân quyền và dashboard phân biệt nguồn/chất lượng; giải CVRP có depot/sức chứa và so sánh baseline công bằng, chỉ rõ giả định bản đồ và đơn vị.

**Rubric gợi ý:** kiến trúc/CSDL 2; bảo mật/dashboard 2; VRP và đánh giá 2 điểm.

**Gợi ý trả lời sát project:**

- Vẽ ESP32→MQTT/TLS→ingest→SQLite, tách Telegram worker/AI/API. Giới thiệu bins/boots/telemetry/events/bin_state/predictions/outbox, unique constraint và transaction. Measured khác received, source bất biến theo registry; unknown không là 0; latest theo boot_no/seq bền vững, replay không làm sống lại thiết bị offline.
- Token bot ở server, password scrypt, session HttpOnly/hết hạn, manager mới tạo tuyến/registry/export. ACL tại broker và kiểm tra schema tại ingest, không chỉ ẩn nút UI. Demo viewer nhận 403 khi POST route; thử topic khác bị broker chặn. Dashboard map tọa độ/heatmap offline, heat weight %/100 chỉ trên số đo usable, có history/event/tuổi dữ liệu.
- CVRP OR-Tools, demand lít ước lượng, xe cùng đơn vị; unknown vào review hoặc giả định đầy có nhãn. Haversine không phải đường xe chạy. So nearest-neighbor cùng depot/xe/capacity; so sánh % chỉ khi cùng tập phục vụ. Trả unserved, lý do, thời gian giải; không gọi nghiệm giới hạn thời gian là tối ưu toàn cục. Trình bày smoke 30/100 thùng như dữ liệu tổng hợp.

## Trình bày AI và chia việc

SV1 chịu lịch lấy mẫu/chất lượng/hiệu chuẩn và dữ liệu thiết bị; SV2 chịu schema/identity/replay/MQTT TLS/queue và bằng chứng mất mạng; SV3 chịu DB/auth/dashboard, pipeline ML và CVRP. Cả ba cùng hiểu hợp đồng dữ liệu và chạy integration test, không chia theo kiểu mỗi người chỉ biết một màn hình.

Demo AI: nêu **mức đầy sau 60 phút**, 9 feature chỉ từ quá khứ, RF so persistence/tuyến tính trên cùng test, purge/embargo thời gian. Đưa MAE/RMSE đơn vị điểm %, TP/FP/FN/TN và nguồn simulated; không nói “95% chính xác”. IF trong bộ này kém rule về báo nhầm, nên trình bày trung thực. Không gọi median/hysteresis là ML; không gọi baseline fallback là số AI đã được xác minh. Model từ simulated không suy luận RF cho real.

Kịch bản bảo vệ ngắn: đăng nhập → lọc nguồn mô phỏng → chọn thùng xem quality/giờ → xem dự báo có nhãn → tạo tuyến, đối chiếu baseline → chạy test gửi bù/ACL → mở sơ đồ điện và danh sách chưa đo. Chuẩn bị firmware build log, JUnit XML, metric JSON và smoke JSON; chưa có browser host trong môi trường triển khai nên nhóm cần kiểm tra thao tác UI trên laptop trước buổi bảo vệ.
