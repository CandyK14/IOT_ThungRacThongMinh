const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { BinSimulation, PendingRecords } = require('../dashboard/simulation-core.js');
const root = path.resolve(__dirname, '..');

test('hand thresholds, hold and add-waste interlock', () => {
  const m = new BinSimulation(); m.advance(4000);
  assert.equal(m.lid, 'CLOSED'); assert.equal(m.addWaste(), false);
  m.setHand(22); m.advance(1000); assert.equal(m.lid, 'CLOSED');
  m.setHand(10); m.advance(1000); assert.equal(m.lid, 'OPEN'); assert.equal(m.addWaste(), true);
  m.setHand(22); m.advance(4000); assert.equal(m.lid, 'OPEN');
  m.setHand(100); m.advance(2800); assert.equal(m.lid, 'OPEN');
  m.advance(1500); assert.equal(m.lid, 'CLOSED'); assert.equal(m.commandAngle, 0);
});

test('filtered 80/75 hysteresis produces one FULL until CLEARED', () => {
  const m = new BinSimulation({fill:90}); m.advance(6000);
  assert.equal(m.full, true); assert.equal(m.history.filter(e => e.type === 'FULL').length, 1);
  m.advance(10000); assert.equal(m.history.filter(e => e.type === 'FULL').length, 1);
  m.setFill(77); m.advance(6000); assert.equal(m.full, true);
  m.setFill(70); m.advance(6000); assert.equal(m.full, false);
  assert.equal(m.history.filter(e => e.type === 'CLEARED').length, 1);
});

test('level fault stays unknown and latched across open-lid suspension', () => {
  const m = new BinSimulation({fill:90}); m.advance(6000);
  m.fillSensorFault = true; m.advance(1500);
  assert.equal(m.snapshot().fill, null); assert.equal(m.full, true); assert.equal(m.reportedFault, true);
  m.setHand(10); m.advance(1000); m.fillSensorFault = false; m.advance(2000);
  assert.equal(m.lid, 'OPEN'); assert.equal(m.snapshot().fill, null); assert.equal(m.reportedFault, true);
  m.setHand(100); m.advance(9000);
  assert.equal(m.quality, 'valid'); assert.equal(m.reportedFault, false); assert.equal(m.full, true);
});

test('hand fault does not mean hand absent; reset requires valid far readings', () => {
  const m = new BinSimulation(); m.setHand(10); m.advance(1500);
  m.handSensorFault = true; m.advance(1000); assert.equal(m.lid, 'FAULT'); assert.equal(m.commandAngle, 90);
  m.advance(5000); assert.equal(m.lid, 'FAULT'); assert.equal(m.resetFault(), false);
  m.handSensorFault = false; m.setHand(100); m.advance(1000);
  assert.equal(m.resetFault(), true); m.advance(5000); assert.equal(m.lid, 'CLOSED');
});

test('automatic cycle reaches FULL and CLEARED through measured states', () => {
  const m = new BinSimulation(); assert.equal(m.startCycle(), true); m.advance(35000);
  const events = m.drainEvents().filter(e => ['FULL','CLEARED','DONE'].includes(e.type));
  assert.deepEqual(events.map(e => e.type), ['FULL','CLEARED','DONE']);
  assert(events[0].snapshot.fill >= 80); assert(events[1].snapshot.fill <= 75);
  assert.equal(m.lid, 'CLOSED'); assert.equal(m.full, false); assert.equal(m.progress, 1);
});

test('collection of a non-full bin never fabricates FULL or CLEARED', () => {
  const m = new BinSimulation(); m.advance(4000); assert.equal(m.startCollection(), true); m.advance(15000);
  const events=m.drainEvents();
  assert.equal(events.filter(e=>e.type==='FULL'||e.type==='CLEARED').length,0);
  assert(events.some(e=>e.type==='DONE')); assert.equal(m.lid,'CLOSED'); assert(m.measuredFill<10);
});

