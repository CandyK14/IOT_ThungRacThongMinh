# Ma trận truy vết yêu cầu → mã → bằng chứng → trạng thái

Đối chiếu `PROMPT_CODEX_NANG_CAP_TOAN_DIEN_VA_AI.md` và các vấn đề P0/P1/P2, câu 2A/2B/2C trong `DANH_GIA_PROJECT_VA_CAU_HOI.md`. Ngày 17/11/2026. Không đánh đồng build/test host với thử điện/cơ khí. Mọi hàng “đã triển khai” vẫn chịu giới hạn ở cột cuối.

Ký hiệu: **T** = có test tự động đã chạy; **B** = build đã chạy; **D** = có mã/tài liệu nhưng chưa nghiệm thu thiết bị; **C** = check môi trường chưa thực hiện được; **M** = hướng mở rộng, không là dependency demo.

## Phạm vi và cách làm việc (mục 1–3)

| Yêu cầu | Module/file | Bằng chứng | Trạng thái |
|---|---|---|---|
| Đọc hướng dẫn, đánh giá lại code, không chỉ lập kế hoạch | README, mã gốc lưu docs/firmware_ban_dau.cpp.txt | Không thấy AGENTS.md tại project/các thư mục cha đã kiểm tra; code ban đầu chỉ firmware | Tài liệu đã đối chiếu |
| Bảo toàn config/secret, không commit/push/deploy | .gitignore, src/settings.h, config mẫu riêng | Không mở/in config.h; không có .git trong workspace đầu vào | Đã giữ phạm vi |
| Không gửi Telegram/nạp thiết bị tự động | backend/config.py, tests/test_telegram.py | Mock/dry-run, không lệnh upload | T; thiết bị chưa thử |
| Tiếng Việt và phân loại đã làm/chưa đo | dashboard/, README, docs/ | Tài liệu/badge real/simulated, bảng kết quả | D; visual UI C |
| Đường đi thiết bị→TLS MQTT→DB→API/AI/VRP | src/main.cpp, backend/, simulator/publish.py | tests/test_mqtt_integration.py | T với broker AMQTT TLS; ESP32 thực D |
| Nắp độc lập Wi-Fi/backend/AI; backend gọn | controlTask, networkTask, backend/app.py | Kiến trúc task, native test state machine | B/T host; độ trễ thật D |
| FastAPI/SQLite/sklearn/OR-Tools/Mosquitto | requirements, broker/ | Build/test Python/SDK, config broker | T; Mosquitto thực C |
| Local Windows không Docker/cloud trả phí | README, backend.cli demo --watch | CLI demo + smoke, 30/100 thùng | T; browser C |
| TinyML/camera/chatbot/CoAP ngoài luồng chính | docs/TRUOC_SAU_VA_MO_RONG.md, câu 2B | Phân tích riêng, không thêm dịch vụ/phần cứng | M |

## A. Điện, firmware và lỗi (mục 4; P0, P1-C/D/E/F, câu 2A)

