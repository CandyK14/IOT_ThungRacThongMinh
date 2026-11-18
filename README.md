# Thùng rác thông minh · Vòng Xanh

ESP32 tự điều khiển nắp, đo mức đầy và lưu sự kiện; backend nhận MQTT/TLS, lưu SQLite, cảnh báo Telegram, dự báo 60 phút và minh họa tuyến thu gom CVRP. Dashboard tiếng Việt chạy cùng FastAPI, không cần Node, Docker, dịch vụ bản đồ hoặc tài khoản AI trả phí.

**Phạm vi đã xác minh:** build firmware, test C++ trên máy, backend/API, Telegram mock, AI trên dữ liệu mô phỏng, VRP và MQTT/TLS với broker kiểm thử AMQTT. Chưa nạp ESP32, chạy Wokwi, gửi Telegram thật, đo điện/cơ khí hoặc kiểm tra giao diện trong trình duyệt. Không dùng phần mềm này để khẳng định có cơ cấu chống kẹp hay bảo vệ điện đã được nghiệm thu.

## 1. Chạy demo local trên Windows

Dùng PowerShell tại thư mục project. Bộ phiên bản đã thử là **Python 3.14** và [requirements-lock.txt](requirements-lock.txt). Python của PlatformIO 3.11 là môi trường riêng, không dùng để cài bộ thư viện Python 3.14 này. Cần Internet một lần để tải dependency; sau đó dashboard và demo CSDL hoạt động ngoại tuyến.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe -m backend.cli user admin --role manager
```

Nhập mật khẩu ít nhất 12 ký tự khi được hỏi. Lệnh tạo user từ chối tên trùng, không tự ghi đè mật khẩu. Có thể tạo tài khoản chỉ xem:

```powershell
.venv\Scripts\python.exe -m backend.cli user viewer --role viewer
```

Terminal 1: nạp 30 thùng **mô phỏng** với lịch sử 2,4 giờ, rồi cập nhật mỗi 60 giây:

```powershell
.venv\Scripts\python.exe -m backend.cli demo --bins 30 --watch
```

Terminal 2: khởi động server, mở **http://127.0.0.1:8000** rồi đăng nhập:

```powershell
$env:TELEGRAM_DRY_RUN = "1"
.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Chọn thùng để xem lịch sử/sự kiện, lọc nguồn/trạng thái, bật lớp mức đầy và bấm **Lập tuyến** với tài khoản quản lý. Sau khoảng 30 giây worker tạo dự báo; chưa có model thì dùng baseline tuyến tính có nhãn nếu đủ lịch sử. Không có baseline hợp lệ thì hiện unavailable.

`demo` không có `--watch` chỉ nạp một lần: sau 6 phút không cập nhật, thùng chuyển offline/stale đúng thiết kế. Có thể dùng `--bins 100`. Mỗi lần chạy tạo boot mới có số tăng dần, giữ lịch sử cũ. **Không chạy hai tiến trình demo cùng CSDL.** Profile này dùng trực tiếp cùng hàm ingest với MQTT và không tuyên bố đã đi qua broker. Luồng MQTT thật có hướng dẫn riêng ở mục 4.

Biến môi trường tham khảo: [.env.example](.env.example). Ứng dụng **không tự nạp `.env`**; đặt `$env:TEN_BIEN=...` trong PowerShell. Mặc định MQTT tắt, Telegram dry-run, không có tài khoản/mật khẩu mặc định. `BIN_DB` chọn CSDL khác; mọi lệnh phải dùng cùng biến này. Giao diện chỉ cho host loopback; cấu hình hiện tại phục vụ demo trên laptop. Muốn mở qua điện thoại/LAN cần cấu hình host allowlist, HTTPS/reverse proxy và `COOKIE_SECURE=1` có chủ đích; chưa có profile triển khai công khai.

## 2. Huấn luyện, đánh giá và suy luận AI

```powershell
.venv\Scripts\python.exe -m simulator.generate --bins 12 --days 14 --seed 42 --output data\training-seed42.jsonl
.venv\Scripts\python.exe -m backend.cli train data\training-seed42.jsonl --horizon-minutes 60
.venv\Scripts\python.exe -m backend.cli evaluate data\model.joblib
.venv\Scripts\python.exe -m backend.cli predict sim-001
```

Bộ sinh từ chối ghi đè file đã có; dùng tên mới để sinh lại. Khởi động lại backend sau khi train để nạp model mới một lần. `evaluate` đọc báo cáo test được lưu khi train, không tuning/fit lại trên test. Artifact chỉ được đọc từ đường dẫn do quản trị viên kiểm soát; không nạp `.joblib` tải từ người lạ.

