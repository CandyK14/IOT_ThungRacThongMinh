#pragma once
// Chỉ đọc Wi-Fi từ config.h hiện hữu; bot Telegram đã chuyển về backend.
#if __has_include("config.h")
#include "config.h"
#else
static const char *WIFI_SSID="Wokwi-GUEST", *WIFI_PASS="";
#endif
#if __has_include("mqtt_config.h")
#include "mqtt_config.h"
#else
#include "mqtt_config.example.h"
#endif