| Yêu cầu | Module/file | Bằng chứng | Trạng thái |
|---|---|---|---|
| Datasheet đúng loại, 5 V HC-SR04, cả hai ECHO hạ mức | diagram.json, PHAN_CUNG.md, hardware_wiring.svg | Datasheet HC-SR04/ESP32 dẫn nguồn, tính chia áp | D; cần kiểm tra linh kiện/VOH thật |
| Sai số nguồn/điện trở, mô phỏng khác mạch thật | PHAN_CUNG.md | 10k/15k 1%, tính min/max, điều kiện rail/backfeed | D; chưa đo |
| BOM, servo nguồn riêng, tụ/chung GND | PHAN_CUNG.md | Model/dòng/nguồn chưa biết được đánh dấu rõ, công thức chọn tụ | Cần linh kiện/thông số |
| Ẩm/đầu đo, vùng mù cảm biến thay thế | PHAN_CUNG.md | Không phủ mặt siêu âm, không chọn model chống nước thiếu datasheet | D/M |
| Đối chiếu board/pin, chân tùy chọn riêng | diagram.json, platformio.ini, PHAN_CUNG.md | DOIT vs DevKitC, giữ pin gốc, bảng 34/32/33/26 | B; board thật D |
| Tách mạng khỏi control, một owner servo | src/main.cpp | controlTask/networkTask, queue, mutex ngắn | B; race log thực D |
| Timeout đo, không delay gom mẫu | main.cpp distance/controlTask | pulseIn 25 ms, slot 70 ms, sleep RTOS 5 ms | B/T logic; latency thật D |
| DNS/TCP/TLS timeout/backoff theo SDK | networkTask, docs/BAO_MAT_VA_VAN_HANH.md | Đọc mqtt_client.h cài sẵn; network_timeout_ms; công bố giới hạn DNS/handshake | B/D; chưa đo trần |
| SNTP không chặn, TLS chỉ sau có giờ | setup/networkTask | configTime, time gate, CA/hostname bắt buộc | B; cold boot thật D |
| Không setInsecure; CA/broker/server rõ | mqtt_config.example.h, broker/, backend/mqtt.py | TLS integration, CA sai bị từ chối | T backend; firmware TLS thật D |
| Chống tràn millis, heap/stack/log | bin_logic.h elapsed, network log | Native rollover; log heap/high-water mỗi 30 s | T; heap/stack thực D |
| Hai cảm biến kích lần lượt, tay nhanh/rác chậm | controlTask | Lịch 4 tay+1 rác, ≥70 ms giữa trigger | B; nhiễu chéo thật D |
| Trimmed Mean 7, Median tay, thiếu/stale/ngoại lai | bin_logic.h Window, controlTask | tests/firmware_logic.cpp | T host |
| Hiệu chuẩn 2 mốc, reject cấu hình/số đo sai trước clamp | Calibration, static_assert, mqtt_config mẫu | Mốc0/100/80, NAN, vùng mù, ngoài vùng bố trí | T/B; mốc đo thật cần bổ sung |
| Unknown khác 0, giữ lịch sử/tuổi dữ liệu | schema/db/app/dashboard | tests/test_backend.py unknown/stale | T API; UI C |
| Sensor trên nắp tạm ngừng, chờ ổn định | FILL_SENSOR_ON_LID/controlTask | Xóa window, settle 1000 ms; inspection/build | B; cơ khí D |
| Ngưỡng cấu hình 80/75, xác nhận và không spam | Hysteresis, Message, db.ingest | Native + custom threshold/backstop tests | T; UI custom chưa visual |
| % chiều cao không phải kg/thể tích chính xác | PHAN_CUNG.md, AI_VA_VRP.md, UI | Nhãn giải thích, capacity_l chỉ là giả định | Đã ghi rõ |
| State CLOSED/OPENING/OPEN/CLOSING/FAULT, góc/thời gian | LidController | Native giữ nắp/reverse/timeout/fault | T host; vị trí thật D |
| Hand sensor lỗi không tương đương “không người” | LidController.tick, controlTask | Native invalid/fault không tự đóng | T; chống kẹp chưa chứng minh |
| Driver/interface bảo vệ tùy chọn, không số dòng giả | protectionInput, ProtectionInput | Mặc định tắt, ADC/limits/power interface, native fake inputs | B/T host; cần linh kiện |
| Startup transient, quá dòng kéo dài, travel timeout, latch/reset | Protection, LidController.reset | Native transient/trip/timeout/reset; startup gate khi bật driver | T host; ngưỡng thật chưa có |
| Ngắt nguồn thật chỉ khi có driver; detach không thay thế | main.cpp POWER_PIN, PHAN_CUNG.md | Default protection off, power boot LOW, docs giới hạn | D; cắt dòng thật chưa thử |

## B. MQTT, queue, năng lượng (mục 5; P1-G, câu 2B)

