(function () {
  'use strict';
  const el = id => document.getElementById(id);
  const { BinSimulation, PendingRecords } = window.SmartBinSimulation;
  const lidText = { CLOSED: 'Đóng', OPENING: 'Đang mở', OPEN: 'Đang mở', CLOSING: 'Đang đóng', FAULT: 'Chốt lỗi' };
  let model = new BinSimulation(), queue = new PendingRecords(), user = null, session = null;
  let running = true, frameId = null, previousFrame = null, lastPaint = 0, handlers = {}, count = 0, epoch = 0;
  let sequence = 0, sessionAt = 0, sessionOpens = 0, lastHeartbeat = 0, offlineAt = 0, reconnects = 0;
  let notificationSwitching = false, notificationUncertain = false, notificationError = '';
  let connecting = false, uploading = false, nextAttempt = 0, retryMs = 1000, activeRequest = null;
  let savedCount = 0, lastRefresh = 0, syncError = '', localPausedForHidden = false;
  let wifiSeq = 0, wifiLastAttempt = 0, wifiLastAck = 0, wifiBusy = false, wifiRequest = null;
  const formatTime = ms => `${String(Math.floor(ms / 60000)).padStart(2, '0')}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}`;
  const isOffline = () => el('lab-offline').checked;
  function notice(type, title, text) {
    el('lab-notice').dataset.tone = type;
    el('lab-notice-title').textContent = title;
    el('lab-notice-text').textContent = text;
  }
  function addLog(event) {
    count++; el('lab-event-count').textContent = `${count} sự kiện`;
    const item = document.createElement('li'); item.dataset.event = event.type;
    const time = document.createElement('time'); time.textContent = formatTime(event.at);
    const text = document.createElement('span'); text.textContent = event.text;
    item.append(time, text);
    if (count === 1) el('lab-events').replaceChildren();
    el('lab-events').prepend(item);
    while (el('lab-events').children.length > 30) el('lab-events').lastChild.remove();
  }
  function record(snapshot, eventType = null) {
    if (!session) return;
    if (sequence >= 4294967295) { syncError = 'Phiên đã hết dải số thứ tự; vui lòng tải lại trang để tạo phiên mới.'; return; }
    const msg = {
      version: 1, bin_id: session.bin_id, boot_id: session.boot_id, boot_no: session.boot_no, seq: ++sequence,
      kind: eventType ? 'event' : 'telemetry', event_type: eventType, source: 'simulated', time_quality: 'simulated',
      sampled_at: new Date(Date.now() - Math.max(0, model.now - snapshot.now)).toISOString(),
      uptime_ms: Math.max(0, Math.round(snapshot.now - sessionAt)),
      fill_pct: snapshot.fill === null ? null : Number(snapshot.fill.toFixed(3)),
      distance_cm: snapshot.distance === null ? null : Number(snapshot.distance.toFixed(3)),
      quality: snapshot.quality, lid_state: snapshot.lid, lid_open_count: Math.max(0, snapshot.openCount - sessionOpens),
      full_on_pct: 80, full_off_pct: 75, battery_mv: null, fault_codes: snapshot.faultCodes,
      queue_depth: queue.records.length, dropped_records: queue.dropped, reconnects,
      offline_ms: offlineAt ? Math.max(0, Date.now() - offlineAt) : 0
    };
    if (!queue.push(msg)) syncError = 'Bộ đệm lab đã đầy: giữ bản cũ, đếm bản mới bị bỏ. Hãy nối lại để lưu.';
  }
  function consumeEvents() {
    for (const event of model.drainEvents()) {
      addLog(event);
      if (event.type === 'FULL') notice('FULL', 'Thùng đã đầy · cần thu gom', `Mức đầy đã xác nhận ${event.snapshot.fill.toFixed(1)}%. ${session && session.notification_mode === 'telegram_opt_in' && session.telegram_available ? 'Đã bật gửi Telegram; chờ backend xử lý, chưa xác nhận đã nhận.' : 'Chỉ xem trước; Telegram chưa được bật cho phiên này.'}`);
      else if (event.type === 'CLEARED') notice('CLEARED', 'Đã xóa cảnh báo đầy', `Mức đầy còn ${event.snapshot.fill.toFixed(1)}% sau lọc và xác nhận. Đã sẵn sàng cho chu kỳ mới.`);
      else if (event.type === 'FAULT') notice('FAULT', 'Cảm biến cần kiểm tra', 'Giá trị không hợp lệ được giữ là chưa biết. Hãy phục hồi cảm biến trước khi tiếp tục.');
      else if (event.type === 'RECOVERED') notice('RECOVERED', 'Dữ liệu cảm biến đã phục hồi', 'Cảnh báo mức đầy vẫn được đánh giá độc lập theo số đo và ngưỡng 80/75%.');
      else if (event.type === 'DONE') notice('DONE', 'Hoàn tất thao tác mô phỏng', 'Nắp đã đóng và bộ lọc đã có số đo mới. Xem nhật ký để đối chiếu FULL/CLEARED của từng đợt đầy.');
      if (['FULL', 'CLEARED', 'FAULT', 'RECOVERED'].includes(event.type)) record(event.snapshot, event.type);
      else if (event.type === 'LID') record(event.snapshot);
    }
  }
  function render() {
    const s = model.snapshot(), near = Math.max(0, (100 - s.handDistance) / 98);
    el('lab-lid').setAttribute('transform', `rotate(${s.servoAngle * 0.5} 386 181)`);
    el('lab-hand').setAttribute('transform', `translate(${50 - near * 145} ${-near * 35})`);
    el('lab-hand').setAttribute('opacity', String(0.2 + near * 0.8));
    el('lab-sensor-waves').setAttribute('opacity', s.handSensorFault ? '.08' : String(.12 + near * .7));
    el('lab-fill-clip-rect').setAttribute('y', String(405 - 170 * s.physicalFill / 100));
    el('lab-fill-clip-rect').setAttribute('height', String(170 * s.physicalFill / 100));
    el('lab-led-red').setAttribute('fill', s.ledRed ? '#ef8a63' : '#56634b');
    el('lab-led-green').setAttribute('fill', s.ledGreen ? '#d0e78d' : '#56634b');
    el('lab-scene-hand').textContent = `Tay: ${s.handDistance.toFixed(0)} cm`;
    el('lab-scene-fill').textContent = `Rác đặt: ${s.physicalFill.toFixed(0)}%`;
    el('lab-hand-range').value = s.handDistance; el('lab-fill-range').value = s.physicalFill;
    el('lab-hand-badge').textContent = `${s.handDistance.toFixed(0)} cm`;
    el('lab-physical-badge').textContent = `${s.physicalFill.toFixed(0)}%`;
    el('lab-lid-state').textContent = lidText[s.lid];
    el('lab-servo').textContent = `${s.servoAngle.toFixed(0)}°`;
    el('lab-measured').textContent = s.fill === null ? '—' : `${s.fill.toFixed(1)}%`;
    const faults = s.faultCodes.map(code => code === 'HAND_SENSOR' ? 'Lỗi cảm biến tay' : 'Lỗi cảm biến mức rác');
    const displayState = s.fault ? 'LỖI THIẾT BỊ' : s.quality === 'lid_open' ? 'CHỜ ĐÓNG NẮP' : s.quality !== 'valid' ? 'CHỜ ĐO' : s.full ? 'ĐẦY · CẦN THU GOM' : 'ĐANG HOẠT ĐỘNG';
    el('lab-display').dataset.tone = s.fault ? 'fault' : s.quality !== 'valid' ? 'waiting' : s.full ? 'full' : 'normal';
    el('lab-display-value').textContent = s.fill === null ? '—' : `${s.fill.toFixed(1)}%`;
    el('lab-display-state').textContent = displayState;
    el('lab-display-fault').textContent = faults.length === 2 ? 'Lỗi tay + mức rác' : faults[0] || 'Chưa có lỗi xác nhận';
    el('lab-display-description').textContent = `LED: ${s.fill === null ? 'chưa có số đo hợp lệ' : s.fill.toFixed(1) + '%'} · ${displayState}. ${faults.join('; ') || 'Chưa ghi nhận lỗi thiết bị.'}`;

    const status = s.fault ? 'Cần kiểm tra' : s.quality !== 'valid' ? 'Chờ đo' : s.full ? 'Đầy' : 'Bình thường';
    el('lab-alert-state').textContent = status;
    el('lab-alert-state').dataset.tone = s.fault ? 'fault' : s.full ? 'full' : '';
    el('lab-measured').dataset.tone = s.full ? 'full' : '';
    const handNear = s.handDistance < (s.lid === 'CLOSED' ? 20 : 25);
    el('lab-hand-toggle').setAttribute('aria-pressed', String(handNear));
    el('lab-hand-toggle').firstElementChild.textContent = handNear ? 'Rút tay ra xa' : 'Đưa tay lại gần';
    el('lab-add').disabled = s.lid !== 'OPEN' || s.fault || s.physicalFill >= 100 || !!s.automation;
    el('lab-collect').disabled = s.lid !== 'CLOSED' || s.fault || s.handSensorFault || !!s.automation;
    el('lab-recover').disabled = s.lid !== 'FAULT' || s.handSensorFault || s.handDistance < 25;
    el('lab-cycle').dataset.active = String(!!s.automation);
    el('lab-cycle').textContent = s.automation ? '■ Dừng kịch bản' : '▷ Chạy chu kỳ tự động';
    el('lab-cycle').disabled = !s.automation && (s.lid === 'FAULT' || s.handSensorFault || s.fillSensorFault);
    el('lab-fault-hand').checked = s.handSensorFault; el('lab-fault-fill').checked = s.fillSensorFault;
    el('lab-noise').checked = s.noise;
    el('lab-stage').textContent = s.automationLabel; el('lab-clock').textContent = formatTime(s.now);
    el('lab-progress-bar').style.width = `${s.progress * 100}%`;
    el('lab-running').lastChild.textContent = localPausedForHidden ? ' Tạm dừng khi ẩn tab' : running ? ' Đang chạy · 1×' : ' Đã tạm dừng';
    el('lab-pause').textContent = running ? 'Tạm dừng' : 'Tiếp tục';
    el('lab-pause').setAttribute('aria-pressed', String(!running));
    const notes = { valid: s.lid === 'OPEN' ? 'Có thể bỏ rác khi nắp mở.' : 'Số đo đã lọc. Cảnh báo bật ở 80%, xóa ở 75%, cần 3 lần xác nhận.',
      lid_open: 'Chờ nắp đóng và ổn định để đo lại mức rác.', warming: 'Đang gom đủ 7 mẫu cho bộ lọc mức rác.',
      stale: 'Lần đo hiện tại chưa hợp lệ; chưa suy ra mức đầy.', fault: 'Cảm biến mức rác đang lỗi. Giá trị được hiển thị là chưa biết.' };
    el('lab-measure-note').textContent = s.lid === 'OPEN' && !s.fault ? 'Nắp đang mở: bạn có thể bấm Bỏ rác +8%. Đo mức đầy sẽ tiếp tục sau khi đóng.' : notes[s.quality];
    el('lab-connect').disabled = connecting || !!session || !user || user.role !== 'manager' || isOffline();
    el('lab-connect').textContent = connecting ? 'Đang tạo phiên lab…' : session ? 'Đồng bộ đã bật' : 'Đồng bộ với dashboard';
    el('lab-history-link').hidden = !session;
    const wifiState = isOffline() ? 'offline' : !session ? 'local' : !wifiLastAck ? 'connecting' : Date.now() - wifiLastAck >= 12000 ? 'unconfirmed' : 'connected';
    const wifiLabels = {offline:'Mất Wi-Fi (giả lập)',local:'Sẵn sàng · chưa giám sát',connecting:'Đang kết nối…',unconfirmed:'Chưa nhận xác nhận',connected:'Đã kết nối'};
    el('lab-wifi-card').dataset.state = wifiState;
    el('lab-wifi-state').textContent = wifiLabels[wifiState];
    el('lab-wifi-toggle').textContent = isOffline() ? 'Kết nối lại Wi-Fi mô phỏng' : 'Ngắt Wi-Fi mô phỏng';
    el('lab-wifi-toggle').setAttribute('aria-pressed', String(isOffline()));
    el('lab-wifi-toggle').disabled = !user;
    el('lab-wifi-note').textContent = !session ? 'Bật đồng bộ để backend giám sát kết nối. Telegram cần bật riêng cho phiên.' : isOffline() ? 'Thùng vẫn hoạt động và giữ bản tin trong RAM. Backend phát hiện mất heartbeat sau khoảng 12 giây; tin Wi-Fi được gửi riêng nếu Telegram đã bật.' : wifiState === 'connected' ? 'Heartbeat mỗi 3 giây; tin kết nối Wi-Fi tách riêng với tin mức đầy/lỗi cảm biến.' : 'Đang chờ heartbeat được backend xác nhận. Máy chạy backend cần Internet để gửi Telegram.';

    const telegramOn = !!session && session.notification_mode === 'telegram_opt_in';
    el('lab-telegram').checked = telegramOn;
    el('lab-telegram').disabled = !session || !user || user.role !== 'manager' || uploading || notificationSwitching || notificationUncertain || isOffline() || (!telegramOn && !session.telegram_available);
    el('lab-notice-tag').textContent = telegramOn && session.telegram_available ? 'TELEGRAM ĐÃ BẬT' : 'XEM TRƯỚC';
    el('lab-telegram-status').textContent = notificationError || (notificationSwitching ? 'Đang lưu lựa chọn…' : !session ? 'Bật đồng bộ trước khi bật Telegram.' : !session.telegram_available ? 'Backend chưa sẵn sàng: cần token, chat ID và TELEGRAM_DRY_RUN=0; khởi động lại backend rồi tải lại trang.' : telegramOn ? `Gửi sự kiện mới tới chat ${session.recipient_hint}. Bản đã xếp hàng vẫn có thể đến sau khi tắt. Đây chưa phải xác nhận nhận tin.` : `Sẵn sàng gửi tới chat ${session.recipient_hint}. Bật trước khi chạy chu kỳ mới; không gửi lại bản cũ.`);

    if (notificationUncertain) el('lab-sync-status').textContent = 'Đồng bộ tạm dừng vì chưa xác nhận lựa chọn Telegram. Tải lại trang để tạo phiên mới.';
    else if (syncError) el('lab-sync-status').textContent = syncError;
    else if (!session) el('lab-sync-status').textContent = user && user.role === 'manager' ? 'Bản xem trước. Bật đồng bộ để lưu vào một thùng lab mô phỏng riêng.' : 'Bạn đang xem thử. Tài khoản quản lý có thể lưu phiên lab vào dashboard.';
    else el('lab-sync-status').textContent = `${isOffline() ? 'Ngoại tuyến mô phỏng' : uploading ? 'Đang lưu' : 'Đồng bộ đang bật'} · ${savedCount} bản đã ACK · ${queue.records.length} chờ · ${queue.dropped} bị bỏ. Nguồn simulated.`;
  }
  function frame(now) {
    if (!user) { frameId = null; return; }
    if (previousFrame === null) previousFrame = now;
    if (running && !document.hidden) {
      model.advance(Math.min(200, now - previousFrame)); consumeEvents();
      if (session && model.now - lastHeartbeat >= 2500) { lastHeartbeat = model.now; record(model.snapshot()); }
    }
    previousFrame = now;
    if (now - lastPaint >= 50) { render(); lastPaint = now; }
    frameId = requestAnimationFrame(frame);
  }
  function resume() { running = true; previousFrame = null; if (!frameId && user) frameId = requestAnimationFrame(frame); }
  function manual() { model.cancelAutomation(); }
  el('lab-hand-range').addEventListener('input', e => { manual(); model.setHand(Number(e.target.value)); render(); });
  el('lab-fill-range').addEventListener('input', e => { manual(); model.setFill(Number(e.target.value)); render(); });
  el('lab-hand-toggle').onclick = () => { manual(); model.setHand(model.handDistance < (model.lid === 'CLOSED' ? 20 : 25) ? 100 : 10); render(); };
  el('lab-add').onclick = () => { if (!model.addWaste()) notice('FAULT', 'Cần mở nắp trước', 'Đưa tay lại gần và chờ nắp mở hoàn toàn để bỏ rác.'); consumeEvents(); render(); };
  el('lab-collect').onclick = () => { if (model.startCollection()) resume(); render(); };
  el('lab-cycle').onclick = () => { if (model.automation) model.cancelAutomation(); else if (model.startCycle()) resume(); render(); };
  el('lab-pause').onclick = () => { running = !running; previousFrame = null; render(); };
  el('lab-recover').onclick = () => { if (!model.resetFault()) notice('FAULT', 'Chưa đủ điều kiện phục hồi', 'Tắt lỗi cảm biến tay, kéo tay về 100 cm và chờ đủ mẫu rồi thử lại.'); consumeEvents(); render(); };
  el('lab-fault-hand').onchange = e => { model.handSensorFault = e.target.checked; render(); };
  el('lab-fault-fill').onchange = e => { model.fillSensorFault = e.target.checked; render(); };
  el('lab-noise').onchange = e => { model.noise = e.target.checked; render(); };
  el('lab-offline').onchange = () => {
    if (isOffline()) {
      offlineAt = Date.now();
      if (activeRequest) activeRequest.abort();
      if (wifiRequest) wifiRequest.abort();
      addLog({type:'WIFI',at:model.now,text:'Đã ngắt Wi-Fi mô phỏng; chờ backend phát hiện mất heartbeat'});
    }
    else { reconnects++; offlineAt = 0; nextAttempt = 0; retryMs = 1000; syncError = ''; wifiLastAck = 0; wifiLastAttempt = 0;
      addLog({type:'WIFI',at:model.now,text:'Đang kết nối lại Wi-Fi mô phỏng'});
      void heartbeat();
    }
    render();
  };
  el('lab-wifi-toggle').onclick = () => { el('lab-offline').checked = !isOffline(); el('lab-offline').onchange(); };
  document.addEventListener('visibilitychange', () => { localPausedForHidden = document.hidden; previousFrame = null; render(); });
  async function request(url, body, channel = 'data') {
    const controller = new AbortController();
    if (channel === 'wifi') wifiRequest = controller; else activeRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal });
      let value; try { value = await response.json(); } catch { throw Error('Backend chưa trả phản hồi hợp lệ.'); }
      if (!response.ok) {
        if (response.status === 404) throw Error('Hãy khởi động lại backend để dùng API lab mới.');
        if (response.status === 401) throw Error('Phiên đăng nhập hết hạn; vui lòng đăng nhập lại.');
        throw Error(typeof value.detail === 'string' ? value.detail : 'Dữ liệu lab chưa được chấp nhận.');
      }
      return value;
    } finally { clearTimeout(timeout); if (activeRequest === controller) activeRequest = null; if (wifiRequest === controller) wifiRequest = null; }
  }
  el('lab-connect').onclick = async () => {
    if (!user || user.role !== 'manager' || session || connecting || isOffline()) return;
    connecting = true; syncError = ''; render();
    const generationAtStart = epoch;
    try {
      const owner = user.username, generation = epoch;
      const value = await request('/api/lab/sessions');
      if (!user || user.username !== owner || generation !== epoch) return;
      session = value; wifiSeq = 0; wifiLastAttempt = 0; wifiLastAck = 0; sequence = 0; savedCount = 0; queue = new PendingRecords();
      sessionAt = model.now; sessionOpens = model.openCount; lastHeartbeat = model.now;
      record(model.snapshot());
      await heartbeat();
      if (generation !== epoch || !user || user.username !== owner) return;
      addLog({ type: 'SYNC', at: model.now, text: 'Đã tạo phiên dashboard · simulated · chỉ xem trước thông báo' });
    } catch (error) { if (generationAtStart !== epoch) return; syncError = `Chưa thể đồng bộ. ${error.name === 'AbortError' ? 'Mất kết nối hoặc quá thời gian chờ.' : error.message}`; }
    finally { if (generationAtStart === epoch) { connecting = false; render(); } }
  };
  el('lab-telegram').onchange = async e => {
    if (!session || !user || user.role !== 'manager' || uploading || notificationSwitching || notificationUncertain || isOffline()) { render(); return; }
    const currentSession = session, generation = epoch, enabled = e.target.checked;
    notificationSwitching = true; notificationError = ''; render();
    try {
      const value = await request(`/api/lab/sessions/${session.session_id}/notifications`, { enabled, after_seq: sequence });
      if (generation !== epoch || session !== currentSession) return;
      Object.assign(session, value);
      addLog({type: 'SYNC', at: model.now, text: enabled ? 'Đã bật Telegram cho sự kiện mới của phiên này' : 'Đã tắt Telegram cho sự kiện mới; bản đã xếp hàng có thể vẫn đến'});
    } catch (error) {
      if (generation === epoch && session === currentSession) { notificationUncertain = true; notificationError = error.name === 'AbortError' ? 'Chưa xác nhận được lựa chọn; tải lại trang để tạo phiên mới trước khi thử tiếp.' : error.message; }
    } finally { if (generation === epoch) { notificationSwitching = false; render(); } }
  };
  async function flush() {
    if (!user || !session || uploading || notificationSwitching || notificationUncertain || isOffline() || !queue.peek() || Date.now() < nextAttempt) return;
    const owner = user.username, currentSession = session, message = queue.peek(), currentQueue = queue, generation = epoch;
    currentQueue.inFlight = message; uploading = true; render();
    try {
      const ack = await request(`/api/lab/sessions/${currentSession.session_id}/messages`, message);
      if (!user || user.username !== owner || session !== currentSession || generation !== epoch) return;
      if (!currentQueue.ack(ack)) throw Error('ACK không khớp bản tin đang gửi.');
      for (const key of ['notification_mode', 'telegram_available', 'recipient_hint']) if (Object.hasOwn(ack, key)) session[key] = ack[key];
      savedCount++; retryMs = 1000; nextAttempt = Date.now() + 500; syncError = '';
      if (Date.now() - lastRefresh > 2000 && handlers.refresh) { lastRefresh = Date.now(); Promise.resolve(handlers.refresh()).catch(() => {}); }
    } catch (error) {
      if (session === currentSession && user && user.username === owner && generation === epoch) {
        nextAttempt = Date.now() + retryMs; retryMs = Math.min(30000, retryMs * 2);
        syncError = isOffline() ? '' : `Đang giữ ${currentQueue.records.length} bản chờ để gửi lại cùng ID. ${error.name === 'AbortError' ? 'Kết nối chưa phản hồi.' : error.message}`;
      }
    } finally { if (generation === epoch) { uploading = false; render(); } }
  }
  async function heartbeat() {
    // Wall-clock lease is independent of the paused sensor animation and telemetry replay.
    if (!user || user.role !== 'manager' || !session || !session.heartbeat_timeout_seconds || isOffline() || wifiBusy || notificationUncertain || Date.now() - wifiLastAttempt < 3000) return;
    const currentSession = session, generation = epoch, seq = ++wifiSeq;
    wifiBusy = true; wifiLastAttempt = Date.now();
    try {
      const ack = await request(`/api/lab/sessions/${session.session_id}/connection`, {seq,action:'heartbeat'}, 'wifi');
      if (generation !== epoch || session !== currentSession || isOffline()) return;
      if (ack.session_id !== session.session_id || ack.heartbeat_seq !== seq || ack.connection_state !== 'connected') throw Error('Heartbeat chưa được xác nhận');
      const first = !wifiLastAck; wifiLastAck = Date.now();
      if (first) addLog({type:'WIFI',at:model.now,text:'Backend đã xác nhận kết nối Wi-Fi mô phỏng'});
    } catch { /* Backend independently detects missing heartbeats; no client-side Telegram call. */ }
    finally { if (generation === epoch) { wifiBusy = false; render(); } }
  }
  if (window.addEventListener) window.addEventListener('pagehide', () => {
    if (session && !isOffline() && user && user.role === 'manager') {
      void fetch(`/api/lab/sessions/${session.session_id}/connection`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seq:++wifiSeq,action:'stop'}),keepalive:true}).catch(() => {});
    }
  });
  el('lab-history-link').onclick = () => { if (session && handlers.select) handlers.select(session.bin_id); };
  setInterval(async () => { await heartbeat(); await flush(); }, 600);
  window.SmartBinLab = {
    configure(value) { handlers = value || {}; },
    setUser(value) {
      if (user && value && user.username === value.username && user.role === value.role) { user = value; render(); return; }
      epoch++;
      if (activeRequest) activeRequest.abort();
      if (wifiRequest) wifiRequest.abort();
      if (frameId) cancelAnimationFrame(frameId);
      frameId = null; previousFrame = null; user = value; session = null; queue = new PendingRecords();
      model = new BinSimulation(); notificationSwitching = false; notificationUncertain = false; notificationError = ''; connecting = false; uploading = false; sequence = 0; savedCount = 0; syncError = ''; count = 0;
      wifiSeq = 0; wifiLastAttempt = 0; wifiLastAck = 0; wifiBusy = false;
      offlineAt = 0; reconnects = 0; nextAttempt = 0; running = true;
      el('lab-offline').checked = false;
      el('lab-events').replaceChildren();
      notice('', 'Sẵn sàng để thử', 'Thao tác trên thùng hoặc chạy một chu kỳ tự động. Thông báo ở đây là bản xem trước, không gửi Telegram.');
      render(); if (user) resume();
    }
  };
  render();
})();