test('bounded queue preserves in-flight bytes and critical order', () => {
  const q = new PendingRecords(4);
  const make = (seq, kind='telemetry') => ({bin_id:'lab-a',boot_id:'a',seq,kind,fill_pct:10});
  const first = make(1); q.push(first); q.inFlight = first;
  const full = make(2,'event'), clear = make(3,'event'); q.push(full); q.push(clear); q.push(make(4)); q.push(make(5));
  assert.deepEqual(q.records.map(r => r.seq), [1,2,3,5]);
  assert.equal(q.ack({stored:true,bin_id:'wrong',boot_id:'a',seq:1}), false);
  assert.equal(q.ack({stored:true,bin_id:'lab-a',boot_id:'a',seq:1}), true);
  assert.equal(q.ack({stored:true,bin_id:'lab-a',boot_id:'a',seq:1}), false);
  q.push(make(6,'event')); q.push(make(7,'event')); assert.equal(q.push(make(8,'event')), false);
  assert.equal(q.dropped, 1); assert(q.records.includes(full) && q.records.includes(clear));
});

// Controller unit harness exercises the actual script and real HTML IDs without a browser.
function controller(fetchOverride, wifiEnabled=false) {
  const html = fs.readFileSync(path.join(root, 'dashboard/index.html'), 'utf8');
  const ids = [...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]);
  assert.equal(new Set(ids).size, ids.length, 'HTML IDs must be unique');
  class Element {
    constructor(id='') { this.id=id;this.children=[];this.dataset={};this.style={};this.attrs={};this.listeners={};this.value='';this.checked=false;this.hidden=false;this.disabled=false;this._text='';this.textLeaf={textContent:''}; }
    set textContent(v) {this._text=String(v);this.children=[];}
    get textContent() {return this._text;}
    get firstElementChild() {if(!this.children[0])this.append(new Element());return this.children[0];}
    get lastChild() {return this.children.at(-1)||this.textLeaf;}
    append(...items) {for(const e of items){e.parent=this;this.children.push(e);}}
    prepend(e) {e.parent=this;this.children.unshift(e);}
    replaceChildren(...items) {this.children=[];this.append(...items);}
    remove() {if(this.parent)this.parent.children=this.parent.children.filter(e=>e!==this);}
    setAttribute(k,v) {this.attrs[k]=String(v);}
    addEventListener(k,f) {this.listeners[k]=f;}
  }
  const nodes = new Map(ids.map(id=>[id,new Element(id)])), intervals=[], frames=new Map(), documentListeners={};
  let frameSeq=0, wall=0;
  const base = Date.now();
  class Clock extends Date {constructor(...args){super(...(args.length?args:[base+wall]));}static now(){return base+wall;}}
  const document = {hidden:false,getElementById:id=>{assert(nodes.has(id),'Missing DOM ID '+id);return nodes.get(id);},createElement:()=>new Element(),addEventListener:(k,f)=>documentListeners[k]=f};
  const calls=[], stored=[];
  const session={session_id:'a'.repeat(32),bin_id:'lab-test',boot_id:'web-test',boot_no:1,...(wifiEnabled?{heartbeat_seconds:3,heartbeat_timeout_seconds:12}: {})};
  const response=value=>({ok:true,status:200,json:async()=>value});
  const fetch = async(url,options)=>{
    calls.push({url,body:options.body});
    if(fetchOverride)return fetchOverride(url,options,response,session,calls);
    if(url==='/api/lab/sessions')return response(session);
    if(url.endsWith('/connection'))return response({...session,heartbeat_seq:JSON.parse(options.body).seq,connection_state:'connected'});
    const m=JSON.parse(options.body);stored.push(m);return response({...m,stored:true});
  };
  const window = {SmartBinSimulation:require('../dashboard/simulation-core.js')};
  const context = {window,document,Date:Clock,AbortController,JSON,Number,Math,Error,Promise,fetch,setTimeout,clearTimeout,
    setInterval:f=>{intervals.push(f);return intervals.length;},requestAnimationFrame:f=>{const id=++frameSeq;frames.set(id,f);return id;},cancelAnimationFrame:id=>frames.delete(id)};
  vm.runInNewContext(fs.readFileSync(path.join(root,'dashboard/simulation.js'),'utf8'),context,{filename:'simulation.js'});
  return {nodes,calls,stored,window,document,session,
    flush:()=>intervals[0](),
    async tick(ms,sync=false){for(let t=0;t<ms;t+=100){wall+=100;const entry=frames.entries().next().value;if(entry){frames.delete(entry[0]);entry[1](wall);}if(sync && wall%600===0)await intervals[0]();}},
    input(id,value){const n=nodes.get(id);n.value=value;n.listeners.input({target:n});},
    toggle(id,value){const n=nodes.get(id);n.checked=value;n.onchange({target:n});},
    visibility(hidden){document.hidden=hidden;documentListeners.visibilitychange();}
  };
}