Dữ liệu seed 42, 12 thùng, 14 ngày, bước 5 phút cho kết quả đã chạy: MAE persistence **9,01**, tuyến tính **8,54**, Random Forest **5,07 điểm phần trăm**. Đây là kết quả mô phỏng của một bộ dữ liệu cụ thể, không chứng minh độ chính xác ngoài thực tế. Xem [báo cáo AI](docs/AI_VA_VRP.md) và [metric lưu lại](docs/results/ai-seed42.metrics.json). Không suy ra ETA từ dự đoán 60 phút.

Xuất dữ liệu: đăng nhập quản lý, tải `/api/export?bin_id=sim-001&start=0&end=...`; JSONL giữ nhãn nguồn. Đăng ký thùng bằng `POST /api/bins` trước khi import:

```powershell
.venv\Scripts\python.exe -m backend.cli import data\observations.jsonl --source real
```

Import không tự đổi nguồn, mã thùng hoặc thời gian. Đổi nguồn một mã đã đăng ký bị từ chối; mã `real` phải được đăng ký riêng và chỉ dùng dữ liệu thật. Không train chung hai nguồn. Bản ghi không biết giờ vẫn được lưu nhưng không đưa vào bài toán dự báo theo giờ.

## 3. Firmware và phần cứng

Giữ nguyên pin: TRIG/ECHO tay **5/18**, TRIG/ECHO rác **19/21**, servo **13**, LED đỏ/xanh **2/4**. Không thay đổi hoặc in `src/config.h` hiện hữu. `src/settings.h` chỉ dùng Wi-Fi từ file đó; bot token cũ không còn được firmware sử dụng. Khi tạo mới, sao chép `src/config.example.h` thành `src/config.h`; cấu hình MQTT/hiệu chuẩn ở `src/mqtt_config.h` sao chép từ mẫu riêng. **Không dùng lệnh Copy-Item để ghi đè file cấu hình đang có.**

```powershell
# Cài PlatformIO nếu chưa có: python -m pip install platformio==6.2.0
# Hoặc dùng PlatformIO Core được VS Code cài sẵn:
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
```

Build không có CA vẫn thành công và vẫn chứa mã MQTT/TLS; lúc chạy chỉ điều khiển cục bộ. Kết nối mạng chỉ bắt đầu khi có Wi-Fi, giờ SNTP hợp lệ, URI `mqtts://` và CA. Không có fallback insecure.

**Trước khi nhóm tự nạp:** đọc [mạch thật/BOM](docs/PHAN_CUNG.md). HC-SR04 chuẩn dùng 5 V và **cả hai ECHO phải được hạ mức**; schematic Wokwi không xác nhận an toàn điện. Model servo/nguồn chưa được xác định nên chưa có số liệu chọn dòng nguồn, ngưỡng kẹt hoặc tụ. Cấu hình phần cứng bảo vệ mặc định tắt. Không bật khi chưa có cảm biến dòng, hai hành trình và driver cắt nguồn phù hợp.

Hiệu chuẩn: đo `d_empty` khi rỗng, `d_full` ở mức đầy cho phép, đảm bảo `2 ≤ d_full < d_empty ≤ 400 cm`. Mẫu hiện tại `30/4 cm` là ví dụ, chưa là số đo của nhóm. Lọc tay Median 3, lọc rác Trimmed Mean 7. Đợi đóng nắp ổn định 1 giây nếu cảm biến gắn trên nắp. Ngưỡng mặc định 80/75%, 3 lần xác nhận. Ngưỡng được mang theo bản tin để backend/UI không hiểu sai khi đổi cấu hình.

FAULT nắp được chốt, không tự thử lại. Lệnh Serial `r` chỉ reset khi cảm biến tay đã có mẫu hợp lệ, khoảng cách ≥25 cm và điều kiện bảo vệ cho phép. Đây là thao tác nhóm chủ động làm sau kiểm tra cơ khí, không phải khẳng định có bảo vệ chống kẹp.

## 4. MQTT TLS và Telegram

Xem [giao thức/API](docs/KIEN_TRUC_GIAO_THUC.md) và [cấu hình broker/bảo mật](docs/BAO_MAT_VA_VAN_HANH.md). Mosquitto không phải dependency để chạy demo CSDL hoặc bộ test; test dùng AMQTT loopback TLS với credential/CA riêng tạm thời.

```powershell
# Cần cài Mosquitto từ nguồn chính thức; chạy từ thư mục project.
.venv\Scripts\python.exe tools\create_local_certs.py --host localhost
New-Item -ItemType Directory -Force data\mosquitto | Out-Null
mosquitto_passwd -c broker\passwords backend
mosquitto_passwd broker\passwords sim-001
# Khi có thiết bị thật: thêm user bin-001; mỗi thiết bị một mật khẩu.
mosquitto -c broker\mosquitto.conf -v
```