| Yêu cầu | Module/file | Bằng chứng | Trạng thái |
|---|---|---|---|
| Publish QoS1 thật, topic/version/TLS/ACL riêng | ESP-MQTT, broker/acl, MQTT schema | SDK API + test TLS/QoS1 AMQTT | B/T; broker/ESP thật D |
| Đủ schema nullable/time/quality/battery/count | backend/schema.py, main.cpp serialize | Validation param tests, integration payloads | T; chưa thu payload UART thật |
| Boot đổi, seq tăng, ID bất biến qua retry/reboot | NVS boot counter, Record/Journal | Host journal restore, DB multi-boot/replay/concurrent dedup | T/B; reset phần cứng D |
| JSON compact, payload/queue sizing; CBOR so sánh | serialize, schema.py, docs bảo mật/câu2B | Smoke max JSON, bounds 2048; sizeof host/ELF | T; đo payload thiết bị D |
| Event sớm, telemetry 60–300s cấu hình | emit, HEARTBEAT_MS | Source/build, simulator timestamps | B; độ trễ thật D |
| Queue RAM hữu hạn/ưu tiên/coalesce/drop count | event_queue.h Outbox, FreeRTOS samples | Native coalesce/inflight/overflow, docs chính sách | T |
| Lưu Flash event, torn write, dung lượng/wear/window mất | Journal 2 bank/NVS, docs bảo mật | Native checksum corruption/restore, giới hạn công bố | T host; cắt điện/Flash wear D |
| ACK sau commit, chỉ xóa đúng ID | db.ingest, Ingestor.on_message, networkTask | TLS integration restart/replay, native ACK duplicate | T; ESP thực D |
| Backoff/jitter/trần, không storm | networkTask, simulator.publish, Paho | Inspection/build; publish test bounded retry | B/T; outage dài thật D |
| Offline FULL→CLEARED→reconnect giữ history/current | outbox/DB ordering | Native queue order + integration replay sau restart | T host/broker |
| Reconnect/depth/drop/offline/delivery delay metrics | Record snapshots, db.states | Schema/DB/API tests; log sizes | T/B; số đo runtime chưa có |
| Không deep-sleep mù chức năng | Firmware không sleep dài, docs năng lượng | Phân tích wake source/giới hạn | Đã thực hiện/phân tích |
| Đo điện năng toàn hệ thống, không bịa pin/instant offline alert | docs bảo mật/PHAN_CUNG | Kế hoạch V/I/Wh toàn hệ, null battery | D; chưa đo |

## C. Backend, Telegram và bảo mật (mục 6; P2, câu 2C)

| Yêu cầu | Module/file | Bằng chứng | Trạng thái |
|---|---|---|---|
| Module ingest/API/cảnh báo/AI/routing/health/env | backend/ | API smoke/lifespan; public/private health | T |
| Bảng/migration/index/history/predictions/outbox | db.py SCHEMA/schema_version | SQLite temp tests, idempotent init | T; migration v1 only |
| Measured/received/source/quality rõ | schema.py/db.py | unknown time và source mismatch tests | T |
| Unique, duplicate không thêm event/job | db.ingest | Reboot + 20 concurrent duplicate tests | T |
| Đảo thứ tự/nhiều boot/không biết giờ không ghi đè | boots/bin_state | Random 4 boot ×10 seq replay, conflict boot tests | T |
| Range/size/rate/schema/log không secret | schema.py, Ingestor.handle | Invalid/oversize/topic/source/rate tests | T; gateway public ngoài phạm vi |
| Online/offline khác stale/fault | db.states | Replay không tăng last_seen, unknown/stale test | T; không dùng LWT |
| Bot/token/polling backend một owner | telegram.py, SingleWorker | OS lock test, offset/dedup update | T; bot thật chưa thử |
| /status,/trangthai,/predict,/collect | process_update | Command allowlist/chat/user tests | T mock |
| HTTP+ok=false/timeout/retry_after/bounded retry | TelegramWorker | Mock status200 false/429/timeout/restart | T mock |
| Outbox durable, cooldown, at-least-once giới hạn | db.py/ml.py/telegram.py | Dedup/restart tests; docs Telegram ambiguity | T; Telegram thật C |
| Dry-run mặc định, không cùng direct bot ESP | config.py, firmware bỏ Telegram | Dry-run forbidden-network test | T |
| Viewer/manager, hash/session/role server | auth.py/app.py | Password/401/403/logout/session cookie tests | T |
| Secret config mẫu/gitignore/TLS không fallback | .env.example/mqtt_config/broker | Source inspection, TLS profile validation tests | T/D |
| Local Windows, Docker không bắt buộc | README/requirements | Demo/smoke và pytest Windows | T |
| SQL parameterized, không CORS *, no untrusted model upload | db.py/app.py/ml.py | Input/Origin/role tests; endpoint inventory | T |