test('real controller renders a cycle and replays offline FULL/CLEARED as simulated', async()=>{
  const c=controller();c.window.SmartBinLab.setUser({username:'manager',role:'manager'});
  await c.nodes.get('lab-connect').onclick();await c.flush();const before=c.calls.length;
  c.toggle('lab-offline',true);c.nodes.get('lab-cycle').onclick();await c.tick(35000,true);
  assert.equal(c.calls.length,before,'No requests while disconnected');
  assert.equal(c.nodes.get('lab-lid-state').textContent,'\u0110\u00f3ng');
  assert.equal(c.nodes.get('lab-alert-state').textContent,'B\u00ecnh th\u01b0\u1eddng');
  c.toggle('lab-offline',false);await c.tick(6000,true);
  const types=c.stored.filter(m=>m.kind==='event').map(m=>m.event_type);
  assert.deepEqual(types,['FULL','CLEARED']);
  assert(c.stored.every(m=>m.source==='simulated' && m.time_quality==='simulated'));
  assert(c.stored.every(m=>!Object.hasOwn(m,'physicalFill')),'Hidden scenario truth must not leak into telemetry features');
  c.window.SmartBinLab.setUser(null);
});

test('viewer previews locally; hidden tab pauses the model; logout stops requests',async()=>{
  const c=controller();c.window.SmartBinLab.setUser({username:'viewer',role:'viewer'});
  assert.equal(c.nodes.get('lab-connect').disabled,true);await c.nodes.get('lab-connect').onclick();assert.equal(c.calls.length,0);
  c.input('lab-hand-range',22);await c.tick(1000);
  c.nodes.get('lab-hand-toggle').onclick();await c.tick(2000);assert.equal(c.nodes.get('lab-lid-state').textContent,'\u0110ang m\u1edf');
  const time=c.nodes.get('lab-clock').textContent;c.visibility(true);await c.tick(5000);assert.equal(c.nodes.get('lab-clock').textContent,time);
  c.visibility(false);c.window.SmartBinLab.setUser(null);await c.tick(1000,true);assert.equal(c.calls.length,0);
});

test('lost ACK retries identical bytes; authenticated login generation isolates delayed responses',async()=>{
  let rejected=false;
  const c=controller(async(url,opts,response,session)=>{
    if(url==='/api/lab/sessions')return response(session);
    if(!rejected){rejected=true;throw new TypeError('Lost ACK after server stored');}
    const m=JSON.parse(opts.body);return response({...m,stored:true});
  });
  c.window.SmartBinLab.setUser({username:'manager',role:'manager'});await c.nodes.get('lab-connect').onclick();await c.flush();
  await c.tick(2000);await c.flush();
  const messages=c.calls.filter(c=>c.body);assert.equal(messages.length,2);assert.equal(messages[0].body,messages[1].body);
  c.window.SmartBinLab.setUser(null);
  let finish;
  const d=controller((url,opts,response,session)=>new Promise(resolve=>{finish=()=>resolve(response(session));}));
  d.window.SmartBinLab.setUser({username:'same-owner',role:'manager'});
  const pending=d.nodes.get('lab-connect').onclick();
  d.window.SmartBinLab.setUser(null);d.window.SmartBinLab.setUser({username:'same-owner',role:'manager'});
  finish();await pending;
  assert.equal(d.nodes.get('lab-history-link').hidden,true,'Old response must not attach to a new login');
  d.window.SmartBinLab.setUser(null);
});


