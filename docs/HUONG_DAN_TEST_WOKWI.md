# Thử tự mở nắp và báo đầy bằng Wokwi

Ngày bổ sung: 18/11/2026. Chỉ mô phỏng, không cần cắm ESP32. Firmware đã có log chuyển trạng thái và sự kiện cục bộ; đây là hướng dẫn thao tác và kết quả mong đợi, chưa phải bằng chứng đã chạy Wokwi runtime.

## Mở mô phỏng

1. Trong VS Code, mở đúng thư mục `D:\S\IOT\Nhom10_DA_IoT_update`, có `platformio.ini`, `wokwi.toml`, `diagram.json`.
2. Extension Wokwi và PlatformIO đã được tìm thấy trên máy. Nếu Wokwi yêu cầu license, nhấn F1 → `Wokwi: Request a new License` rồi làm theo hướng dẫn chính thức trên website; không gửi license/token vào chat.
3. Firmware đã được build. Nếu sau này sửa mã, build lại bằng terminal PowerShell tại project:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
```

4. Nhấn F1, chọn `Wokwi: Start Simulator`. Chỉ khởi động mô phỏng, không chọn Upload. Mở phần Serial Monitor của Wokwi để xem log.

Nguồn thao tác: [Wokwi PlatformIO](https://docs.wokwi.com/vscode/platformio), [khởi tạo/license](https://docs.wokwi.com/vscode/getting-started). Firmware ELF là định dạng được Wokwi hỗ trợ cho ESP32 theo [project config](https://docs.wokwi.com/vscode/project-config).

## Thử cảm biến tay và servo

Cảm biến bên trái là `ultrasonic_lid`, giá trị ban đầu 100 cm. Bấm trực tiếp vào hình cảm biến để đổi khoảng cách bằng slider. [Wokwi HC-SR04](https://docs.wokwi.com/parts/wokwi-hc-sr04).

| Thao tác | Kết quả mong đợi |
|---|---|
| Để tay 100 cm | Servo đóng, lệnh góc 0° |
| Đổi xuống 10 cm | Servo mở tới lệnh góc 90°, log CLOSED → OPENING → OPEN |
| Giữ 10 cm | Nắp tiếp tục mở |
| Khi đã mở, đổi lên 22 cm | Nắp vẫn mở vì ngưỡng giữ là dưới25cm |
| Đổi về100cm | Sau khoảng3giây giữ mở và thời gian chuyển động, nắp đóng; log OPEN → CLOSING → CLOSED |

Thời gian ở đây là thời gian mô phỏng; máy chạy mô phỏng chậm có thể làm thời gian ngoài đời dài hơn. Bộ lọc tay cần đủ mẫu, không kết luận lỗi từ một lần đổi slider quá nhanh. Chưa đo mục tiêu phản ứng500ms trên thiết bị thật.

## Thử mức đầy và chống báo lặp

Cảm biến bên phải là `ultrasonic_fill`, ban đầu30cm. Trước mỗi bước thử, giữ cảm biến tay100cm và đợi nắp đóng. Mặc định sensor rác được coi là gắn trên nắp, nên phép đo bị tạm dừng khi nắp mở và cần thời gian ổn định sau đóng.

Mốc hiệu chuẩn mẫu empty30cm/full4cm; công thức `100×(30-distance)/(30-4)`. Không dùng công thức `100×(30-distance)/30`. Các con số dưới đây xấp xỉ vì cách mô phỏng/xử lý xung và lọc.

| Khoảng cách rác | Kết quả mong đợi sau khi ổn định |
|---|---|
| 30 cm | Gần0%, LED xanh |
| 8 cm | Khoảng85%, LED đỏ và một log FULL |
| Tiếp tục giữ8cm | Duy trì đỏ, không tạo FULL liên tục |
| Từ8 đổi sang10cm | Khoảng77%, vẫn giữ đỏ vì chưa xuống ngưỡng xóa75% |
| Đổi lên12cm | Khoảng69%, chuyển xanh và một log CLEARED |
| Sau đó đổi lại8cm | Một đợt đầy mới, được tạo FULL mới |

Giữ mỗi bước khoảng5giây mô phỏng; sau khi vừa đóng nắp có thể cần chờ thêm. Firmware dùng TrimmedMean7 và3 lần xác nhận, nên LED/sự kiện không đổi tức thì theo một mẫu.

Log mong đợi có dạng:

```text
[Nap] CLOSED -> OPENING
[Nap] OPENING -> OPEN
[Nap] OPEN -> CLOSING
[Nap] CLOSING -> CLOSED
[Su kien cuc bo] FULL | fill=...% | sensor=valid
[Su kien cuc bo] CLEARED | fill=...% | sensor=valid
```

`Su kien cuc bo` xác nhận firmware đã phát hiện sự kiện. Nó không xác nhận backend hoặc Telegram đã nhận. Nếu hai LED cùng sáng kéo dài, xem log FAULT/unknown và trạng thái nắp trước khi tiếp tục; không coi đây là đầy hợp lệ.

## Web và thông báo Telegram

Bản cấu hình hiện tại chưa có `src/mqtt_config.h`, và CA MQTT trong mẫu đang trống. Vì vậy thử local bằng servo, LED và Serial được; firmware chưa gửi sự kiện Wokwi về backend. Dòng báo CA trống trong Serial là thông tin cấu hình.

Dashboard đang nhận các thùng `sim-xxx` từ simulator Python; firmware Wokwi dùng mã mẫu `bin-001`. Để số đo Wokwi xuất hiện trên web/Telegram, cần cấu hình toàn bộ đường đi:

```text
Wokwi ESP32 → MQTT/TLS → broker → backend → DB/outbox → Telegram
```

Cần broker có đường truy cập được từ Wokwi, CA khớp hostname, credential/ACL riêng và cấu hình backend tương ứng. Trước khi nối mạng phải bổ sung profile firmware Wokwi phát source=simulated cùng mã thùng mô phỏng riêng, rồi đăng ký cùng nguồn ở backend. Firmware mặc định hiện phát source=real cho thiết bị thật; không dùng nguyên profile đó để đưa số đo Wokwi lên web như dữ liệu thật. Vì profile mạng Wokwi này chưa được cấu hình, hướng dẫn hiện tại chỉ nghiệm thu cục bộ. Không bật Telegram thật để bù cho MQTT chưa cấu hình, và không dùng setInsecure để vượt lỗi chứng chỉ.

Đối với lần thử này, giữ Telegram dry-run. Bộ test đường MQTT/TLS/outbox/Telegram mock đã có:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_mqtt_integration.py tests/test_telegram.py -q
```

Muốn nhận Telegram thật thì nhóm phải chủ động cấu hình token/chat/user allowlist tại backend và bật `TELEGRAM_DRY_RUN=0` sau khi đã nối broker, kiểm tra nhãn môi trường và nguồn dữ liệu. Không đặt token mới vào firmware. Xem README và BAO_MAT_VA_VAN_HANH.md.
