"""Smoke demo cô lập; không dùng CSDL/credential/Telegram thật."""
import json
from pathlib import Path
import tempfile
import time

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth import create_user
from backend.config import Settings
from backend.db import Database
from backend.ml import Predictor,update_predictions
from backend.routing import RouteRequest,solve
from backend.schema import Message
from simulator.generate import generate,register_bins


def run():
    with tempfile.TemporaryDirectory(prefix='smartbin-smoke-') as folder:
        cfg=Settings(db=Path(folder)/'demo.sqlite3',mqtt_enabled=False,telegram_dry_run=True)
        db=Database(cfg.db);register_bins(db,30)
        create_user(db,'smoke-manager','test-password-smoke','manager')
        count=0;max_bytes=0
        for r in generate(30,.1,42):
            m=Message.model_validate(r['message']);db.ingest(m);count+=1
            max_bytes=max(max_bytes,len(m.model_dump_json().encode()))
        update_predictions(db,Predictor(cfg.model),cfg)
        with TestClient(create_app(cfg,background=False)) as c:
            assert c.post('/api/login',json={'username':'smoke-manager','password':'test-password-smoke'}).status_code==200
            states=c.get('/api/bins').json();assert len(states)==30
            result=c.post('/api/routes',json={'seconds':2}).json()
            assert 'routes' in result
            assert c.get('/static/app.js').status_code==200
        # Scale case: 100 simulated full bins, same capacity/depot constraints in both methods.
        big=[{'id':f'scale-{i:03}','source':'simulated','lat':10.77+(i//10)*.009,
              'lon':106.66+(i%10)*.008,'capacity_l':120,'fill_pct':90,'usable':True,'prediction':{}} for i in range(100)]
        scale=solve(big,RouteRequest(vehicles=10,capacity_l=1500,seconds=3))
        summary={'message_count':count,'max_normalized_json_bytes':max_bytes,'bins':len(states),
                 'prediction_available':sum(s['prediction'].get('status')=='available' for s in states),
                 'demo_route':result,'scale_100_route':scale,
                 'scope':'HTTP/API/static asset smoke; UI browser not exercised. All inputs simulated. No external Telegram or hardware.'}
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/smoke.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('demo_route','scale_100_route')},ensure_ascii=True))
    for k in ('demo_route','scale_100_route'):
        r=summary[k];print(k,json.dumps({'distance_m':r['total_distance_m'],'baseline_m':r['baseline']['distance_m'],
                                        'unserved':len(r['unserved']),'comparison':r['comparison']},ensure_ascii=True))


if __name__=='__main__':run()
