#include "bin_logic.h"
#include "event_queue.h"
#include <cassert>
#include <cstring>
#include <iostream>
using namespace smartbin;
int main(){
  float p=0;Calibration c(30,4);assert(c.convert(30,p)&&p==0);assert(c.convert(4,p)&&p==100);
  assert(c.convert(9.2,p)&&std::abs(p-80)<.01);assert(!c.convert(1,p));assert(!c.convert(300,p));
  assert(!Calibration(4,30).valid());assert(!Calibration(NAN,4).valid());
  Window<7> w;float f;for(int i=0;i<6;++i)w.push(10,100+i*10);assert(!w.filtered(160,1000,f));
  w.push(100,160);assert(w.filtered(160,1000,f)&&f==10);assert(!w.filtered(2000,1000,f));
  Window<3> hands;hands.push(10,UINT32_MAX-50);hands.push(10,UINT32_MAX-20);hands.push(100,5);
  assert(hands.filtered(10,100,f)&&f==10);assert(elapsed(10,UINT32_MAX-10)==21);
  Hysteresis h;assert(!h.update(81,true));assert(!h.update(81,true));h.update(0,false);
  assert(!h.update(81,true));assert(!h.update(81,true));assert(h.update(81,true)==1);
  for(int i=0;i<10;++i)assert(h.update(79,true)==0);assert(h.full);
  assert(!h.update(75,true));assert(!h.update(75,true));assert(h.update(75,true)==-1);
  MeasurementHealth health;health.sample(false,false);health.sample(false,false);health.sample(false,false);
  assert(health.fault);
  Window<7> recoveryWindow; // Lid opens: no samples, old window discarded, fault must persist.
  recoveryWindow.clear();assert(health.fault);
  health.sample(true,false);assert(health.fault); // A single new raw value is not full recovery.
  for(int i=0;i<7;++i)recoveryWindow.push(12,100+i*10);
  bool recovered=recoveryWindow.filtered(170,1000,f);health.sample(true,recovered);assert(!health.fault);
  LidController lid;lid.tick(100,10,true,false);assert(lid.state==Lid::OPENING&&lid.angle==90);
  lid.tick(700,10,true,false);assert(lid.state==Lid::OPEN&&lid.openCount==1);
  lid.tick(3600,40,true,false);assert(lid.state==Lid::OPEN);
  lid.tick(3701,40,false,false);assert(lid.state==Lid::OPEN); // invalid != person gone
  lid.tick(3702,40,true,false);assert(lid.state==Lid::CLOSING);
  lid.tick(3800,10,true,false);assert(lid.state==Lid::OPENING); // reverse when hand returns
  lid.tick(3801,10,false,true);assert(lid.state==Lid::FAULT&&lid.angle==90);
  assert(!lid.reset(false,true,{}));assert(lid.reset(true,true,{}));
  Protection protection;protection.tripMa=1000;ProtectionInput input;
  input.currentAvailable=input.powerSwitchAvailable=true;input.currentMa=1500;
  assert(!protection.update(50,0,true,true,input));assert(!protection.update(150,0,true,true,input));
  input.currentMa=500;assert(!protection.update(200,0,true,true,input));
  input.currentMa=1500;assert(!protection.update(300,0,true,true,input));
  assert(!protection.update(499,0,true,true,input));assert(protection.update(500,0,true,true,input));
  input.currentMa=0;assert(protection.update(600,0,false,false,input));protection.reset();
  input.limitsAvailable=true;assert(protection.update(1600,0,true,true,input));
  Outbox box;Record full{};full.event=Event::FULL;full.seq=1;full.bootNo=1;std::strcpy(full.bootId,"boot-before-reset");
  Record clear=full;clear.event=Event::CLEARED;clear.seq=2;
  Ack none{};assert(box.push(full,none,false));assert(box.push(clear,none,false));
  Record tele=full;tele.event=Event::NONE;tele.seq=3;box.push(tele,none,false);tele.seq=4;box.push(tele,none,false);
  assert(box.count==3&&box.records[2].seq==4); // telemetry coalesces; FULL/CLEARED remain ordered
  Ack inFlight{};std::strcpy(inFlight.bootId,tele.bootId);inFlight.seq=4;tele.seq=5;box.push(tele,inFlight,true);
  assert(box.count==4&&box.records[2].seq==4); // in-flight payload cannot mutate
  Journal oldBank{},newBank{};assert(makeJournal(box,1,oldBank));assert(oldBank.count==2&&journalValid(oldBank));
  assert(makeJournal(box,2,newBank)&&firstJournalNewer(newBank,oldBank));
  reinterpret_cast<unsigned char*>(&newBank)[sizeof(Journal)-1]^=1;assert(!journalValid(newBank)&&journalValid(oldBank));
  Outbox restored;for(uint32_t i=0;i<oldBank.count;++i)restored.push(oldBank.records[i],none,false);
  assert(restored.count==2&&matches(restored.records[0],Ack{"boot-before-reset",1}));
  for(int i=2;i<PERSIST_EVENTS;++i){full.seq=i+1;assert(restored.push(full,none,false));}
  assert(!restored.push(full,none,false)&&restored.dropped==1);assert(restored.count==32);
  Ack ack{"boot-before-reset",1};assert(matches(restored.records[0],ack));restored.erase(0);
  assert(!matches(restored.records[0],ack)); // repeated application ACK cannot remove the next event
  assert(makeJournal(restored,3,newBank));assert(newBank.count==31);
  std::cout<<"Firmware logic PASS; sizeof(record)="<<sizeof(Record)<<"; queue="<<sizeof(Outbox)<<"; journal="<<sizeof(Journal)<<"\n";
}