`-c` chỉ dùng lúc tạo file passwords lần đầu; dùng lại sẽ thay file. Công cụ tạo CA từ chối ghi đè. Cấu hình broker mặc định chỉ bind `127.0.0.1`; muốn ESP32 kết nối cần SAN chứa tên/IP LAN chính xác và listener bind đúng IP LAN, không mở ra Internet.

Terminal backend dùng `MQTT_USER=backend`, mật khẩu tương ứng và CA:

```powershell
$env:MQTT_ENABLED = "1"
$env:MQTT_HOST = "127.0.0.1"
$env:MQTT_PORT = "8883"
$env:MQTT_DEV_LOOPBACK = "0"
$env:MQTT_CA = "broker/certs/ca.crt"
$env:MQTT_USER = "backend"
$mqttBackendSecret = Read-Host -AsSecureString "Mật khẩu MQTT backend"
$env:MQTT_PASSWORD = [System.Net.NetworkCredential]::new("", $mqttBackendSecret).Password
.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Terminal simulator dùng credential **sim-001**, đăng ký thùng simulated bằng demo/API trước. File huấn luyện quá khứ sẽ được hiển thị là dữ liệu cũ khi replay, đúng thiết kế:

```powershell
$env:MQTT_USER = "sim-001"
$mqttSimulatorSecret = Read-Host -AsSecureString "Mật khẩu MQTT sim-001"
$env:MQTT_PASSWORD = [System.Net.NetworkCredential]::new("", $mqttSimulatorSecret).Password
.venv\Scripts\python.exe -m simulator.publish data\training-seed42.jsonl --bin-id sim-001 --pace 1
```

Simulator đợi ACK ứng dụng và thử lại cùng ID, tối đa 5 lần; không ACK thì dừng để nhóm chạy lại. Không chạy đồng thời simulator replay và demo ghi cùng mã/boot. Nếu đã dùng `sim-001` với boot khác, hãy dùng CSDL lab riêng bằng `BIN_DB` và đăng ký thùng qua API thay vì nạp demo vào CSDL replay đó.

Telegram mặc định **dry-run**, các công việc được đánh dấu `dry_run` trong outbox và không tự gửi lại khi sau này bật thật. Nếu nhóm muốn thử thật, chủ động đặt `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_USER_IDS` rồi `TELEGRAM_DRY_RUN=0` và khởi động **một** backend. `/status [bin_id]`, `/trangthai [bin_id]`, `/predict [bin_id]`, `/collect`. Không chạy bot khác polling cùng token. Chưa gửi Telegram thật trong lần triển khai này.

## 5. Kiểm thử và tài liệu bàn giao

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=artifacts/tests.xml
.venv\Scripts\python.exe -m tools.smoke_demo
node --check dashboard/app.js
```

Node chỉ dùng kiểm tra cú pháp khi phát triển, không cần để chạy dashboard. C++ test dùng Zig cài trong `.venv`, lần compile đầu có thể mất hơn một phút; không cần ESP32. Test MQTT mở socket loopback TLS trên port ngẫu nhiên; không gửi mạng ngoài. Tất cả test dùng DB/thư mục/credential tạm; Telegram dùng mock/dry-run.

- [Kết quả kiểm thử thực sự đã chạy](docs/KET_QUA_KIEM_THU.md).
- [Kiến trúc, schema, ordering và API](docs/KIEN_TRUC_GIAO_THUC.md).
- [Phần cứng, BOM, hiệu chuẩn và nghiệm thu thiết bị](docs/PHAN_CUNG.md).
- [Bảo mật, queue, năng lượng và vận hành](docs/BAO_MAT_VA_VAN_HANH.md).
- [AI, anomaly, VRP và giới hạn đánh giá](docs/AI_VA_VRP.md).
- [Ma trận yêu cầu → file → test → trạng thái](docs/MA_TRAN_TRUY_VET.md).
- [Ba câu bảo vệ 2A/2B/2C và phân công](docs/CAU_HOI_VA_GOI_Y_TRA_LOI.md).
- [Trước/sau và hướng mở rộng](docs/TRUOC_SAU_VA_MO_RONG.md).

Sửa lỗi thường gặp: `401` → đăng nhập/tạo tài khoản; `403` → cần quản lý hoặc sai Origin; `409` → trùng ID/boot hoặc đang giải tuyến; MQTT không kết nối → kiểm tra giờ, CA/SAN, credentials, listener; `unavailable` → thiếu lịch sử 30 phút, số đo lỗi/cũ hoặc chưa biết giờ. Nếu model train lại, khởi động lại backend. Không xóa CSDL, NVS hoặc CA để chữa lỗi một cách tùy tiện.