test('Telegram opt-in uses current sequence cutoff and resets on logout', async()=>{
  const c=controller((url,opts,response,session)=>{
    if(url==='/api/lab/sessions')return response({...session,telegram_available:true,recipient_hint:'...6789',notification_mode:'preview_only'});
    if(url.endsWith('/notifications'))return response({notification_mode:JSON.parse(opts.body).enabled?'telegram_opt_in':'preview_only',telegram_available:true,recipient_hint:'...6789'});
    return response({...JSON.parse(opts.body),stored:true});
  });
  c.window.SmartBinLab.setUser({username:'manager',role:'manager'});
  assert(c.nodes.get('lab-telegram').disabled);
  await c.nodes.get('lab-connect').onclick();await c.flush();
  assert.equal(c.nodes.get('lab-telegram').checked,false);
  c.nodes.get('lab-telegram').checked=true;
  await c.nodes.get('lab-telegram').onchange({target:c.nodes.get('lab-telegram')});
  assert.deepEqual(JSON.parse(c.calls.find(v=>v.url.endsWith('/notifications')).body),{enabled:true,after_seq:1});
  assert(c.nodes.get('lab-telegram').checked);
  c.window.SmartBinLab.setUser(null);
  assert.equal(c.nodes.get('lab-telegram').checked,false);assert(c.nodes.get('lab-telegram').disabled);
});

test('ambiguous Telegram toggle stops uploads until a fresh session', async()=>{
  const c=controller((url,opts,response,session)=>{
    if(url==='/api/lab/sessions')return response({...session,telegram_available:true,notification_mode:'preview_only'});
    if(url.endsWith('/notifications'))throw new TypeError('Lost response after commit');
    return response({...JSON.parse(opts.body),stored:true});
  });
  c.window.SmartBinLab.setUser({username:'manager',role:'manager'});await c.nodes.get('lab-connect').onclick();
  c.nodes.get('lab-telegram').checked=true;
  await c.nodes.get('lab-telegram').onchange({target:c.nodes.get('lab-telegram')});
  const before=c.calls.length;await c.tick(10000,true);
  assert.equal(c.calls.length,before);assert(c.nodes.get('lab-telegram').disabled);
  c.window.SmartBinLab.setUser(null);
});


test('fault-set transitions report simultaneous and partial recovery without false RECOVERED',()=>{
  const m=new BinSimulation();m.advance(4000);m.drainEvents();
  m.fillSensorFault=true;m.advance(1800);
  assert.deepEqual(m.snapshot().faultCodes,['FILL_SENSOR']);
  m.handSensorFault=true;m.advance(1000);
  assert.deepEqual(m.snapshot().faultCodes,['HAND_SENSOR','FILL_SENSOR']);
  m.handSensorFault=false;m.setHand(100);m.advance(1000);assert(m.resetFault());m.advance(200);
  assert.deepEqual(m.snapshot().faultCodes,['FILL_SENSOR']);
  assert.equal(m.drainEvents().filter(e=>e.type==='RECOVERED').length,0);
  m.fillSensorFault=false;m.advance(4000);
  const recovered=m.drainEvents().filter(e=>e.type==='RECOVERED');
  assert.equal(recovered.length,1);assert.deepEqual(recovered[0].snapshot.faultCodes,[]);
});

test('level sensor recovery needs a fresh full filter window',()=>{
  const m=new BinSimulation();m.advance(4000);m.fillSensorFault=true;m.advance(1100);
  assert(m.fillFaultLatched);m.fillSensorFault=false;m.advance(400);
  assert.equal(m.snapshot().fill,null);assert(m.fillFaultLatched);
  m.advance(3000);assert.equal(m.quality,'valid');assert(!m.fillFaultLatched);
});

test('mounted LED follows filtered measurement, suspends with lid, and shows confirmed faults',async()=>{
  const c=controller();c.window.SmartBinLab.setUser({username:'manager',role:'manager'});
  assert.equal(c.nodes.get('lab-display-value').textContent,c.nodes.get('lab-measured').textContent);
  await c.tick(4500);assert.equal(c.nodes.get('lab-display-value').textContent,'22.0%');
  c.input('lab-fill-range',90);
  assert.equal(c.nodes.get('lab-display-value').textContent,'22.0%','Slider must not immediately replace filtered measurement');
  await c.tick(6000);assert.equal(c.nodes.get('lab-display-value').textContent,'90.0%');
  assert.equal(c.nodes.get('lab-display').dataset.tone,'full');
  c.nodes.get('lab-hand-toggle').onclick();await c.tick(1500);
  assert.equal(c.nodes.get('lab-display-value').textContent,c.nodes.get('lab-measured').textContent);
  assert(!c.nodes.get('lab-display-value').textContent.includes('%'));
  c.toggle('lab-fault-hand',true);await c.tick(1500);
  assert.equal(c.nodes.get('lab-display').dataset.tone,'fault');
  assert(c.nodes.get('lab-display-description').textContent.includes('tay'));
  c.window.SmartBinLab.setUser(null);
});

