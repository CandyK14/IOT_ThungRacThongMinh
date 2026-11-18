# Bảo mật, queue, năng lượng và vận hành

## Môi trường

`requirements-lock.txt` ghim đầy đủ bộ phiên bản đã cài/chạy trên Windows/Python 3.14; `requirements.txt` là dependencies runtime và `requirements-dev.txt` bổ sung pytest, AMQTT, Zig. Không tự nâng tất cả lên mới nhất. Firmware: Espressif32 7.0.1, Arduino-ESP32 2.0.17, ESP32Servo 3.2.1, ArduinoJson 7.4.3. ESP-MQTT đi cùng ESP-IDF của framework, không cài PubSubClient vì cần publish QoS 1.

Config riêng: `src/config.h`, `src/mqtt_config.h`, `broker/passwords`, `broker/certs/`, `.env`, CSDL/model trong `data/` được ignore. Không ghi token vào UI, log, URL trình duyệt, báo cáo hoặc source. Backend không log URL Telegram hoặc payload lỗi. Mã firmware gốc lưu ở `docs/firmware_ban_dau.cpp.txt`, không chứa nội dung secret của config.h.

Mật khẩu dashboard dùng scrypt với salt ngẫu nhiên; token phiên ngẫu nhiên 256 bit, DB chỉ lưu SHA-256 token, phiên hết hạn 8 giờ. Cookie HttpOnly/SameSite Strict; local HTTP cần `COOKIE_SECURE=0`, khi có HTTPS dùng `1`. Role viewer/manager được kiểm tra server cho đăng ký, export và tạo tuyến. CSP chỉ cho cùng origin, không CDN/bundle chứa secrets. Tên thùng/response được đưa vào DOM bằng textContent.

Server hiện giới hạn loopback/TrustedHost và không bật CORS. Đây là profile lab, chưa cấu hình cloud. Nâng lên LAN/Internet cần HTTPS, hostname allowlist cụ thể, firewall, log/rate limit phù hợp, backup, chính sách retention và credential rotation. Không mở rộng bind rồi coi local cookie đã an toàn qua mạng không mã hóa.

## Broker và TLS

`broker/mosquitto.conf` có listener TLS 8883 loopback, password file, ACL, persistence và giới hạn bản tin. `mosquitto-dev.conf` không mã hóa **chỉ loopback**. Mỗi username thiết bị chính là bin_id và credential riêng; backend có user riêng. Backend ghi ACK còn device không có quyền ghi ACK hoặc topic thùng khác. Khi triển khai thực tế cần bảo vệ file khóa riêng bằng quyền NTFS phù hợp.

Tạo CA local bằng `tools/create_local_certs.py --host IP_HOAC_TEN_BROKER`: script không ghi đè, CA lab 365 ngày, server 90 ngày, SAN chứa hostname/IP đã chọn; không tự cài vào trust store Windows. Copy **CA public** vào `MQTT_CA_PEM`; không nhúng private key server/CA vào ESP32. Broker listener mặc định loopback nên ESP32 không truy cập được cho tới khi nhóm chủ động đổi đúng IP LAN. Dùng mDNS/tên phải xác minh phân giải; `broker.local` trong mẫu chỉ là placeholder.

ESP32 đợi SNTP hợp lệ rồi mới start MQTT TLS. `skip_cert_common_name_check=false`; không setInsecure, không tắt kiểm tra chứng chỉ. CA Telegram cũ không được coi là còn đúng; backend dùng trust store của HTTP client. Cần kiểm tra TLS thực tế với broker/certificate nhóm cấp.

