"""Dự báo một chân trời cố định. Không suy diễn thành thời gian còn lại tới đầy."""
import bisect
import hashlib
import json
import math
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import joblib
import sklearn
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

LOOKBACK=1800
PIPELINE_VERSION='1.0'
FEATURES=['fill_now','fill_lag15','fill_lag30','rate_per_hour','opens_30min','hour_sin','hour_cos','day_sin','day_cos']


def timestamp(m):
    value=m.get('sampled_at')
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp() if value else None


def features(history):
    valid=[m for m in history if m.get('quality')=='valid' and m.get('fill_pct') is not None and timestamp(m) is not None]
    if len(valid)<3: return None
    valid.sort(key=timestamp)
    current=valid[-1];t=timestamp(current)
    if any(timestamp(b)-timestamp(a)>900 for a,b in zip(valid,valid[1:]) if timestamp(b)>t-LOOKBACK): return None
    def lag(seconds):
        candidates=[m for m in valid if timestamp(m)<=t-seconds]
        if not candidates: return None
        m=candidates[-1]
        return m if t-seconds-timestamp(m)<=300 else None
    a,b=lag(900),lag(1800)
    if a is None or b is None or any(m['boot_id']!=current['boot_id'] for m in (a,b)): return None
    delta=current['fill_pct']-b['fill_pct']
    rate=max(0,delta*3600/(t-timestamp(b)))
    opens=max(0,current['lid_open_count']-b['lid_open_count'])
    dt=datetime.fromtimestamp(t,timezone(timedelta(hours=7)))
    return np.array([current['fill_pct'],a['fill_pct'],b['fill_pct'],rate,opens,
                     math.sin(2*math.pi*dt.hour/24),math.cos(2*math.pi*dt.hour/24),
                     math.sin(2*math.pi*dt.weekday()/7),math.cos(2*math.pi*dt.weekday()/7)],dtype=float)


def baselines(x,horizon):
    return {'persistence':x[:,0], 'linear':np.clip(x[:,0]+x[:,3]*horizon/3600,0,100)}


def metrics(y,p):
    actual=np.asarray(y)>=80;positive=np.asarray(p)>=80
    return {'mae_pp':float(mean_absolute_error(y,p)), 'rmse_pp':float(math.sqrt(mean_squared_error(y,p))),
            'threshold_80':{'tp':int(np.sum(actual & positive)),'fp':int(np.sum(~actual & positive)),
                            'fn':int(np.sum(actual & ~positive)),'tn':int(np.sum(~actual & ~positive))}}


def dataset(records,horizon):
    groups=defaultdict(list)
    for r in records:
        m=r['message']
        if timestamp(m) is not None: groups[m['bin_id']].append(r)
    rows=[]
    for group in groups.values():
        group.sort(key=lambda r:timestamp(r['message']))
        times=[timestamp(r['message']) for r in group]
        for i,r in enumerate(group):
            m=r['message'];t=times[i]
            # Do not look beyond i while creating features.
            begin=bisect.bisect_left(times,t-LOOKBACK-300)
            if m['quality']!='valid': continue
            x=features([v['message'] for v in group[begin:i+1]])
            if x is None: continue
            target=bisect.bisect_left(times,t+horizon)
            if target>=len(group) or times[target]-(t+horizon)>300: continue
            future=group[target]['message']
            if future['quality']!='valid' or future['boot_id']!=m['boot_id']: continue
            rows.append((t,times[target],x,future['fill_pct'],r.get('anomaly_label'),m['source']))
    return sorted(rows,key=lambda r:r[0])


