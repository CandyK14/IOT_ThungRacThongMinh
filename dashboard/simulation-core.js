/* Behavioral browser model. This does not execute the ESP32 firmware. */
(function (root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.SmartBinSimulation = value;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  class Window {
    constructor(size, age) { this.size = size; this.age = age; this.items = []; }
    clear() { this.items = []; }
    push(value, now) { this.items.push({ value, now }); if (this.items.length > this.size) this.items.shift(); }
    read(now) {
      if (this.items.length < this.size || this.items.some(s => now - s.now > this.age)) return null;
      const v = this.items.map(s => s.value).sort((a, b) => a - b);
      return this.size === 3 ? v[1] : v.slice(1, -1).reduce((a, b) => a + b, 0) / (v.length - 2);
    }
  }
  class BinSimulation {
    constructor(options = {}) {
      this.now = 0; this.handDistance = 100; this.physicalFill = options.fill === undefined ? 22 : clamp(options.fill, 0, 100);
      this.handSensorFault = false; this.fillSensorFault = false; this.noise = false;
      this.lid = 'CLOSED'; this.commandAngle = 0; this.servoAngle = 0; this.openCount = 0;
      this.moveAt = 0; this.closedAt = 0; this.lastSeen = 0; this.seen = false;
      this.handWindow = new Window(3, 500); this.fillWindow = new Window(7, 3000);
      this.handFailures = 0; this.fillFailures = 0; this.handValid = false; this.filteredHand = null;
      this.filteredDistance = null; this.measuredFill = null; this.lastValidFill = null; this.quality = 'warming';
      this.fillFaultLatched = false; this.reportedFault = false; this.reportedFaultCodes = ''; this.full = false; this.high = 0; this.low = 0;
      this.slot = 0; this.slotAt = 0; this.seed = 42; this.events = []; this.history = [];
      this.automation = null; this.progress = 0; this.automationLabel = 'Sẵn sàng cho một chu kỳ thử';
    }
    random() { this.seed = (1664525 * this.seed + 1013904223) >>> 0; return this.seed / 4294967296; }
    snapshot() {
      return { now: this.now, lid: this.lid, servoAngle: this.servoAngle, commandAngle: this.commandAngle,
        openCount: this.openCount, handDistance: this.handDistance, filteredHand: this.filteredHand,
        physicalFill: this.physicalFill, fill: this.quality === 'valid' ? this.measuredFill : null,
        lastValidFill: this.lastValidFill, distance: this.quality === 'valid' ? this.filteredDistance : null,
        quality: this.quality, full: this.full, fault: this.reportedFault,
        faultCodes: this.faultCodes(),
        ledRed: this.full || this.reportedFault || this.quality !== 'valid',
        ledGreen: !this.full || this.reportedFault || this.quality !== 'valid',
        handSensorFault: this.handSensorFault, fillSensorFault: this.fillSensorFault, noise: this.noise,
        automation: this.automation ? this.automation.kind : null,
        progress: this.progress, automationLabel: this.automationLabel };
    }
    faultCodes() {
      return [this.lid === 'FAULT' ? 'HAND_SENSOR' : null, this.fillFaultLatched ? 'FILL_SENSOR' : null].filter(Boolean);
    }
    emit(type, text) {
      const event = { type, text, at: this.now, snapshot: this.snapshot() };
      this.events.push(event); this.history.unshift(event);
      if (this.events.length > 256) this.events.shift();
      if (this.history.length > 80) this.history.length = 80;
    }
    drainEvents() { const events = this.events; this.events = []; return events; }
    advance(milliseconds) {
      if (!Number.isFinite(milliseconds) || milliseconds < 0 || milliseconds > 60000) throw new Error('Invalid simulation time step');
      const target = this.now + milliseconds;
      while (this.now < target) { const step = Math.min(10, target - this.now); this.now += step; this.tick(step); }
      return this.snapshot();
    }
    setHand(value) { if (!Number.isFinite(value)) return; this.handDistance = clamp(value, 2, 100); }
    setFill(value) { if (!Number.isFinite(value)) return; this.physicalFill = clamp(value, 0, 100); }
    addWaste(amount = 8) {
      if (this.lid !== 'OPEN' || this.reportedFault) return false;
      const before = this.physicalFill; this.setFill(before + clamp(amount, 0, 100));
      if (this.physicalFill > before) this.emit('DISPOSE', 'Đã bỏ thêm rác mô phỏng');
      return this.physicalFill > before;
    }
    cancelAutomation() {
      if (!this.automation) return;
      this.automation = null; this.automationLabel = 'Đã dừng kịch bản; tiếp tục thao tác bằng tay'; this.progress = 0;
      this.setHand(100);
    }
    startCycle() {
      if (this.lid === 'FAULT' || this.handSensorFault || this.fillSensorFault) return false;
      this.automation = { kind: 'cycle', phase: 'prepare', at: this.now, next: this.now };
      this.progress = 0; this.automationLabel = '1/6 · Chuẩn bị mức rác ban đầu'; this.setHand(100); this.setFill(10);
      return true;
    }
    startCollection() {
      if (this.automation || this.lid !== 'CLOSED' || this.handSensorFault || this.reportedFault) return false;
      this.automation = { kind: 'collection', phase: 'collect-open', at: this.now };
      this.progress = 0.2; this.automationLabel = 'Đang mở nắp để thu gom'; this.setHand(10); return true;
    }
    resetFault() {
      if (this.lid !== 'FAULT' || this.handSensorFault || !this.handValid || this.filteredHand < 25) return false;
      this.changeLid(this.commandAngle === 90 ? 'OPEN' : 'CLOSED'); this.seen = true; this.lastSeen = this.now;
      this.emit('RESET', 'Đã xác nhận phục hồi cảm biến tay'); return true;
    }
    changeLid(next) {
      if (next === this.lid) return;
      const previous = this.lid; this.lid = next;
      if (next === 'OPENING') { this.moveAt = this.now; this.openCount++; }
      if (next === 'CLOSING') this.moveAt = this.now;
      if (next === 'CLOSED') this.closedAt = this.now;
      this.commandAngle = next === 'FAULT' ? (previous === 'CLOSED' ? 0 : 90) : (next === 'CLOSED' || next === 'CLOSING' ? 0 : 90);
      this.fillWindow.clear(); this.quality = 'lid_open'; this.measuredFill = null; this.high = this.low = 0;
      this.emit('LID', previous + ' → ' + next);
    }
    sampleHand() {
      if (this.handSensorFault) { this.handFailures = Math.min(3, this.handFailures + 1); this.handValid = false; return; }
      this.handFailures = 0; this.handWindow.push(this.handDistance, this.now);
      this.filteredHand = this.handWindow.read(this.now); this.handValid = this.filteredHand !== null;
    }
    sampleFill() {
      if (this.lid !== 'CLOSED' || this.now - this.closedAt < 1000) {
        this.fillWindow.clear(); this.quality = 'lid_open'; this.measuredFill = null; this.high = this.low = 0; return;
      }
      if (this.fillSensorFault) {
        this.fillWindow.clear();
        this.fillFailures = Math.min(3, this.fillFailures + 1);
        if (this.fillFailures >= 3) this.fillFaultLatched = true;
        this.quality = this.fillFaultLatched ? 'fault' : 'stale'; this.measuredFill = null; this.high = this.low = 0; return;
      }
      this.fillFailures = 0;
      this.fillWindow.push(30 - 26 * this.physicalFill / 100 + (this.noise ? (this.random() - 0.5) * 0.8 : 0), this.now);
      this.filteredDistance = this.fillWindow.read(this.now);
      if (this.filteredDistance === null) { this.quality = this.fillFaultLatched ? 'fault' : 'warming'; this.measuredFill = null; return; }
      this.fillFaultLatched = false; this.quality = 'valid';
      this.measuredFill = clamp(100 * (30 - this.filteredDistance) / 26, 0, 100); this.lastValidFill = this.measuredFill;
      this.high = this.measuredFill >= 80 ? Math.min(3, this.high + 1) : 0;
      this.low = this.measuredFill <= 75 ? Math.min(3, this.low + 1) : 0;
      if (!this.full && this.high >= 3) { this.full = true; this.emit('FULL', 'Đã xác nhận đầy · cần thu gom'); }
      if (this.full && this.low >= 3) { this.full = false; this.emit('CLEARED', 'Mức rác đã giảm · xóa cảnh báo đầy'); }
    }
    tick(step) {
      if (this.now - this.slotAt >= 70) {
        this.slotAt = this.now;
        this.slot === 4 ? this.sampleFill() : this.sampleHand(); this.slot = (this.slot + 1) % 5;
      }
      if (this.lid !== 'FAULT') {
        if (this.handFailures >= 3) this.changeLid('FAULT');
        else {
          const near = this.handValid && this.filteredHand < (this.lid === 'CLOSED' ? 20 : 25);
          if (near) { this.seen = true; this.lastSeen = this.now; }
          if (near && (this.lid === 'CLOSED' || this.lid === 'CLOSING')) this.changeLid('OPENING');
          if (this.lid === 'OPENING' && this.now - this.moveAt >= 600) this.changeLid('OPEN');
          else if (this.lid === 'CLOSING' && this.now - this.moveAt >= 600) this.changeLid('CLOSED');
          else if (this.lid === 'OPEN' && this.handValid && this.seen && this.now - this.lastSeen >= 3000) this.changeLid('CLOSING');
        }
      }
      const maxMove = 90 * step / 600;
      this.servoAngle += clamp(this.commandAngle - this.servoAngle, -maxMove, maxMove);
      const fault = this.fillFaultLatched || this.lid === 'FAULT';
      const faultCodes = this.faultCodes().join(',');
      if (faultCodes !== this.reportedFaultCodes) {
        this.reportedFault = fault; this.reportedFaultCodes = faultCodes;
        const names = this.faultCodes().map(code => code === 'HAND_SENSOR' ? 'cảm biến tay / nắp chốt lỗi' : 'cảm biến mức rác');
        this.emit(fault ? 'FAULT' : 'RECOVERED', fault ? 'Cần kiểm tra: ' + names.join(', ') : 'Các lỗi đã xác nhận được phục hồi');
      }
      this.runAutomation();
    }
    phase(next, label, progress) {
      this.automation.phase = next; this.automation.at = this.now; this.automation.next = this.now;
      this.automationLabel = label; this.progress = progress;
    }
    runAutomation() {
      const a = this.automation; if (!a) return;
      if (this.reportedFault || this.handSensorFault || this.fillSensorFault) { this.cancelAutomation(); this.automationLabel = 'Kịch bản dừng: cần phục hồi cảm biến'; return; }
      if (this.now - a.at > 15000) { this.cancelAutomation(); this.automationLabel = 'Kịch bản dừng: chưa đạt trạng thái mong đợi'; return; }
      if (a.phase === 'prepare' && this.lid === 'CLOSED' && this.quality === 'valid' && !this.full && this.measuredFill < 20) {
        this.phase('approach', '2/6 · Đưa tay vào vùng cảm biến', 0.15); this.setHand(10);
      } else if (a.phase === 'approach' && this.lid === 'OPEN') {
        this.phase('dispose', '3/6 · Bỏ rác qua nắp đang mở', 0.3);
      } else if (a.phase === 'dispose' && this.now >= a.next) {
        if (this.physicalFill < 88) { this.addWaste(Math.min(8, 88 - this.physicalFill)); a.next = this.now + 250; }
        else { this.phase('withdraw', '4/6 · Rút tay, chờ nắp đóng', 0.48); this.setHand(100); }
      } else if (a.phase === 'withdraw' && this.lid === 'CLOSED') {
        this.phase('wait-full', '5/6 · Lọc số đo và xác nhận FULL', 0.62);
      } else if (a.phase === 'wait-full' && this.full && this.quality === 'valid') {
        if (this.now - a.at >= 4500) { this.phase('collect-open', '6/6 · Thu gom và kiểm tra CLEARED', 0.76); this.setHand(10); }
      } else if (a.phase === 'collect-open' && this.lid === 'OPEN') {
        this.setFill(5); this.emit('COLLECT', 'Đã lấy rác ra khỏi thùng mô phỏng');
        this.phase('collect-empty', 'Đã thu gom, chờ đóng nắp và đo lại', 0.85);
      } else if (a.phase === 'collect-empty' && this.now - a.at >= 700) {
        this.setHand(100); this.phase('wait-clear', 'Đang xác nhận mức rác sau thu gom', 0.92);
      } else if (a.phase === 'wait-clear' && this.lid === 'CLOSED' && this.quality === 'valid' && !this.full && this.measuredFill < 20) {
        this.automation = null; this.progress = 1; this.automationLabel = 'Hoàn tất · nắp đóng, mức rác thấp'; this.emit('DONE', a.kind === 'cycle' ? 'Hoàn tất chu kỳ thử nghiệm' : 'Đã thu gom và đo lại mức rác');
      }
    }
  }
  class PendingRecords {
    constructor(limit = 32) { this.limit = limit; this.records = []; this.inFlight = null; this.dropped = 0; }
    push(record) {
      if (record.kind === 'telemetry') this.records = this.records.filter(r => r.kind === 'event' || r === this.inFlight);
      if (this.records.length >= this.limit) {
        const disposable = this.records.findIndex(r => r.kind === 'telemetry' && r !== this.inFlight);
        if (disposable >= 0) this.records.splice(disposable, 1);
        else { this.dropped++; return false; }
      }
      this.records.push(record); return true;
    }
    peek() { return this.records[0] || null; }
    ack(ack) {
      const i = this.records.findIndex(r => r.bin_id === ack.bin_id && r.boot_id === ack.boot_id && r.seq === ack.seq);
      if (i < 0 || ack.stored !== true) return false;
      const removed = this.records.splice(i, 1)[0]; if (this.inFlight === removed) this.inFlight = null; return true;
    }
  }
  return { BinSimulation, PendingRecords, Window };
});
