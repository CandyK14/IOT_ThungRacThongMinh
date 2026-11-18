import argparse
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path


def generate(bins=30, days=2, seed=42, step_seconds=300, end=None):
    rng = random.Random(seed)
    end = int(end or datetime.now(timezone.utc).timestamp())
    start = end - int(days * 86400)
    states = [{'fill':rng.uniform(5,90), 'rate':rng.uniform(1,8), 'opens':0, 'full':False, 'high':0,'low':0} for _ in range(bins)]
    for step, stamp in enumerate(range(start, end+1, step_seconds)):
        hour = datetime.fromtimestamp(stamp,timezone.utc).hour
        for i,s in enumerate(states):
            # Missing observations retain real timestamps; no compressed training clock.
            if rng.random()<0.025: continue
            if step%48==0: s['rate']=rng.uniform(1,8)
            growth=s['rate']*(1.5 if 1<=hour<=11 else .5)*step_seconds/3600
            s['fill']=min(100,s['fill']+growth*rng.uniform(.4,1.6))
            if s['fill']>=96 and rng.random()<.25: s['fill']=rng.uniform(2,12)
            s['opens']+=rng.randint(0,5)  # Opening a lid is not a fixed quantity of waste.
            anomaly=rng.random()<.015
            observed=max(0,min(100,s['fill']+rng.gauss(0,1.1)+(rng.choice([-35,35]) if anomaly else 0)))
            quality='fault' if rng.random()<.02 else 'valid'
            s['high']=min(3,s['high']+1) if quality=='valid' and observed>=80 else 0
            s['low']=min(3,s['low']+1) if quality=='valid' and observed<=75 else 0
            event=None
            if not s['full'] and s['high']>=3: s['full']=True;event='FULL'
            if s['full'] and s['low']>=3: s['full']=False;event='CLEARED'
            message=dict(version=1,bin_id=f'sim-{i+1:03}',boot_id=f'sim-{seed}-{i+1}',boot_no=1,
                         seq=step+1,kind='event' if event else 'telemetry',event_type=event,
                         source='simulated',sampled_at=datetime.fromtimestamp(stamp,timezone.utc).isoformat(),
                         time_quality='simulated',uptime_ms=(stamp-start)*1000,quality=quality,
                         fill_pct=round(observed,3) if quality=='valid' else None,
                         distance_cm=round(30-26*observed/100,3) if quality=='valid' else None,
                         lid_state='CLOSED',lid_open_count=s['opens'],battery_mv=None)
            yield {'message':message,'anomaly_label':bool(anomaly and quality=='valid')}


def register_bins(db, count):
    for i in range(count):
        db.register(f'sim-{i+1:03}',f'Thùng mô phỏng {i+1}',10.77+(i//10)*.009,
                    106.66+(i%10)*.008,120,'simulated')


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description='Sinh lịch sử mô phỏng, không gửi Telegram')
    p.add_argument('--bins',type=int,default=12,choices=range(1,101))
    p.add_argument('--days',type=float,default=14)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--output',type=Path,default=Path('data/simulated.jsonl'))
    p.add_argument('--end',help='ISO 8601 có timezone, cố định để tái lập cả lịch giờ/ngày; mặc định giờ hiện tại')
    a=p.parse_args()
    if not 0<a.days<=365: p.error('days cần trong (0,365]')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    end=None
    if a.end:
        date=datetime.fromisoformat(a.end.replace('Z','+00:00'))
        if date.tzinfo is None:p.error('--end phải có timezone')
        end=date.timestamp()
    with a.output.open('x',encoding='utf-8') as f:
        for r in generate(a.bins,a.days,a.seed,end=end): f.write(json.dumps(r,separators=(',',':'))+'\n')
    print(f'Đã tạo dữ liệu MÔ PHỎNG: {a.output}; bước 300 giây, không tua nhanh thời gian huấn luyện.')


if __name__=='__main__': main()
