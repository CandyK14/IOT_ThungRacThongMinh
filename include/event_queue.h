#pragma once
#include "bin_logic.h"
#include <cstddef>
#include <cstring>

namespace smartbin {
// 32 durable events + one in-flight telemetry + one fresh telemetry.
constexpr int MAX_QUEUE=34,PERSIST_EVENTS=32;
enum class Quality:uint8_t {VALID,WARMING,STALE,FAULT,LID_OPEN};
enum class Event:uint8_t {NONE,FULL,CLEARED,FAULT,RECOVERED};
struct Record {
  uint32_t seq,bootNo; char bootId[25]; uint64_t uptime; int64_t sampledAt;
  float fill,distance; uint32_t openCount; Lid lid; Quality quality; Event event;
  uint32_t dropped,reconnects,offlineMs,depth;
  float fullOn,fullOff;
};
struct Ack {char bootId[25];uint32_t seq;};
inline bool matches(const Record &r,const Ack &a) {return r.seq==a.seq && std::strcmp(r.bootId,a.bootId)==0;}
struct Outbox {
  Record records[MAX_QUEUE]{};int count=0;uint32_t dropped=0;
  void erase(int i) {for(int k=i+1;k<count;++k)records[k-1]=records[k];--count;}
  bool push(const Record &r,const Ack &inFlight,bool sending) {
    if(r.event==Event::NONE) {
      for(int i=count-1;i>=0;--i)if(records[i].event==Event::NONE && !(sending && matches(records[i],inFlight)))erase(i);
    }
    int events=0;for(int i=0;i<count;++i)events+=records[i].event!=Event::NONE;
    if(r.event!=Event::NONE && events>=PERSIST_EVENTS){++dropped;return false;}
    if(count>=MAX_QUEUE){++dropped;return false;}
    records[count++]=r;return true;
  }
};
struct Journal {uint32_t magic,generation,count,checksum;Record records[PERSIST_EVENTS];};
inline uint32_t journalChecksum(const Journal &j) {
  uint32_t h=2166136261UL;const auto *b=reinterpret_cast<const uint8_t*>(&j);
  for(size_t i=0;i<sizeof(Journal);++i){if(i>=offsetof(Journal,checksum) && i<offsetof(Journal,checksum)+4)continue;h=(h^b[i])*16777619UL;}
  return h;
}
inline bool journalValid(const Journal &j) {return j.magic==0xB1700001 && j.count<=PERSIST_EVENTS && j.checksum==journalChecksum(j);}
inline bool firstJournalNewer(const Journal &a,const Journal &b) {return int32_t(a.generation-b.generation)>0;}
inline bool makeJournal(const Outbox &box,uint32_t generation,Journal &j) {
  std::memset(&j,0,sizeof(j));j.magic=0xB1700001;j.generation=generation;
  for(int i=0;i<box.count;++i)if(box.records[i].event!=Event::NONE) {
    if(j.count==PERSIST_EVENTS)return false;j.records[j.count++]=box.records[i];
  }
  j.checksum=journalChecksum(j);return true;
}
}
