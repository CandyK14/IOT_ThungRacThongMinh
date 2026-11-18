#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <Preferences.h>
#include <WiFi.h>
#include <atomic>
#include <esp_timer.h>
#include <mqtt_client.h>
#include <time.h>
#include "bin_logic.h"
#include "event_queue.h"
#include "settings.h"

using namespace smartbin;
namespace {
constexpr int TRIG_LID=5,ECHO_LID=18,TRIG_FILL=19,ECHO_FILL=21,SERVO_PIN=13,LED_RED=2,LED_GREEN=4;
constexpr int CURRENT_PIN=34,OPEN_LIMIT_PIN=32,CLOSED_LIMIT_PIN=33,POWER_PIN=26;
constexpr uint32_t PULSE_TIMEOUT_US=25000,SLOT_MS=70,FILL_SETTLE_MS=1000;
static_assert(HEARTBEAT_MS>=1000 && HEARTBEAT_MS<0x80000000UL,"Heartbeat invalid");
static_assert(EMPTY_DISTANCE_CM>FULL_DISTANCE_CM && FULL_DISTANCE_CM>=2 && EMPTY_DISTANCE_CM<=400,"Calibration invalid");
static_assert(FULL_ON_PERCENT>FULL_OFF_PERCENT && FULL_ON_PERCENT<=100 && FULL_OFF_PERCENT>=0,"Threshold invalid");
static_assert(FULL_CONFIRMATIONS>0 && FULL_CONFIRMATIONS<=100,"Confirmations invalid");
#if SERVO_PROTECTION_ENABLED
static_assert(SERVO_TRIP_MA>0 && SERVO_CURRENT_MA_PER_MV>0,"Calibrate current protection first");
#endif
const char *qualityName(Quality q) {
  switch(q){case Quality::VALID:return "valid";case Quality::WARMING:return "warming";
    case Quality::STALE:return "stale";case Quality::FAULT:return "fault";default:return "lid_open";}
}
const char *eventName(Event e){switch(e){case Event::FULL:return "FULL";case Event::CLEARED:return "CLEARED";case Event::FAULT:return "FAULT";default:return "RECOVERED";}}
static Outbox outbox;
auto &pending=outbox.records;int &pendingCount=outbox.count;
QueueHandle_t samples,acks; SemaphoreHandle_t statsMutex;
struct Stats {uint32_t dropped=0,reconnects=0,offlineMs=0,depth=0;bool storageFault=false;} stats;
uint32_t bootNo=0,seq=0; char bootId[25];
std::atomic<bool> mqttConnected{false};
esp_mqtt_client_handle_t client=nullptr;
String dataTopic,eventTopic,ackTopic;
String brokerCA(MQTT_CA_PEM);
Preferences prefs;uint32_t generation=0; int activeBank=-1;

bool readBank(const char *key,Journal &j) {
  return prefs.getBytesLength(key)==sizeof(j) && prefs.getBytes(key,&j,sizeof(j))==sizeof(j) && journalValid(j);
}
bool persist() {
  static Journal j;if(!makeJournal(outbox,generation+1,j))return false;
  const char *key=activeBank==0?"bank1":"bank0";
  if(prefs.putBytes(key,&j,sizeof(j))!=sizeof(j))return false;
  generation=j.generation;activeBank=activeBank==0?1:0;return true;
}
void restore() {
  static Journal a,b;bool va=readBank("bank0",a),vb=readBank("bank1",b);
  if(!va&&!vb) {
    if(prefs.getBytesLength("bank0") || prefs.getBytesLength("bank1")){xSemaphoreTake(statsMutex,portMAX_DELAY);stats.storageFault=true;xSemaphoreGive(statsMutex);}
    return;
  }
  Journal &chosen=va&&(!vb || firstJournalNewer(a,b))?a:b;
  activeBank=&chosen==&a?0:1;generation=chosen.generation;
  for(uint32_t i=0;i<chosen.count;++i)pending[pendingCount++]=chosen.records[i];
}
bool distance(int trig,int echo,float &d) {
  digitalWrite(trig,LOW);delayMicroseconds(2);digitalWrite(trig,HIGH);delayMicroseconds(10);digitalWrite(trig,LOW);
  uint32_t us=pulseIn(echo,HIGH,PULSE_TIMEOUT_US); d=us*0.0343f/2;
  return us && d>=2 && d<=400;
}
ProtectionInput protectionInput() {
  ProtectionInput p;
#if SERVO_PROTECTION_ENABLED
  p.currentAvailable=p.limitsAvailable=p.powerSwitchAvailable=true;
  p.currentMa=std::max(0.f,(analogReadMilliVolts(CURRENT_PIN)-SERVO_CURRENT_ZERO_MV)*SERVO_CURRENT_MA_PER_MV);
  p.atOpen=digitalRead(OPEN_LIMIT_PIN)==LOW;p.atClosed=digitalRead(CLOSED_LIMIT_PIN)==LOW;
#endif
  return p;
}
void emit(Event e,float fill,float d,Quality q,const LidController &lid) {
  if(seq==UINT32_MAX) {xSemaphoreTake(statsMutex,portMAX_DELAY);stats.storageFault=true;xSemaphoreGive(statsMutex);return;}
  Record r{};r.seq=++seq;r.bootNo=bootNo;strlcpy(r.bootId,bootId,sizeof(r.bootId));
  r.uptime=esp_timer_get_time()/1000;time_t utc=time(nullptr);r.sampledAt=utc>1700000000?utc:0;
  r.fill=fill;r.distance=d;r.quality=q;r.event=e;r.lid=lid.state;r.openCount=lid.openCount;
  r.fullOn=FULL_ON_PERCENT;r.fullOff=FULL_OFF_PERCENT;
  xSemaphoreTake(statsMutex,portMAX_DELAY);r.dropped=stats.dropped;r.reconnects=stats.reconnects;r.offlineMs=stats.offlineMs;r.depth=stats.depth;xSemaphoreGive(statsMutex);
  if(e!=Event::NONE) {
    if(q==Quality::VALID)Serial.printf("[Su kien cuc bo] %s | fill=%.1f%% | sensor=%s\n",eventName(e),fill,qualityName(q));
    else Serial.printf("[Su kien cuc bo] %s | fill=unknown | sensor=%s\n",eventName(e),qualityName(q));
  }
  if(xQueueSend(samples,&r,0)!=pdTRUE){xSemaphoreTake(statsMutex,portMAX_DELAY);++stats.dropped;xSemaphoreGive(statsMutex);}
}
void controlTask(void*) {
  Servo servo;servo.setPeriodHertz(50);servo.attach(SERVO_PIN,500,2400);servo.write(0);
  LidController lid;lid.protection.tripMa=SERVO_TRIP_MA;
#if SERVO_PROTECTION_ENABLED
  ProtectionInput startup=protectionInput();
  if(!startup.atClosed || startup.atOpen){lid.protection.latched=true;lid.fault();}
#endif
  Window<3> hands;Window<7> fills;Calibration calibration{EMPTY_DISTANCE_CM,FULL_DISTANCE_CM};
  Hysteresis threshold;threshold.on=FULL_ON_PERCENT;threshold.off=FULL_OFF_PERCENT;threshold.confirmations=FULL_CONFIRMATIONS;
  uint32_t slotAt=millis(),beatAt=millis()-HEARTBEAT_MS;int slot=0,handFailures=0;
  MeasurementHealth fillHealth;
  float hand=0,fill=0,filtered=0;bool handValid=false;Quality q=Quality::WARMING;
  bool reportedFault=false;Lid previous=lid.state;
  for(;;) {
    uint32_t now=millis();
    if(elapsed(now,slotAt)>=SLOT_MS) {
      slotAt=now;float raw;
      if(slot==4) {
        bool allowed=!FILL_SENSOR_ON_LID || (lid.state==Lid::CLOSED && elapsed(now,lid.closedAt)>=FILL_SETTLE_MS);
        if(!allowed){fills.clear();q=Quality::LID_OPEN;threshold.invalid();}
        else {
          bool ok=distance(TRIG_FILL,ECHO_FILL,raw);float converted;ok=ok && calibration.convert(raw,converted);
          if(ok){fills.push(raw,now);}else threshold.invalid();
          bool ready=ok && fills.filtered(now,3000,filtered) && calibration.convert(filtered,fill);
          fillHealth.sample(ok,ready);
          q=fillHealth.fault?Quality::FAULT:ready?Quality::VALID:!ok?Quality::STALE:Quality::WARMING;
          if(ready){int change=threshold.update(fill,true);if(change)emit(change>0?Event::FULL:Event::CLEARED,fill,filtered,q,lid);}
        }
      } else {
        bool ok=distance(TRIG_LID,ECHO_LID,raw);
        if(ok){handFailures=0;hands.push(raw,now);}else handFailures=std::min(3,handFailures+1);
        handValid=ok && hands.filtered(now,500,hand);
      }
      slot=(slot+1)%5;
    }
    ProtectionInput p=protectionInput();lid.tick(now,hand,handValid,handFailures>=3,p);
    if(previous!=lid.state)Serial.printf("[Nap] %s -> %s\n",lidName(previous),lidName(lid.state));
    if(previous!=lid.state && FILL_SENSOR_ON_LID){fills.clear();q=Quality::LID_OPEN;threshold.invalid();}
    previous=lid.state;servo.write(constrain(lid.angle,0,90));
#if SERVO_PROTECTION_ENABLED
    digitalWrite(POWER_PIN,lid.protection.latched?LOW:HIGH);
#endif
    // Suspending an on-lid sensor must not falsely announce recovery from a sensor fault.
    bool fault=fillHealth.fault || lid.state==Lid::FAULT;
    if(fault!=reportedFault){emit(fault?Event::FAULT:Event::RECOVERED,fill,filtered,q,lid);reportedFault=fault;}
    if(Serial.available() && Serial.read()=='r' && handFailures==0 && handValid && hand>=25) {
      if(lid.reset(true,true,p)){lid.lastSeen=now;Serial.println("[Nap] Da reset loi; can kiem tra co khi truoc.");}
    }
    bool sf; xSemaphoreTake(statsMutex,portMAX_DELAY);sf=stats.storageFault;xSemaphoreGive(statsMutex);
    digitalWrite(LED_RED,threshold.full || fault || sf || q!=Quality::VALID);
    digitalWrite(LED_GREEN,!threshold.full || fault || sf || q!=Quality::VALID);
    if(elapsed(now,beatAt)>=HEARTBEAT_MS){beatAt=now;emit(Event::NONE,fill,filtered,q,lid);}
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}
esp_err_t mqttEvent(esp_mqtt_event_handle_t e) {
  if(e->event_id==MQTT_EVENT_CONNECTED) {mqttConnected=true;esp_mqtt_client_subscribe(client,ackTopic.c_str(),1);}
  if(e->event_id==MQTT_EVENT_DISCONNECTED)mqttConnected=false;
  if(e->event_id==MQTT_EVENT_DATA && e->current_data_offset==0 && e->data_len==e->total_data_len && e->data_len<256 &&
     size_t(e->topic_len)==ackTopic.length() && memcmp(e->topic,ackTopic.c_str(),e->topic_len)==0) {
    JsonDocument doc;
    if(!deserializeJson(doc,e->data,e->data_len) && doc["stored"]==true && doc["bin_id"]==BIN_ID) {
      Ack a{};strlcpy(a.bootId,doc["boot_id"]|"",sizeof(a.bootId));a.seq=doc["seq"]|0U;xQueueSend(acks,&a,0);
    }
  }
  return ESP_OK;
}
size_t serialize(const Record &r,char *buffer,size_t size) {
  JsonDocument j;j["version"]=1;j["bin_id"]=BIN_ID;j["boot_id"]=r.bootId;j["boot_no"]=r.bootNo;j["seq"]=r.seq;
  j["kind"]=r.event==Event::NONE?"telemetry":"event";if(r.event!=Event::NONE)j["event_type"]=eventName(r.event);
  j["source"]="real";j["uptime_ms"]=r.uptime;
  if(r.sampledAt){time_t utc=r.sampledAt;tm t;gmtime_r(&utc,&t);char date[25];strftime(date,sizeof(date),"%Y-%m-%dT%H:%M:%SZ",&t);j["sampled_at"]=date;j["time_quality"]="sntp";}
  else{j["sampled_at"]=nullptr;j["time_quality"]="unknown";}
  j["quality"]=qualityName(r.quality);
  j["full_on_pct"]=r.fullOn;j["full_off_pct"]=r.fullOff;
  if(r.quality==Quality::VALID){j["fill_pct"]=r.fill;j["distance_cm"]=r.distance;}
  else{j["fill_pct"]=nullptr;j["distance_cm"]=nullptr;}
  j["lid_state"]=lidName(r.lid);j["lid_open_count"]=r.openCount;j["battery_mv"]=nullptr;
  // Snapshot metrics are immutable across retries and reset recovery.
  j["queue_depth"]=r.depth;j["dropped_records"]=r.dropped;j["reconnects"]=r.reconnects;j["offline_ms"]=r.offlineMs;
  return serializeJson(j,buffer,size);
}
void networkTask(void*) {
  if(brokerCA.length()==0)Serial.println("[Mang] Chua cau hinh CA MQTT: thu nap/LED/Serial cuc bo; chua gui backend/Telegram.");
  bool nvs=prefs.begin("binqueue",false);if(nvs)restore();else{xSemaphoreTake(statsMutex,portMAX_DELAY);stats.storageFault=true;xSemaphoreGive(statsMutex);}
  uint32_t lastWifi=millis()-10000,lastReconnect=0,lastPublish=millis()-1000,lastLog=0,backoff=1000,offlineAt=millis();
  bool wasConnected=false,started=false;uint32_t sendBackoff=1000;
  static char payload[2048];size_t payloadLen=0;Ack inFlight{};
  for(;;) {
    uint32_t now=millis();Record r;
    for(int n=0;n<8 && xQueueReceive(samples,&r,0)==pdTRUE;++n) {
      if(!outbox.push(r,inFlight,payloadLen>0)) {
        xSemaphoreTake(statsMutex,portMAX_DELAY);++stats.dropped;stats.storageFault|=r.event!=Event::NONE;xSemaphoreGive(statsMutex);
      } else if(r.event!=Event::NONE && (!nvs || !persist())){xSemaphoreTake(statsMutex,portMAX_DELAY);stats.storageFault=true;xSemaphoreGive(statsMutex);}
    }
    Ack a;
    while(xQueueReceive(acks,&a,0)==pdTRUE) {
      if(!payloadLen || a.seq!=inFlight.seq || strcmp(a.bootId,inFlight.bootId)!=0)continue;
      for(int i=0;i<pendingCount;++i)if(pending[i].seq==a.seq && strcmp(pending[i].bootId,a.bootId)==0) {
        bool durable=pending[i].event!=Event::NONE;Record removed=pending[i];
        for(int k=i+1;k<pendingCount;++k)pending[k-1]=pending[k];--pendingCount;
        if(durable && (!nvs || !persist())) {pending[pendingCount++]=removed;xSemaphoreTake(statsMutex,portMAX_DELAY);stats.storageFault=true;xSemaphoreGive(statsMutex);}
        payloadLen=0;sendBackoff=1000;break;
      }
    }
    if(WiFi.status()!=WL_CONNECTED && elapsed(now,lastWifi)>=10000) {lastWifi=now;WiFi.begin(WIFI_SSID,WIFI_PASS);}
    if(WiFi.status()==WL_CONNECTED && !started && brokerCA.length()>0 && time(nullptr)>1700000000) {
      esp_mqtt_client_config_t cfg{};cfg.uri=MQTT_URI;cfg.username=MQTT_USERNAME;cfg.password=MQTT_PASSWORD;cfg.client_id=BIN_ID;
      cfg.cert_pem=brokerCA.c_str();cfg.skip_cert_common_name_check=false;cfg.event_handle=mqttEvent;
      cfg.disable_auto_reconnect=true;cfg.network_timeout_ms=4000;cfg.keepalive=60;cfg.task_stack=6144;cfg.buffer_size=2048;
      if(String(MQTT_URI).startsWith("mqtts://")) {client=esp_mqtt_client_init(&cfg);if(client){esp_mqtt_client_start(client);started=true;lastReconnect=now;}}
    }
    if(started && !mqttConnected && elapsed(now,lastReconnect)>=backoff) {
      lastReconnect=now;esp_mqtt_client_reconnect(client);backoff=std::min(uint32_t(60000),backoff*2)+esp_random()%500;
      xSemaphoreTake(statsMutex,portMAX_DELAY);++stats.reconnects;xSemaphoreGive(statsMutex);
    }
    bool connected=mqttConnected;
    if(connected)backoff=1000;
    if(!connected && wasConnected)offlineAt=now;
    xSemaphoreTake(statsMutex,portMAX_DELAY);stats.depth=pendingCount;if(!connected)stats.offlineMs=elapsed(now,offlineAt);xSemaphoreGive(statsMutex);
    wasConnected=connected;
    if(connected && pendingCount && elapsed(now,lastPublish)>=sendBackoff) {
      if(!payloadLen) {inFlight.seq=pending[0].seq;strlcpy(inFlight.bootId,pending[0].bootId,sizeof(inFlight.bootId));payloadLen=serialize(pending[0],payload,sizeof(payload));}
      // Bound the SDK's dynamic QoS outbox as well as our own fixed application queue.
      if(payloadLen<sizeof(payload)-1 && esp_mqtt_client_get_outbox_size(client)+int(payloadLen)<=4096)
        esp_mqtt_client_publish(client,pending[0].event==Event::NONE?dataTopic.c_str():eventTopic.c_str(),payload,payloadLen,1,0);
      lastPublish=now;sendBackoff=std::min(uint32_t(30000),sendBackoff*2)+esp_random()%200;
    }
    if(elapsed(now,lastLog)>=30000) {lastLog=now;Serial.printf("[Mang] mqtt=%d queue=%d heap=%u stack=%u record=%u journal=%u\n",connected,pendingCount,ESP.getFreeHeap(),uxTaskGetStackHighWaterMark(nullptr),unsigned(sizeof(Record)),unsigned(sizeof(Journal)));}
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}
}
void setup() {
  Serial.begin(115200);
  for(int p:{TRIG_LID,TRIG_FILL,LED_RED,LED_GREEN})pinMode(p,OUTPUT);
  pinMode(ECHO_LID,INPUT);pinMode(ECHO_FILL,INPUT);
#if SERVO_PROTECTION_ENABLED
  pinMode(POWER_PIN,OUTPUT);digitalWrite(POWER_PIN,LOW);pinMode(OPEN_LIMIT_PIN,INPUT_PULLUP);pinMode(CLOSED_LIMIT_PIN,INPUT_PULLUP);
#endif
  Preferences bootPrefs;
  if(!bootPrefs.begin("binboot",false)){Serial.println("[LOI] NVS khong san sang; khong khoi dong servo.");return;}
  uint32_t previous=bootPrefs.getUInt("number",0);
  if(previous==UINT32_MAX || bootPrefs.putUInt("number",previous+1)!=sizeof(uint32_t)){Serial.println("[LOI] Khong luu duoc boot_no; khong khoi dong servo.");return;}
  bootNo=previous+1;bootPrefs.end();snprintf(bootId,sizeof(bootId),"%08lx-%08lx",(unsigned long)bootNo,(unsigned long)esp_random());
  dataTopic=String("v1/bins/")+BIN_ID+"/telemetry";eventTopic=String("v1/bins/")+BIN_ID+"/events";ackTopic=String("v1/bins/")+BIN_ID+"/ack";
  samples=xQueueCreate(16,sizeof(Record));acks=xQueueCreate(8,sizeof(Ack));statsMutex=xSemaphoreCreateMutex();
  if(!samples || !acks || !statsMutex){Serial.println("[LOI] Khong du RAM cho queue.");return;}
  WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);configTime(0,0,"pool.ntp.org","time.google.com");
  if(xTaskCreatePinnedToCore(controlTask,"control",6144,nullptr,3,nullptr,1)!=pdPASS ||
     xTaskCreatePinnedToCore(networkTask,"network",12288,nullptr,1,nullptr,0)!=pdPASS)Serial.println("[LOI] Tao task that bai.");
}
void loop(){vTaskDelay(pdMS_TO_TICKS(1000));}
