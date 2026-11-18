import copy
import random
import time
from datetime import datetime,timezone

from backend.schema import Message


def watch(db,latest,seed=42,interval=60):
    """Real wall-clock updates to local simulated DB. No MQTT claim for this profile."""
    rng=random.Random(seed);status={b['id']:b for b in db.states()}
    full={k:bool(status[k]['full']) for k in latest};high={k:0 for k in latest};low={k:0 for k in latest}
    print('Live demo: cập nhật CSDL mô phỏng mỗi 60 giây. Ctrl+C để dừng.')
    while True:
        time.sleep(interval)
        now=datetime.now(timezone.utc).isoformat()
        for bin_id,previous in list(latest.items()):
            m=copy.deepcopy(previous);m['seq']+=1;m['uptime_ms']+=interval*1000;m['sampled_at']=now
            fill=previous['fill_pct'] if previous['fill_pct'] is not None else rng.uniform(5,90)
            fill=fill+rng.uniform(0,.8)
            if fill>96 and rng.random()<.2:fill=rng.uniform(3,10)
            fill=max(0,min(100,fill));valid=rng.random()>.02
            m['quality']='valid' if valid else 'fault';m['fill_pct']=round(fill,3) if valid else None
            m['distance_cm']=round(30-26*fill/100,3) if valid else None
            m['lid_open_count']+=rng.randint(0,2);m['kind']='telemetry';m['event_type']=None
            high[bin_id]=min(3,high[bin_id]+1) if valid and fill>=80 else 0
            low[bin_id]=min(3,low[bin_id]+1) if valid and fill<=75 else 0
            if not full[bin_id] and high[bin_id]>=3:full[bin_id]=True;m['kind']='event';m['event_type']='FULL'
            if full[bin_id] and low[bin_id]>=3:full[bin_id]=False;m['kind']='event';m['event_type']='CLEARED'
            db.ingest(Message.model_validate(m));latest[bin_id]=m