## D. Dashboard (mục 7)

| Yêu cầu | Module/file | Bằng chứng | Trạng thái |
|---|---|---|---|
| Tổng/thugom/offline/lỗi/update | dashboard/app.js/index.html | API states + static served, syntax check | T API; visual C |
| Per-bin fill/lid/history/events/quality/age/prediction | detail/render/history canvas | API history/events; labeling source/stale | T API; visual C |
| Map marker/heatmap 20–100 thùng, weight/coordinate | canvas map, generate/register_bins | Smoke 30/100; custom geographic projection offline | T data; UI C |
| Real/simulated UI/API/export không trộn âm thầm | source registry/labels/export | Role/export/source tests | T API; UI C |
| Lọc trạng thái/mã/thời gian/ưu tiên | filters/history controls/bin list | JS implement + syntax | Đã triển khai; tương tác UI C |
| Route/depot/xe/km/unserved/assumptions | route form/map/result | Routing tests + smoke | T API; UI C |
| Không cần Internet/maps trả phí, fallback bảng/chart | Local CSS/JS/canvas, không tile/CDN | CSP self-only/static assets | Đã triển khai; browser C |
| Laptop/phone/loading/empty/error/backend offline | Responsive CSS, error states | Syntax/API/static checks | C kiểm tra desktop/mobile trực quan |

## E. AI (mục 8)

| Yêu cầu | Module/file | Bằng chứng | Trạng thái |
|---|---|---|---|
| Dự báo fixed horizon 60 phút/configurable | ml.py/train CLI | Artifact horizon/CLI and cold-start tests | T simulated |
| Features causal/time/lags/opens, không metadata tương lai | features/dataset | Causal feature test, same-boot guard | T |
| Persistence/linear/RF cùng tập, chọn validation | train/metrics | Seed42 metric JSON + repeatability test | T simulated |
| Không suy ETA, đo≥80 độc lập ML, early alert quality/cooldown | db backstop/ml.update_predictions | Threshold tests, no-ML ingest/inference fallback | T; cảnh báo early thật chưa đo |
| Import/export real, seed/nhiều bin/cycles/noise/gaps/fault | cli/export/generate | Deterministic seed+end, label/fault/gap tests | T; chưa có real dataset |
| Timestamp thật, horizon tolerance, no long interpolation | dataset/features | Gap/causality/purged split tests | T |
| Chronological train/val/test, purge horizon/lookback | train split, metrics metadata | Boundary assertions, no fit preprocessing/test | T |
| Xét thùng/cycle holdout, không claim quá mức | AI_VA_VRP.md | Công bố cùng nhóm thùng, chu kỳ có thể cắt ranh | Chưa đánh giá holdout độc lập |
| MAE/RMSE pp, FP/FN/TP, không accuracy giả | metrics/report JSON | Test counts/evaluation, baseline cùng tập | T simulated |
| Artifact version/features/horizon/data/metrics/repeat CLI | joblib + metrics.json, CLI | Two training runs equal metrics, SHA256 | T; local artifact trusted only |
| Cold-start/no model/stale/fault/inference fail, không train request | Predictor/worker | Missing model/history/fault tests | T |
| AI fault không treo ingest/control | Task/module split, worker catches | API/integration không có model vẫn chạy | T host; thiết bị D |
| IsolationForest so rule, labeled false positives | train/anomaly_test | Metric IF kém rule được báo trung thực | T simulated; real chưa có |
| Anomaly không chẩn đoán phần cứng/tắt alarm; phân biệt signal filter | docs/AI_VA_VRP.md/core logic | ML chỉ output cảnh báo, không gọi servo | Đã ràng buộc |