API ESP-MQTT của SDK đã cài được đọc trực tiếp: `esp_mqtt_client_publish(...,qos=1,retain=0)`, `network_timeout_ms=4000`, `disable_auto_reconnect=true`. [Tài liệu ESP-IDF 4.4.8](https://docs.espressif.com/projects/esp-idf/en/v4.4.8/esp32/api-reference/protocols/mqtt.html) xác nhận publish QoS và khả năng block I/O. Timeout MQTT không phải chứng minh trần toàn bộ DNS/TCP/TLS. SDK Arduino đóng gói không expose riêng mọi timeout DNS/handshake trong config MQTT; không sửa binary SDK hoặc giả vờ có giới hạn tổng chính xác. Toàn bộ thao tác chỉ nằm ở task mạng; cần đo phản ứng nắp khi DNS/TLS chậm trên thiết bị thật.

Backend Paho `tls_set(ca_certs=...)` giữ xác minh CA/hostname, không tls_insecure_set. Reconnect 1–60 giây. Profile dev chỉ chấp nhận `127.0.0.1/localhost/::1`, không tự rơi về profile đó khi lỗi TLS. Test đã kiểm chứng private CA không được system trust chấp nhận, credential sai bị broker từ chối, ACL chặn topic thùng khác. Đây là broker AMQTT lab, chưa chạy Mosquitto thực tế trong môi trường này.

## Queue và độ bền

`include/event_queue.h` là logic được cả firmware và C++ host test sử dụng. RAM outbox **34 bản ghi**: tối đa 32 sự kiện bền vững, một telemetry đang chờ ACK và một telemetry mới nhất. Đây là lựa chọn tiết kiệm RAM so với ví dụ 128 trong yêu cầu, vì telemetry còn lại được gộp. Ngoài ra có queue control→network 16 bản ghi, ACK queue 8. Publish mới còn bị chặn nếu bộ đệm QoS động của SDK cộng payload vượt 4096 byte theo esp_mqtt_client_get_outbox_size; đây là dung lượng SDK báo, chưa bao gồm mọi overhead heap. Kích thước thực tế được test/build ghi ở báo cáo; không lấy con số RAM tĩnh làm bằng chứng TLS đủ heap.

Sự kiện FULL/CLEARED/FAULT/RECOVERED được giữ FIFO. Không sửa payload đang chờ ACK. Khi đủ 32 sự kiện thì **giữ sự kiện cũ, từ chối sự kiện mới**, tăng dropped_records và chốt chỉ báo lỗi lưu trữ (hai LED cùng sáng). Không thể bảo đảm không mất sự kiện nếu outage dài hơn khả năng queue; telemetry mới nhất vẫn thể hiện trạng thái sau khi gửi bù. Control queue đầy cũng tăng dropped; không block cơ khí để chờ mạng.

Mỗi thêm/xóa sự kiện tạo snapshot hai bank NVS luân phiên, có magic/version, generation, count, checksum FNV-1a; chọn bank hợp lệ mới nhất sau reboot. Checksum nhằm phát hiện ghi dở/lỗi ngẫu nhiên, **không phải chữ ký bảo mật**. Nếu bank mới hỏng giữ bank cũ, có thể phát lại sự kiện đã ACK; backend dedup xử lý. Nếu cả hai hỏng báo lỗi, không tự format. NVS blob format phụ thuộc layout record; đổi firmware layout cần version/migration riêng, hiện chỉ bảo đảm khôi phục cùng format.

Firmware không ghi Flash mỗi lượt cảm biến; chỉ theo sự kiện/ACK, telemetry không bền qua reset. Vẫn có cửa sổ mất điện từ lúc control tạo event → queue RAM → task mạng persist, đặc biệt khi network task đang block TLS. Không có đo trần cửa sổ này trên máy thật. Nếu cần bảo đảm cao hơn, tách task lưu trữ hoặc thêm nguồn giữ điện; phiên bản hiện tại công bố giới hạn này thay vì gọi zero-loss. Chưa đo wear/endurance; snapshot mỗi sự kiện cần đánh giá theo tần suất thật.

Một bản tin in-flight, chỉ xóa khi ACK đúng boot/seq. Mất ACK retry cùng nội dung, backoff khoảng 1–30 giây cộng jitter; gửi bù được giới hạn, không vòng lặp publish không nghỉ. Wi-Fi retry mỗi 10 giây, MQTT reconnect lùi khoảng 1–60 giây+jitter. Metrics queue_depth/dropped/reconnects/offline_ms là snapshot **tại lúc tạo bản tin**, giữ bất biến khi retry; offline_ms là thời gian của đợt offline gần nhất, không phải tổng toàn đời. Độ trễ gửi bù được backend tính từ measured/received nếu biết giờ. Không thể gửi cảnh báo từ xa tức thời khi không có mạng.

## Telegram

Một OS file lock theo DB ngăn hai backend worker cùng poll/outbox; dùng `uvicorn --workers 1`, không chạy bot khác cùng token ở ứng dụng khác. Offset update lưu DB; công việc phản hồi dedup bằng update_id. Xác minh chat ID, và user ID nếu cấu hình allowlist nhóm. ID không được phép không được phản hồi.

Outbox có status pending/sent/dry_run/failed, attempts, next_at, lỗi đã lược secrets. Mỗi lượt tối đa 4 công việc, tối đa 8 lần thử, lùi thời gian và tôn trọng retry_after; polling cũng lùi theo retry_after. Kiểm tra HTTP **và** JSON `ok=true`, không coi 200/ok=false là thành công. HTTP client có connect 4 giây, các pha đọc/ghi 10 giây, không coi đó là trần toàn giao dịch.

Không bảo đảm exactly-once Telegram: nếu Telegram nhận nhưng response mất, retry có thể gửi trùng. DB chỉ bảo đảm một công việc nội bộ cho cùng ID. Dry-run không gửi HTTP/poll; những bản ghi đã dry_run không tự được gửi thật khi đổi cấu hình. Cảnh báo AI có nhãn phương pháp/chân trời, dữ liệu phải usable và dự báo chưa hết hiệu lực, cooldown 1 giờ/thùng; không chặn cảnh báo đầy theo đo thực.

## Năng lượng và bảo trì

Heartbeat mặc định 60 giây, có thể thử 60–300 giây tùy yêu cầu. Gửi ngay sự kiện, gộp telemetry offline, bỏ HTTPS polling tại ESP32. Đây là cải tiến về lịch truyền, **chưa có số đo tiết kiệm điện**. Không deep-sleep dài khi HC-SR04 phải nhận tay liên tục; muốn ngủ phải có nguồn đánh thức ngoài (nút/PIR/đầu đo riêng phù hợp) và đánh giá mất chức năng nhận tay, thời gian kết nối lại.

Đo điện năng tại đầu vào **toàn hệ thống**, cả ESP32, cảm biến, servo, nguồn/driver; ghi điện áp, dòng theo thời gian, tích phân `Wh=∫V×I dt/3600`. Đo cùng tải/lịch thao tác ở baseline và bản mới: idle, quét tay, mở/đóng, reconnect, TLS, offline gửi bù. Tách dòng tĩnh với xung servo và tổn hao nguồn. Chưa có thiết bị đo nên không công bố thời lượng pin/Wh. Chưa có đo battery, trường battery_mv luôn null.

SQLite WAL và FULL phù hợp lab một backend. Sao lưu bằng SQLite backup API hoặc dừng sạch rồi copy đủ dữ liệu; không copy riêng DB đang chạy và bỏ WAL. Chưa có retention tự động, nên cần theo dõi dung lượng khi thu dữ liệu nhiều tuần. Một triệu bản ghi cần đo lại dung lượng/độ trễ trước khi chuyển PostgreSQL. Không tự xóa dữ liệu thật để chạy test.
