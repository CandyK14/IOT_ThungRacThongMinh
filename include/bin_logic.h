#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace smartbin {
inline uint32_t elapsed(uint32_t now, uint32_t then) { return now - then; }
struct Calibration {
  float empty = 30, full = 4;
  Calibration() = default;
  Calibration(float e,float f):empty(e),full(f){}
  bool valid() const { return std::isfinite(empty) && std::isfinite(full) && full >= 2 && empty <= 400 && empty > full; }
  bool convert(float d, float &pct) const {
    if (!valid() || !std::isfinite(d) || d < 2 || d > 400 || d > empty + 10) return false;
    pct = std::max(0.f, std::min(100.f, 100 * (empty-d)/(empty-full)));
    return true;
  }
};
template<int N> class Window {
  static_assert(N>=3,"Filter window must have at least 3 samples");
  float values[N]{}; uint32_t times[N]{}; int count=0, next=0;
 public:
  void clear() { count=next=0; }
  void push(float v, uint32_t now) { values[next]=v; times[next]=now; next=(next+1)%N; if(count<N) ++count; }
  bool filtered(uint32_t now, uint32_t maxAge, float &out) const {
    if(count<N) return false;
    float sorted[N];
    for(int i=0;i<N;++i) { if(elapsed(now,times[i])>maxAge) return false; sorted[i]=values[i]; }
    std::sort(sorted,sorted+N);
    if(N==3) out=sorted[1];
    else { out=0; for(int i=1;i<N-1;++i) out+=sorted[i]; out/=N-2; }
    return true;
  }
};
struct Hysteresis {
  bool full=false; int high=0,low=0; float on=80,off=75; int confirmations=3;
  void invalid() { high=low=0; }
  int update(float p, bool valid) {
    if(!valid) { invalid(); return 0; }
    high=p>=on ? std::min(high+1,confirmations):0; low=p<=off ? std::min(low+1,confirmations):0;
    if(!full && high>=confirmations) { full=true; return 1; }
    if(full && low>=confirmations) { full=false; return -1; }
    return 0;
  }
};
struct MeasurementHealth {
  int failures=0;bool fault=false;
  void sample(bool rawValid,bool filteredReady) {
    failures=rawValid?0:std::min(3,failures+1);
    if(failures>=3)fault=true;
    if(rawValid && filteredReady)fault=false;
  }
  // No sample while the sensor is suspended: fault deliberately remains latched.
};
enum class Lid { CLOSED,OPENING,OPEN,CLOSING,FAULT };
inline const char *lidName(Lid s) {
  switch(s) { case Lid::CLOSED:return "CLOSED"; case Lid::OPENING:return "OPENING";
    case Lid::OPEN:return "OPEN"; case Lid::CLOSING:return "CLOSING"; default:return "FAULT"; }
}
struct ProtectionInput {
  bool currentAvailable=false, limitsAvailable=false, powerSwitchAvailable=false;
  float currentMa=0; bool atOpen=false, atClosed=false;
};
struct Protection {
  float tripMa=0; uint32_t startupMs=200, sustainedMs=200, travelTimeoutMs=1500;
  bool latched=false, over=false; uint32_t overSince=0;
  bool update(uint32_t now,uint32_t movementStart,bool moving,bool opening,const ProtectionInput &p) {
    if(latched) return true;
    if(p.currentAvailable && tripMa>0 && p.currentMa>=tripMa && (!moving || elapsed(now,movementStart)>=startupMs)) {
      if(!over) {over=true;overSince=now;}
      if(elapsed(now,overSince)>=sustainedMs) latched=true;
    } else over=false;
    if(p.limitsAvailable && p.atOpen && p.atClosed) latched=true;
    if(moving && p.limitsAvailable && elapsed(now,movementStart)>=travelTimeoutMs && !(opening?p.atOpen:p.atClosed)) latched=true;
    return latched;
  }
  void reset() {latched=over=false;}
};
struct LidController {
  Lid state=Lid::CLOSED; uint32_t lastSeen=0,moveStart=0,closedAt=0,openCount=0;
  uint32_t holdMs=3000,travelMs=600; int closedAngle=0,openAngle=90,angle=0;
  bool seen=false; Protection protection;
  void fault() { if(state!=Lid::CLOSED) angle=openAngle; state=Lid::FAULT; }
  void tick(uint32_t now,float distance,bool handValid,bool handFault,const ProtectionInput &p={}) {
    if(state==Lid::FAULT) return;
    bool moving=state==Lid::OPENING || state==Lid::CLOSING;
    if(protection.update(now,moveStart,moving,state==Lid::OPENING,p)) {fault();return;}
    if(handFault) {fault();return;}
    const bool detected=handValid && distance<(state==Lid::CLOSED?20.f:25.f);
    if(detected) {seen=true;lastSeen=now;}
    if(detected && (state==Lid::CLOSED || state==Lid::CLOSING)) {
      state=Lid::OPENING;moveStart=now;++openCount;
    }
    if(state==Lid::OPENING || state==Lid::CLOSING) {
      bool opening=state==Lid::OPENING;
      bool reached=p.limitsAvailable ? (opening?p.atOpen:p.atClosed) : elapsed(now,moveStart)>=travelMs;
      angle=opening?openAngle:closedAngle;
      if(reached) {state=opening?Lid::OPEN:Lid::CLOSED; if(!opening)closedAt=now;}
    } else if(state==Lid::OPEN && handValid && seen && elapsed(now,lastSeen)>=holdMs) {
      state=Lid::CLOSING;moveStart=now;angle=closedAngle;
    }
  }
  bool reset(bool handValid,bool handFar,const ProtectionInput &p) {
    if(state!=Lid::FAULT || !handValid || !handFar || (p.currentAvailable && p.currentMa>=protection.tripMa) ||
       (p.limitsAvailable && !p.atOpen && !p.atClosed) || (p.atOpen && p.atClosed)) return false;
    protection.reset();state=p.limitsAvailable?(p.atOpen?Lid::OPEN:Lid::CLOSED):(angle==openAngle?Lid::OPEN:Lid::CLOSED);
    angle=state==Lid::OPEN?openAngle:closedAngle;seen=true;return true;
  }
};
} // namespace smartbin