test('controller queues only diagnosed fault codes with null fill and sends recovery after repair',async()=>{
  const c=controller();c.window.SmartBinLab.setUser({username:'manager',role:'manager'});
  await c.nodes.get('lab-connect').onclick();await c.tick(4500,true);
  c.toggle('lab-fault-fill',true);await c.tick(2500,true);
  c.toggle('lab-fault-fill',false);await c.tick(5000,true);
  const faulty=c.stored.find(m=>m.event_type==='FAULT'), recovered=c.stored.find(m=>m.event_type==='RECOVERED');
  assert(faulty);assert.deepEqual(faulty.fault_codes,['FILL_SENSOR']);assert.equal(faulty.fill_pct,null);
  assert(recovered);assert.deepEqual(recovered.fault_codes,[]);assert.equal(recovered.quality,'valid');
  c.window.SmartBinLab.setUser(null);
});


test('Wi-Fi panel stops every device request offline, then heartbeats and replays on reconnect',async()=>{
  const c=controller(undefined,true);c.window.SmartBinLab.setUser({username:'manager',role:'manager'});
  await c.nodes.get('lab-connect').onclick();await c.flush();
  assert.equal(c.nodes.get('lab-wifi-card').dataset.state,'connected');
  c.nodes.get('lab-wifi-toggle').onclick();const before=c.calls.length;
  c.nodes.get('lab-cycle').onclick();await c.tick(35000,true);
  assert.equal(c.calls.length,before,'No loss announcement can be faked by sending through disconnected device path');
  assert.equal(c.nodes.get('lab-wifi-card').dataset.state,'offline');
  c.nodes.get('lab-wifi-toggle').onclick();await c.tick(7000,true);
  assert.equal(c.nodes.get('lab-wifi-card').dataset.state,'connected');
  assert(c.calls.filter(call=>call.url.endsWith('/connection')).length>=3);
  assert.deepEqual(c.stored.filter(m=>m.kind==='event').map(m=>m.event_type),['FULL','CLEARED']);
  c.window.SmartBinLab.setUser(null);
});

test('Wi-Fi heartbeat continues on wall clock while sensor animation is paused or tab hidden',async()=>{
  const c=controller(undefined,true);c.window.SmartBinLab.setUser({username:'manager',role:'manager'});
  await c.nodes.get('lab-connect').onclick();await c.tick(2000,true);
  c.nodes.get('lab-pause').onclick();const clock=c.nodes.get('lab-clock').textContent;
  const before=c.calls.filter(v=>v.url.endsWith('/connection')).length;
  c.visibility(true);await c.tick(15000,true);
  assert.equal(c.nodes.get('lab-clock').textContent,clock);
  assert(c.calls.filter(v=>v.url.endsWith('/connection')).length-before>=4);
  c.visibility(false);c.window.SmartBinLab.setUser(null);
  const stopped=c.calls.length;await c.tick(20000,true);assert.equal(c.calls.length,stopped);
});

test('late heartbeat ACK cannot mark a manually disconnected thùng as connected',async()=>{
  let count=0,finish;
  const c=controller((url,options,response,session)=>{
    if(url==='/api/lab/sessions')return response(session);
    if(url.endsWith('/connection')){
      const ack={...session,heartbeat_seq:JSON.parse(options.body).seq,connection_state:'connected'};
      if(++count===1)return response(ack);
      return new Promise(resolve=>{finish=()=>resolve(response(ack));});
    }
    return response({...JSON.parse(options.body),stored:true});
  },true);
  c.window.SmartBinLab.setUser({username:'manager',role:'manager'});await c.nodes.get('lab-connect').onclick();
  await c.tick(3500);const pending=c.flush();
  c.nodes.get('lab-wifi-toggle').onclick();finish();await pending;
  assert.equal(c.nodes.get('lab-wifi-card').dataset.state,'offline');
  c.window.SmartBinLab.setUser(null);
});
