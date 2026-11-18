# Mạch thật, BOM và kiểm thử thiết bị

**Trạng thái:** đã sửa mô hình và firmware; chưa đo mạch, chưa nạp ESP32, chưa xác nhận servo/nguồn thực tế. Đọc tài liệu này trước khi nhóm chủ động đấu nối. [Sơ đồ mạch thật](hardware_wiring.svg) tách riêng với Wokwi.

## HC-SR04 và điện áp

Tài liệu HC-SR04 do ElecFreaks phát hành, lưu tại [SparkFun](https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf), nêu nguồn 5 V, vùng đo 2–400 cm, TRIG ≥10 µs, chu kỳ đo trên 60 ms. Các thông số đó chỉ áp dụng module đúng loại; kiểm tra nhãn/datasheet linh kiện nhóm thực sự có. [Datasheet ESP32](https://www.espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf) nêu các giới hạn điện áp và ngưỡng logic; GPIO không được coi là chịu 5 V.

Mỗi ECHO dùng **10 kΩ phía trên và 15 kΩ xuống GND, sai số 1%**:

```text
HC-SR04 ECHO ── 10kΩ ──┬── GPIO18 (tay) hoặc GPIO21 (rác)
                      └── 15kΩ ── GND
```

Hai cảm biến có hai bộ chia riêng. Vout = Vecho × Rbottom / (Rtop + Rbottom). Danh định 5 V → **3,00 V**. Nếu Vecho bám nguồn 5 V ±5% và R sai số ±1%: Vout thấp nhất `4,75×14,85/(10,10+14,85)=2,827 V`; cao nhất `5,25×15,15/(9,90+15,15)=3,175 V`. Với rail ESP32 3,3 V ±5%, VDD thấp nhất 3,135 V nên đầu vào cao nhất vẫn dưới VDD+0,3; VIH cao nhất `0,75×3,465=2,599 V`.

Đây là tính toán theo **giả định** ECHO mức cao gần nguồn, chưa phải đo module. Datasheet ngắn ghi TTL nhưng không cung cấp đầy đủ VOH theo tải: cần đo VOH và dạng xung thực tế ở hai GPIO. Với ECHO chỉ 4,5 V, Vout thấp nhất khoảng 2,679 V; với VOH thấp hơn phải tính lại/đổi sang bộ chuyển mức có thông số đảm bảo. Không dùng phép tính danh định để tuyên bố mọi bản clone đều tương thích. Nếu ESP32 mất nguồn nhưng cảm biến còn 5 V, bộ chia không bảo đảm chống cấp ngược GPIO: cấp/tắt đồng bộ hai nhánh hoặc dùng buffer có Ioff/phần cách ly phù hợp.

TRIG GPIO 3,3 V được mô tả theo yêu cầu TTL của module mẫu; xác minh ngưỡng của linh kiện thật, dùng buffer nếu cần. GPIO5 và GPIO2 là chân có liên quan strap boot: bảo đảm thiết bị ngoài không kéo sai mức khi reset; hiện giữ pin gốc, chưa xác minh trên board thật.

## Nguồn servo và BOM

```text
Nguồn logic 5 V ── ESP32 regulator 3,3 V
               └─ hai HC-SR04 5 V
Nguồn servo đã chọn theo model/tải ── cầu chì/giới hạn dòng ── driver nguồn ── servo V+
ESP32 GPIO13 ── PWM servo
GND ESP32 ── điểm sao chung ── GND HC-SR04 / nguồn servo / servo
```

Không nối song song hai đầu ra nguồn 5 V độc lập. Chỉ chung GND và tín hiệu điều khiển theo schematic. Nhánh servo không lấy công suất qua GPIO hoặc mặc định cho rằng USB/5V board chịu được dòng kẹt. Khi chưa lắp bảo vệ tùy chọn, driver trong sơ đồ là vị trí thiết kế, không phải linh kiện đã có.

| Hạng mục | Số lượng | Trạng thái / cần xác minh |
|---|---:|---|
| ESP32 DOIT DevKit V1 | 1 | Build đúng board; kiểm tra board vật lý thực tế |
| HC-SR04 chuẩn 5 V | 2 | Xác minh đúng loại, vị trí và VOH |
| 10 kΩ 1% + 15 kΩ 1% | 2 bộ | Cần bổ sung nếu chưa có; mỗi ECHO một bộ |
| Servo | 1 | **Chưa biết model, điện áp, dòng chạy/khởi động/kẹt, mô-men** |
| Nguồn servo, dây, đầu nối, cầu chì/giới hạn dòng | Theo tải | Chưa chọn định mức khi chưa có model và số đo |
| Tụ sát servo + bypass logic | Theo thử nghiệm | Chưa chốt giá trị; tính rồi đo sụt áp |
| LED đỏ/xanh + 220 Ω | 2 bộ | Đã có trong mô hình; xác minh dòng theo LED thật |
| Hộp mạch, cable gland, đầu nối phù hợp ẩm | Theo bố trí | Cần bổ sung/kiểm tra |
| Cảm biến dòng analog, hai công tắc hành trình, driver ngắt nguồn | Tùy chọn | Chưa lắp; phải hiệu chuẩn/kiểm tra điện áp trước bật firmware |

Chọn tụ từ `C ≥ I_transient × Δt / ΔV` sau khi có số đo, cộng ESR, ripple, sụt dây và đáp ứng nguồn. Đây là phương pháp ước tính, không phải phép tính đã thực hiện với servo hiện hữu. Dùng nguồn giới hạn dòng và đo tại đầu servo/ESP32 bằng thiết bị phù hợp. Không suy ra tụ lớn bất kỳ sẽ khắc phục được nguồn yếu.

## Phần cứng bảo vệ tùy chọn

| GPIO bổ sung | Vai trò | Interface đang có |
|---:|---|---|
| 34 | Dòng analog, đầu vào tối đa phù hợp ADC ESP32 | `analogReadMilliVolts`, offset/gain cấu hình |
| 32 | Hành trình mở | INPUT_PULLUP, active LOW |
| 33 | Hành trình đóng | INPUT_PULLUP, active LOW |
| 26 | Enable driver nguồn servo | Active HIGH; LOW ngắt qua driver phù hợp |

`SERVO_PROTECTION_ENABLED=0` mặc định. Khi bật cần `SERVO_CURRENT_ZERO_MV`, `SERVO_CURRENT_MA_PER_MV`, `SERVO_TRIP_MA` đo theo thực tế; build từ chối gain/ngưỡng bằng 0. Input dòng không được vượt rail ADC; module dòng có output 5 V không thể nối thẳng. Driver nguồn cần trạng thái tắt khi reset và đáp ứng dòng thực tế, không điều khiển tải servo trực tiếp bằng GPIO26. Chương trình không thay thế bảo vệ quá dòng phần cứng độc lập.

Khi bật bảo vệ, driver khởi động ở trạng thái tắt; chỉ cho chạy khi hành trình đóng đang xác nhận và hành trình mở không kích hoạt. Nếu không thỏa, chốt FAULT và giữ tắt nguồn để nhóm kiểm tra. Logic có cửa sổ khởi động 200 ms, quá dòng liên tục 200 ms sau đó, hành trình quá 1500 ms thì chốt FAULT. Đây là tham số **đề xuất thử nghiệm**, chưa được xác nhận cho servo của nhóm. Có thể cần giảm đáng kể theo phân tích lực/nhiệt. Khi fault do quá dòng/hành trình, GPIO26 ra LOW nếu phần cứng được bật. `detach()` không được dùng để tuyên bố đã cắt dòng. Nếu không có phần cứng, CLOSED/OPEN là ước lượng thời gian 600 ms, không xác nhận tới vị trí và không phát hiện kẹt thật.

Khi cảm biến tay lỗi liên tiếp 3 mẫu: nếu nắp đã mở/di chuyển, phát lệnh mở và chốt FAULT; nếu đang đóng kín, giữ lệnh đóng và chốt FAULT. Đây là chính sách dừng đóng tự động cho nguyên mẫu, cần cơ cấu tự giữ/đối trọng và đánh giá thực tế. Cảm biến phía trước không quan sát được mọi vật ở khe nắp, không chứng minh chống kẹp. Không dùng tay để thử kẹt.

## Lịch đo, độ trễ và ẩm

Một slot 70 ms, thứ tự `tay, tay, tay, tay, rác`, mọi lần kích cách nhau ≥70 ms. `pulseIn` timeout 25.000 µs; không có hai lần đo nối sát nhau trong cùng slot. Khoảng cách giữa hai phép đo tay tối đa 140 ms, giữa hai phép đo rác 350 ms. Delay 2+10 µs chỉ tạo TRIG; control ngủ FreeRTOS 5 ms sau lượt, không chờ mạng. Median 3 tay có thể cần 2 mẫu sau chuyển vùng, warm-up cần đủ 3; ngân sách lý thuyết vài trăm ms, **chưa đo được mục tiêu ≤500 ms trên thiết bị**. Có thể phải thay thuật toán/tăng timeout nếu dữ liệu thực không đáp ứng.

Trimmed Mean 7 rác bỏ min/max lấy trung bình 5; cửa sổ phải đủ mẫu và mọi mẫu ≤3 giây. Thiếu cửa sổ là warming, lần lỗi là stale, 3 lỗi liên tiếp là fault. Mẫu ngoài 2–400 cm, không finite, hoặc lớn hơn `d_empty+10 cm` bị loại trước clamp. Ngưỡng 10 cm là guard thử nghiệm, cần chốt sau đo bố trí thực tế. Khi mở/chuyển nắp, xóa cửa sổ; sau đóng đợi 1 giây, rồi gom mẫu mới. Không tái sử dụng mẫu rác khi đầu đo đang xoay.

Đặt mạch trong hộp chống nước đọng, có đường thoát/thoáng phù hợp và đầu nối kín. Có thể phủ bảo vệ PCB theo vật liệu phù hợp, **không phủ kín mặt phát/thu siêu âm**. Không mặc định đổi sang JSN-SR04T hay model chống nước nào khi chưa kiểm tra vùng mù: nếu vùng mù gần 20 cm thì không phù hợp ngưỡng tay 20 cm và khoảng đầy 4 cm trong thùng 30 cm. Hiện chưa đề xuất một model thay thế đã được xác minh.

## Wokwi

`diagram.json` đã cấp hai HC-SR04 từ 5 V và vẽ hai bộ chia ECHO. Servo trong Wokwi vẫn nối rail 5V mô phỏng vì mô hình không chứng minh dòng nguồn; mạch thật dùng nhánh nguồn riêng như trên. Wokwi dùng DevKitC V4 trong khi build DOIT DevKit V1; cùng họ ESP32 và các số GPIO hiện hữu, nhưng khác bố trí chân/USB/nguồn. Không dùng vị trí hình học trong Wokwi làm pinout board thật. Mô phỏng điện trở không được coi là kiểm chứng analog/VOH hay bảo vệ dòng. Chưa chạy Wokwi sau sửa sơ đồ.

## Phiếu thử thiết bị do nhóm thực hiện

Ghi board, servo, nguồn, phiên bản firmware, thiết bị đo, tải nắp và điều kiện. Mỗi thử nghiệm cần số lần, timestamp, dữ liệu gốc và kết luận riêng.

1. Đo điện áp nguồn/ECHO trước cắm vào GPIO; xác minh GPIO bootstrap và chung GND. Xác minh servo không chạm chặn cơ khí ở 0/90°.
2. Hiệu chuẩn 30/4 theo **số đo thật**, thử mốc rỗng/80%/đầy và vật liệu rác phân bố khác nhau. Ghi sai số điểm phần trăm, báo nhầm, khoảng cách thô và sau lọc.
3. Đưa tay qua ngưỡng 20/25 cm, giữ tay, rời tay, quay lại khi đang đóng. Dùng timestamp/logic analyzer/video có đồng hồ để đo trễ; mục tiêu ban đầu ≤500 ms, chưa là kết quả.
4. Ngắt ECHO từng cảm biến, che đầu đo có kiểm soát, thử timeout. Xác minh unknown không thành 0%, nắp không tự coi sensor hỏng là người đã rời đi.
5. Tắt AP; có Wi-Fi nhưng chặn Internet; trì hoãn broker/TLS/SNTP. Đo phản ứng nắp đồng thời, heap thấp nhất và stack high-water mark.
6. Offline → FULL → CLEARED → reset → nối lại. Kiểm tra ID, lịch sử, độ trễ gửi bù, không đảo trạng thái, mất ACK/trùng ACK; cắt nguồn có kiểm soát để thử hai bank, không xóa NVS tùy tiện.
7. Chỉ thử kẹt sau lắp bảo vệ phù hợp, dùng đồ gá giới hạn lực/dòng, không dùng tay. Ghi dòng startup/kẹt, thời gian ngắt, điện áp ESP32 và nhiệt; xác minh driver thật ngắt nguồn.
8. Chạy bền 24 giờ nếu có điều kiện; ghi số reset, min heap/stack, queue/dropped, báo nhầm, nhiệt và bất thường. Không điền số liệu khi chưa chạy.
