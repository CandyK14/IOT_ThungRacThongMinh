#pragma once
// Sao chép thành mqtt_config.h; không ghi đè cấu hình riêng config.h.
#define BIN_ID "bin-001"
#define MQTT_URI "mqtts://broker.local:8883"
#define MQTT_USERNAME BIN_ID
#define MQTT_PASSWORD "REPLACE_DEVICE_PASSWORD"
// CA PEM của broker; hostname phải khớp SAN. Trống => chỉ chạy cục bộ.
#define MQTT_CA_PEM ""
#define EMPTY_DISTANCE_CM 30.0f
#define FULL_DISTANCE_CM 4.0f
#define FILL_SENSOR_ON_LID 1
#define FULL_ON_PERCENT 80.0f
#define FULL_OFF_PERCENT 75.0f
#define FULL_CONFIRMATIONS 3
#define HEARTBEAT_MS 60000UL
#define SERVO_PROTECTION_ENABLED 0
// Khi bật: cần hiệu chuẩn cảm biến dòng analog; hai công tắc active LOW;
// driver cắt nguồn active HIGH. Chân bổ sung GPIO34 / 32 / 33 / 26.
#define SERVO_CURRENT_ZERO_MV 0.0f
#define SERVO_CURRENT_MA_PER_MV 0.0f
#define SERVO_TRIP_MA 0.0f
