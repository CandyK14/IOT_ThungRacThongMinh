# Trước/sau và hướng mở rộng

## So sánh theo mã, không gán số đo thực chưa có

| Hạng mục | Bản đầu vào | Bản nâng cấp |
|---|---|---|
| Điều khiển | loop cảm biến + HTTP đồng bộ | FreeRTOS control sở hữu servo, network riêng |
| Siêu âm | Hai lần pulseIn gần nhau, một mẫu | Slot ≥70 ms, Median3 tay/Trimmed7 rác, stale/fault |
| Hiệu chuẩn | Chiều cao giả định30, không full-offset | Hai mốc empty/full, reject trước clamp, pause đầu đo trên nắp |
| Nắp | Bool mở/đóng, hand lỗi có thể đóng | State machine, hold/hysteresis/reverse, fault latch và reset có điều kiện |
| Điện | 3V3 HC-SR04, ECHO trực tiếp | Mô hình 5V + hai divider; schematic thật/BOM có điều kiện |
| Servo protection | Không feedback/current/cut | Interface/logic/test giả lập, mặc định tắt; **chưa có bảo vệ phần cứng xác minh** |
| Mạng | Telegram HTTPS/poll tại ESP32 | MQTT TLS QoS1 sau SNTP; bot tại backend |
| Queue | Trạng thái RAM, không lịch sử offline | 32 event bền/34 slot RAM, hai bank NVS/checksum, ACK ứng dụng |
| Chống trùng/thứ tự | Chưa có | Unique ID, boot_no NVS, replay/duplicate/concurrent tests |
| Server/UI | Chưa có | FastAPI/SQLite/auth/dashboard offline map/history/route |
| AI | Chưa có | RF dự báo60phút, baseline, IF/rule, report mô phỏng |
| VRP | Chưa có | OR-Tools capacity/depot/time limit, baseline công bằng, scale100 |
| Bằng chứng | Build cũ, chưa test thực tế | Build mới, test host/API/TLS/mock, metric/smoke; thiết bị/UI vẫn cần nghiệm thu |

Không so thời gian phản ứng, Wh, tuổi thọ pin hay độ bền servo trước/sau khi chưa đo. Flash/RAM là con số build, không hiệu năng vận hành.

## TinyML trên ESP32 — tùy chọn

Chỉ cân nhắc khi đã có lịch sử thật và baseline backend đáng tin. Bản hiện tại không chạy ML ở ESP32. Cần chọn model nhỏ/quantized và công cụ chuyển đổi phù hợp; RandomForest sklearn joblib không thể chép sang ESP32 rồi chạy trực tiếp.

Ngân sách thử nghiệm đề xuất: giới hạn model và runtime bổ sung ban đầu ≤100 KiB Flash, tensor/work buffer ≤32 KiB RAM, inference mục tiêu ≤20 ms trên **task riêng ưu tiên thấp**. Đây là **trần thiết kế để đo/thử**, không phải kích thước/chạy trễ đã đạt. So với build hiện tại cần trừ heap TLS động, task stack và buffer mạng; không lấy tổng RAM trừ RAM tĩnh rồi cấp hết cho tensor. Nếu không còn margin/độ trễ điều khiển, giữ AI backend. Test missing model/corrupt model/version, đo worst-case inference/TLS cùng lúc; AI không được quyết định chống kẹp hoặc cắt nguồn.

Ưu điểm có thể có: dự báo baseline nhỏ khi mất mạng; nhược điểm: cần lịch sử/cấp phát, phân phối model, theo dõi drift và cập nhật an toàn. Dự báo offline vẫn không tự gửi cảnh báo từ xa nếu mất mạng.

## Camera phân loại rác — tùy chọn

Cần camera, ánh sáng/vị trí cố định, tập ảnh thật có nhãn và đánh giá theo môi trường; có thể cần board xử lý khác nếu tài nguyên không đủ. Nếu muốn **phân loại vật lý**, phải thêm cơ cấu ngăn/chuyển hướng, phản hồi vị trí, kiểm soát vật lạ và thử an toàn riêng. Một ảnh phân loại không tự làm servo nắp biến thành cơ cấu phân loại. Cần cân nhắc quyền riêng tư, lưu ảnh, thời gian xử lý và nguồn; không thêm camera hoặc API trả phí vào demo chính.

## Chatbot/LLM — tùy chọn

Có thể truy vấn trạng thái/lịch sử/dự báo qua backend đã phân quyền, câu trả lời phải kèm tuổi dữ liệu và nguồn. Secret API giữ server, kiểm tra role ở từng tool, giới hạn chi phí/tần suất, chống prompt injection từ tên thùng/tài liệu. Không cho mô hình tự tạo số cảm biến, quyết định an toàn hoặc gửi lệnh servo ngoài kiểm soát. Cần đánh giá dataset câu hỏi thực tế và câu từ chối khi dữ liệu unknown. Bot lệnh Telegram hiện tại đủ phục vụ demo, không cần LLM.

## Đường bộ và vận hành lớn hơn — tùy chọn

Có thể thay ma trận Haversine bằng dữ liệu đường bộ hợp pháp/OSRM tự host khi có nhu cầu, kèm thời gian di chuyển, hạn chế xe, time windows và thời gian phục vụ. Giữ baseline cùng ràng buộc mới. Nếu load database tăng, đo trước khi chuyển PostgreSQL; thêm retention/backup/monitoring, credential provisioning, firmware OTA có chữ ký và migration dữ liệu có kiểm soát. Không tự triển khai cloud công khai trong công việc này.
