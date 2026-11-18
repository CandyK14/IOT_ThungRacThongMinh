# Kết quả nghiệm thu phần mềm — 17/11/2026

Đây là các check **thực sự đã chạy** trong workspace Windows. Không có thao tác upload ESP32, di chuyển servo, gửi Telegram thật, public deploy, commit hoặc push. Tài liệu yêu cầu/báo cáo ban đầu được giữ lại; `src/config.h` không bị sửa/in ra log.

## Các check đã qua

| Check | Lệnh | Kết quả |
|---|---|---|
| Firmware mặc định, mã MQTT/TLS có liên kết | `platformio run` với Core 6.2.0 | **SUCCESS** |
| Test C++ production logic, backend/API, Telegram, ML, routing, TLS | `.venv\Scripts\python.exe -m pytest -q --junitxml=artifacts/tests.xml` | **42 passed**, 6 warnings dependency |
| Smoke API/demo/scale | `.venv\Scripts\python.exe -m tools.smoke_demo` | Qua: 30 thùng/852 bản tin; solver case 100 điểm |
| Cú pháp JS | `node --check dashboard/app.js` | Qua, exit 0 |
| Dependency tương thích | `.venv\Scripts\python.exe -m pip check` | `No broken requirements found` |
| Pipeline RF/IF và tái lập | `backend.cli train`, train hai lần trong test | Qua; cùng input/seed/version cho cùng metric |
| Seed + mốc giờ cố định | Sinh lại dữ liệu trong bộ nhớ, chuẩn hóa newline Windows | Nội dung và SHA-256 khớp dataset gốc |
| Cấu trúc Wokwi | Python JSON parse sau cập nhật | JSON hợp lệ; chưa chạy simulator |

JUnit, log build, log test, metric và smoke được lưu trong [results/](results/). File runtime đầy đủ trong `artifacts/` được ignore; bản bằng chứng bàn giao nằm trong `docs/results/`.

Các warnings đã thấy: Starlette khuyến nghị `httpx2` cho test client; ba cảnh báo SWIG của OR-Tools; AMQTT cảnh báo tên cấu hình ACL test đang deprecated. Chúng không làm check thất bại. Giữ phiên bản đã chạy trong lock, không sửa dependency hàng loạt để che warning.

## Firmware và bộ nhớ

- Platform Espressif32 **7.0.1**; Arduino-ESP32 **2.0.17**; ESP32Servo **3.2.1**; ArduinoJson **7.4.3**; DOIT ESP32 DevKit V1, xtensa toolchain 8.4.0.
- RAM tĩnh: **62.652 / 327.680 byte**, khoảng **19,1%**.
- Flash chương trình: **935.009 / 1.310.720 byte**, khoảng **71,3%** phân vùng chương trình.
- Host C++ và kích thước symbol ELF phù hợp: record **104 byte**, outbox34 **3.544 byte**, journal32 +header **3.344 byte**. Ba buffer journal static =10.032 byte. Queue control 16×104=1.664 byte và ACK8×32=256 byte **chưa cộng overhead FreeRTOS**.
- Stack được yêu cầu: control6.144, network12.288 và MQTT6.144 byte; đây là cấp phát cấu hình, chưa phải high-water đo trên thiết bị. TLS/JSON/Wi-Fi/MQTT còn dùng heap động. Có gate bộ đệm QoS SDK 4096 byte theo số SDK báo; không khẳng định tổng heap chỉ bằng con số đó.
- Mã có log free heap và stack high-water, nhưng chưa có môi trường ESP32/Wokwi để thu các số này. Build thành công không chứng minh đủ heap mọi tình huống hoặc đạt độ trễ ≤500 ms.

## Logic quan trọng đã có bằng chứng

**Firmware host:** dùng chính `include/bin_logic.h` và `event_queue.h`, không viết lại thuật toán trong Python. Ca thử bao gồm mốc hiệu chuẩn0/80/100, cấu hình sai/NAN/vùng mù, trimmed outlier, thiếu/stale window, rollover millis, hysteresis xác nhận, hold/reverse/hand invalid/fault/reset, startup overcurrent transient và quá dòng kéo dài/travel timeout. Có regression sensor fill lỗi rồi đầu đo bị pause khi nắp mở: không được thông báo RECOVERED trước khi có lại cửa sổ hợp lệ.

**Queue:** FULL→CLEARED được giữ FIFO; telemetry coalesce không sửa bản đang đợi ACK; khôi phục cùng ID qua journal; lỗi bit/ghi dở loại bank hỏng; overflow32 giữ cũ/tăng dropped; ACK trùng không xóa event tiếp theo. Đây là test dữ liệu/codec host, không phải thử cắt nguồn Flash thật.

**Backend:** schema/range/oversize/rate/source/topic; unknown/stale không thành0; cùng ID khác nội dung bị từ chối; nhiều boot và replay ngẫu nhiên không đổi trạng thái mới nhất; 20 ingest trùng đồng thời chỉ một bản ghi/job; backstop FULL không báo lại khi event FULL của trạng thái đó tới sau. Role/session/logout/Origin và lỗi validation không echo mật khẩu. Ngưỡng custom được mang qua schema/DB.