## F. VRP (mục 9)

| Yêu cầu | Module/file | Bằng chứng | Trạng thái |
|---|---|---|---|
| OR-Tools depot/xe/capacity/time limit | routing.py RouteRequest/solve | Empty/single/multi/capacity tests | T |
| Chọn measured/prediction fresh + lý do | select_points | Expiry/source tests, point reasons | T |
| Unknown/offline/fault review/conservative | select_points | Stale None và conservative tests | T |
| Ma trận địa lý có nhãn/đơn vị, không road claim | distance_m/result/UI | Haversine mét + assumption labels | T API; đường bộ M |
| Demand/xe tương thích lít, không kg | ceil(capacity_l*fill/100) | assert_capacity ở solver và baseline | T, dựa giả định |
| Baseline cùng points/constraints, cùng served set mới so % | baseline/solve comparison | Multiple/infeasible tests, smoke 100 | T |
| Costs/time/served/dropped/reasons, không “global optimum” | solve output | Smoke JSON, 100 điểm đủ phục vụ | T |
| Demo20–100 không cần100device | simulator/CLI + scale smoke | 30 thùng ingest, case solver100 điểm | T data/API; UI C |

## Kiểm thử và đầu ra (mục 10–12)

| Yêu cầu | File/bằng chứng | Trạng thái |
|---|---|---|
| Firmware calib/filter/stale/threshold/lid/rollover | tests/firmware_logic.cpp + test_firmware_native.py | T host, B ESP32 |
| Protection startup spike/stall/travel/reset fake inputs | C++ Protection/LidController tests | T host, phần cứng D |
| Queue overflow/reboot/torn/ACK/lịch sử/retry | C++ Journal/Outbox + MQTT integration/reorder tests | T host/broker; cắt nguồn thật D |
| Backend invalid/auth/dedup/order/boots/stale/roles | test_backend.py/test_ordering_concurrent.py | T |
| Telegram errors/retry/outbox/chat/user/dryrun | test_telegram.py | T mock |
| AI no model/causal/split/baseline/artifact | test_ml_routing.py | T simulated |
| VRP empty/single/multi/infeasible/stale/units | test_ml_routing.py/smoke | T |
| Simulator MQTT→TLS→DB→AI unavailable/route→mock, restart | test_mqtt_integration.py | T; dashboard HTTP smoke riêng |
| Firmware RAM/Flash, commands và giới hạn | KET_QUA_KIEM_THU.md, ELF/bin | B; runtime heap/stack D |
| Target≤500ms, 24h, AP/Internet/TLS/reset/jam protocol | PHAN_CUNG.md checklist | Chưa đo, không claim đạt |
| Test isolated không đụng data thật | pytest tmp_path/TemporaryDirectory, TLS cert temp | T |
| Broker/Wokwi/browser/dependency thiếu phải ghi rõ | KET_QUA_KIEM_THU.md | Browser host/Wokwi/Mosquitto C; dependencies đã cài |
| Firmware/config/Wokwi/BOM | src/, include/, diagram.json, PHAN_CUNG.md | B/D |
| Broker/backend/schema/dashboard/simulator/local smoke | broker/, backend/, dashboard/, simulator/, tools/ | T API/B; visual C |
| AI pipeline/data seed/baseline/metrics/coldstart | ml.py/generate.py/results/ | T |
| VRP/module/demo/map labels | routing.py/dashboard/results | T API; visual C |
| Tests/README/dependency/kiến trúc/security/queue/energy | tests/, README, lock, docs/ | Đã bàn giao |
| 2A/2B/2C6đ/rubricgợiý/AI/chia3người | CAU_HOI_VA_GOI_Y_TRA_LOI.md | Đã bàn giao |
| Truy vết và mở rộng TinyML/camera/chatbot | Tài liệu này + TRUOC_SAU_VA_MO_RONG.md | Đã bàn giao; mở rộng M |
| Demo local chưa cắm ESP32 và báo cáo cuối trung thực | README demo, KET_QUA_KIEM_THU.md | T dữ liệu/API; người dùng cần thử UI |