def train(input_path,output_path,horizon=3600):
    records=[json.loads(line) for line in Path(input_path).read_text(encoding='utf-8').splitlines() if line.strip()]
    rows=dataset(records,horizon)
    if len(rows)<300: raise ValueError('Cần ít nhất 300 cặp dữ liệu hợp lệ và lịch sử đủ dài')
    sources={r[5] for r in rows}
    if len(sources)!=1: raise ValueError('Huấn luyện và đánh giá riêng dữ liệu thật/mô phỏng')
    lo,hi=rows[0][0],rows[-1][1];cut1=lo+.6*(hi-lo);cut2=lo+.8*(hi-lo)
    # Purge future targets and embargo the full feature lookback at each boundary.
    splits={'train':[r for r in rows if r[1]<cut1],
            'validation':[r for r in rows if r[0]-LOOKBACK-300>cut1 and r[1]<cut2],
            'test':[r for r in rows if r[0]-LOOKBACK-300>cut2]}
    if min(map(len,splits.values()))<30: raise ValueError('Không đủ mẫu sau khoảng cách chống leakage')
    def arrays(name):
        s=splits[name];return np.stack([r[2] for r in s]),np.array([r[3] for r in s])
    xt,yt=arrays('train');xv,yv=arrays('validation');xe,ye=arrays('test')
    candidates={};forests={}
    for depth in (8,14):
        rf=RandomForestRegressor(n_estimators=80,max_depth=depth,min_samples_leaf=8,random_state=42,n_jobs=1)
        rf.fit(xt,yt);key=f'random_forest_depth{depth}';forests[key]=rf;candidates[key]=metrics(yv,rf.predict(xv))
    for key,p in baselines(xv,horizon).items(): candidates[key]=metrics(yv,p)
    chosen=min(candidates,key=lambda k:candidates[k]['mae_pp'])
    best_rf=min(forests,key=lambda k:candidates[k]['mae_pp']);forest=forests[best_rf]
    test={k:metrics(ye,p) for k,p in baselines(xe,horizon).items()}
    test[best_rf]=metrics(ye,forest.predict(xe))
    # Train anomaly detector only on annotated normal train observations when labels exist.
    normal=np.stack([r[2] for r in splits['train'] if r[4] is not True])
    isolation=IsolationForest(n_estimators=100,contamination=.025,random_state=42,n_jobs=1).fit(normal)
    anomaly_labels=[r[4] for r in splits['test']]
    anomaly_report={'status':'unlabeled'}
    if all(v is not None for v in anomaly_labels):
        labels=np.array(anomaly_labels,dtype=bool)
        def confusion(pred):
            return {'tp':int(sum(labels&pred)),'fp':int(sum(~labels&pred)),'fn':int(sum(labels&~pred)),
                    'tn':int(sum(~labels&~pred)), 'false_positive_rate':float(sum(~labels&pred)/max(1,sum(~labels)))}
        anomaly_report={'isolation_forest':confusion(isolation.predict(xe)==-1),
                        'rule_jump_25pp':confusion(np.abs(xe[:,0]-xe[:,1])>25),
                        'interpretation':'Bất thường số đo, không phải chẩn đoán lỗi phần cứng.'}
    data_sha=hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
    version=hashlib.sha256((data_sha+str(horizon)+str(FEATURES)+PIPELINE_VERSION+sklearn.__version__).encode()).hexdigest()[:16]
    report={'version':version,'source':next(iter(sources)),'horizon_seconds':horizon,'features':FEATURES,
            'pipeline_version':PIPELINE_VERSION,'sklearn_version':sklearn.__version__,'data_sha256':data_sha,
            'units':'điểm phần trăm','selected_using_validation':chosen,'rf_candidate':best_rf,
            'validation':candidates,'test':test,'anomaly_test':anomaly_report,
            'split':{k:{'count':len(v),'first_feature':v[0][0],'last_target':v[-1][1]} for k,v in splits.items()},
            'split_policy':'Global chronological 60/20/20; purge horizon; embargo lookback+300s. Cùng nhóm thùng; không chứng minh khái quát sang thùng mới hoặc chu kỳ mới độc lập.',
            'target_policy':'First observation at/after horizon, tolerance <=300s; discard if invalid; no interpolation.',
            'threshold_definition':'Mỗi mẫu: dự đoán >=80 so với số đo sau chân trời >=80; không phải đánh giá thời gian tới đầy.',
            'limitations':'Dữ liệu simulated chỉ kiểm tra pipeline. Chu kỳ thu gom có thể cắt qua các tập; chưa đánh giá holdout theo chu kỳ/thùng.'}
    output_path=Path(output_path);output_path.parent.mkdir(parents=True,exist_ok=True)
    joblib.dump({'report':report,'forest':forest,'isolation':isolation},output_path)
    output_path.with_suffix('.metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


class Predictor:
    def __init__(self,path):
        self.artifact=None;self.load_error=False
        if Path(path).is_file():
            try: self.artifact=joblib.load(path) # Only administrator-controlled local artifact; no upload endpoint.
            except Exception: self.load_error=True

    def predict(self,history,source,now=None,stale_seconds=360):
        now=time.time() if now is None else now
        if not history: return {'status':'unavailable','reason':'Thiếu lịch sử'}
        latest=history[-1];stamp=timestamp(latest)
        if latest.get('quality')!='valid' or latest.get('lid_state')=='FAULT' or stamp is None or now-stamp>stale_seconds or stamp>now+300:
            return {'status':'unavailable','reason':'Dữ liệu lỗi/cũ/chưa biết giờ'}
        x=features(history)
        if x is None: return {'status':'unavailable','reason':'Chưa đủ lịch sử 30 phút liên tục'}
        horizon=self.artifact['report']['horizon_seconds'] if self.artifact else 3600
        method='linear';version=None;anomaly=None;reason='Chưa có model; baseline có nhãn'
        value=baselines(x.reshape(1,-1),horizon)[method][0]
        if self.artifact and self.artifact['report']['source']==source:
            try:
                method=self.artifact['report']['selected_using_validation'];version=self.artifact['report']['version']
                if method.startswith('random_forest'): value=self.artifact['forest'].predict(x.reshape(1,-1))[0]
                else: value=baselines(x.reshape(1,-1),horizon)[method][0]
                anomaly=bool(self.artifact['isolation'].predict(x.reshape(1,-1))[0]==-1);reason=None
            except Exception:
                method='linear';value=baselines(x.reshape(1,-1),horizon)['linear'][0]
                version=None;anomaly=None;reason='Lỗi suy luận; dùng baseline'
        elif self.artifact: reason='Model huấn luyện từ nguồn khác; chỉ dùng baseline'
        return {'status':'available','fill_pct':round(float(np.clip(value,0,100)),2),'method':method,
                'horizon_seconds':horizon,'model_version':version,'source':source,'sampled_at':latest['sampled_at'],
                'created_at':now,'valid_until':stamp+stale_seconds,'anomaly':anomaly,'reason':reason}


def current_prediction(db,predictor,settings,b,now=None):
    now=time.time() if now is None else now
    if not b['usable']:return {'status':'unavailable','reason':'Thiết bị offline/cũ/lỗi/chưa biết giờ'}
    history=[m for m in db.history(b['id'],now-LOOKBACK-900,now+300,1000)
             if m['boot_id']==b['boot_id'] and m['seq']<=b['seq']]
    if not history or history[-1]['seq']!=b['seq']:
        return {'status':'unavailable','reason':'Thời gian trong phiên bị đảo thứ tự hoặc thiếu bản tin hiện tại'}
    return predictor.predict(history,b['source'],now,settings.stale_seconds)


def update_predictions(db,predictor,settings):
    now=time.time()
    for b in db.states(settings.stale_seconds,now):
        pred=current_prediction(db,predictor,settings,b,now)
        with db.connect() as c:
            c.execute('INSERT INTO predictions VALUES(?,?,?) ON CONFLICT(bin_id) DO UPDATE SET created_at=excluded.created_at,payload=excluded.payload',(b['id'],now,json.dumps(pred)))
            if not b['id'].startswith('lab-') and b['usable'] and b['fill_pct']<b['full_on_pct'] and pred.get('fill_pct',0)>=b['full_on_pct'] and pred.get('status')=='available' and pred.get('anomaly') is not True:
                previous=c.execute('SELECT value FROM kv WHERE key=?',('early:'+b['id'],)).fetchone()
                if not previous or now-float(previous[0])>=3600:
                    db.enqueue(c,f'early:{b["id"]}:{int(now//3600)}',f'[{b["source"]}] DỰ ĐOÁN {b["id"]}: {pred["fill_pct"]}% sau {pred["horizon_seconds"]//60} phút; phương pháp {pred["method"]}.',now)
                    c.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('early:'+b['id'],str(now)))