**TLS integration:** broker AMQTT dùng CA, credential và port loopback tạm. Simulator publish QoS1→ingest→SQLite commit→application ACK. Cố ý bỏ ACK đầu tiên sau commit, simulator retry cùng ID và DB không nhân đôi. Restart backend rồi replay FULL cũ sau CLEARED: trạng thái cuối vẫn CLEARED, lịch sử/job không trùng. Sai mật khẩu bị broker từ chối; private CA không được system trust chấp nhận; ACL chặn topic thùng khác trước ingest. AI không đủ lịch sử trả unavailable, routing vẫn chạy và outbox dry-run.

**Telegram:** mock HTTP200/ok=false, 429/retry_after, timeout, outbox phục hồi, allowlist chat/user, command dedup, shutdown giữ job chưa gửi và dry-run không gọi mạng. Log HTTP verbose được kiểm tra không chứa token URL.

**AI:** causal feature, purge/embargo, cùng baseline/test, artifact/metric repeatable; no model/history/stale/fault; chặn lấy lịch sử boot cũ dù đồng hồ boot đó mới hơn; lỗi Isolation Forest sau RF phải trả lại **giá trị baseline thật** và nhãn baseline, không chỉ đổi tên phương pháp. Test routing bỏ đóng góp dự báo bị đánh dấu anomaly nhưng không vô hiệu số đo thực.

**VRP:** rỗng/một điểm/nhiều xe/vượt sức chứa, review/conservative unknown, prediction expiry/source/anomaly, capacity/depot cho cả solver và baseline, so % chỉ cùng tập phục vụ.

## AI và demo đã chạy

Dữ liệu **mô phỏng**, seed42, 12 thùng/14 ngày/bước5phút/mốc cuối cố định; train26.826/validation8.804/test8.751 cặp. MAE: persistence9,007; tuyến tính8,537; RF5,067 điểm phần trăm. RMSE tương ứng20,230 /21,394 /12,639. IF báo nhầm3,883% trên normal test, rule2,196%; chưa có chứng cứ IF tốt hơn rule. Không có “95% chính xác” và không quy đổi thành ETA.

Smoke30 thùng có28 prediction available ở snapshot đã thử; số còn lại không bị ép thành dự báo. JSON chuẩn hóa lớn nhất quan sát trong bộ này **462 byte**, thấp hơn giới hạn2048; **chưa đo JSON phát từ ESP32 thực tế**.

Snapshot route30:16.997m so baseline17.907m, cùng tập phục vụ, không bỏ điểm. Case100 điểm đều90%, 10 xe×1500lít, limit3giây:166.391m so baseline178.409m, cùng tập phục vụ, không bỏ điểm. Toàn bộ là khoảng cách địa lý tổng hợp; nghiệm có thể thay đổi theo thời gian tìm kiếm/máy. Không khẳng định đường xe chạy thực tế hoặc tối ưu toàn cục.

## Chưa chạy / chưa thể xác nhận

| Hạng mục | Lý do / bước tiếp theo |
|---|---|
| Kiểm tra trực quan desktop/mobile | CUA trả `browser access host unavailable`, native pipe không tồn tại, inventory apps/browsers rỗng. Chỉ xác minh HTTP/static assets/cú pháp; nhóm cần mở browser, đăng nhập, lọc/chọn/route và kiểm tra responsive |
| Wokwi runtime | Không có runtime/session khả dụng; sơ đồ mới chỉ parse JSON và đối chiếu tài liệu |
| Mosquitto thực tế | Không có executable cài sẵn; config mẫu đã đối chiếu man page, integration thay bằng AMQTT TLS có auth/ACL |
| Firmware MQTT/TLS/SNTP và NVS trên ESP32 | Không có thiết bị chạy; cần CA/credential/broker nhóm cấu hình và thử cold boot/reset/lost ACK/cắt điện thật |
| Nguồn/ECHO/servo/chống kẹp | Chưa biết model servo, dòng/nguồn/BOM thật và chưa có dụng cụ/linh kiện bảo vệ; xem PHAN_CUNG.md |
| Độ trễ≤500ms, heap/stack runtime, điện năng, 24h | Chưa có số đo thiết bị; đã có cách log và phiếu nghiệm thu |
| Telegram thật | Chủ động không gửi; nhóm tự cấu hình/cho phép bằng dry-run=0 sau kiểm tra |
| AI trên dữ liệu thật, holdout theo thùng/cycle | Chưa có dữ liệu thật hoặc đánh giá độc lập đó; kết quả hiện tại chỉ simulated |
| Profile smartphone/LAN/HTTPS | CSS có responsive nhưng chưa visual test; server mặc định loopback/host allowlist, cần cấu hình có chủ đích trước mở LAN |

Phần mềm và tài liệu đã được triển khai theo phạm vi ghi ở ma trận. **Chưa kết luận nghiệm thu toàn hệ thống vật lý**, chưa chứng minh an toàn cơ khí/điện hay chất lượng dự báo thực tế. Hướng TinyML/camera/chatbot/đường bộ được giữ riêng như mở rộng.
