import time
from datetime import datetime,timezone

from backend.ml import Predictor,current_prediction


def test_prediction_cannot_use_previous_boot_with_newer_clock(db,cfg,message):
    now=time.time()
    for i in range(8):
        stamp=now+30-(7-i)*300
        db.ingest(message(seq=i+1,sampled_at=datetime.fromtimestamp(stamp,timezone.utc).isoformat(),
                          fill_pct=float(30+i),lid_open_count=i))
    db.ingest(message(boot_no=2,boot_id='new-boot',seq=1,sampled_at=datetime.fromtimestamp(now,timezone.utc).isoformat()))
    b=db.states(now=now)[0];assert b['boot_id']=='new-boot' and b['usable']
    p=current_prediction(db,Predictor(cfg.model),cfg,b,now)
    assert p['status']=='unavailable' # Current boot has one sample, regardless of old clock skew.
