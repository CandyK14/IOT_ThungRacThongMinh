import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from .auth import create_user
from .config import Settings
from .db import Database
from .schema import Message


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description='Quản trị local; không gửi Telegram hoặc điều khiển thiết bị')
    sub=p.add_subparsers(dest='command',required=True)
    user=sub.add_parser('user');user.add_argument('username');user.add_argument('--role',choices=['viewer','manager'],default='manager')
    demo=sub.add_parser('demo');demo.add_argument('--bins',type=int,default=30,choices=range(20,101));demo.add_argument('--seed',type=int,default=42)
    demo.add_argument('--watch',action='store_true',help='Cập nhật liên tục CSDL mô phỏng mỗi 60 giây; Ctrl+C để dừng')
    imp=sub.add_parser('import');imp.add_argument('file',type=Path);imp.add_argument('--source',choices=['real','simulated'],required=True)
    train=sub.add_parser('train');train.add_argument('file',type=Path);train.add_argument('--output',type=Path,default=Path('data/model.joblib'));train.add_argument('--horizon-minutes',type=int,default=60,choices=range(5,361))
    evaluate=sub.add_parser('evaluate');evaluate.add_argument('model',type=Path)
    pred=sub.add_parser('predict');pred.add_argument('bin_id')
    a=p.parse_args();cfg=Settings();db=Database(cfg.db)
    if a.command=='user':
        create_user(db,a.username,os.getenv('BIN_NEW_PASSWORD') or getpass.getpass('Mật khẩu (ít nhất 12 ký tự): '),a.role)
        print('Đã tạo người dùng. Mật khẩu không ghi vào repo.')
    elif a.command=='demo':
        from simulator.generate import generate,register_bins
        register_bins(db,a.bins)
        # New random boot session with increasing boot_no lets a second demo run coexist safely.
        import secrets
        with db.connect() as c:
            boot=c.execute("SELECT COALESCE(MAX(boot_no),0)+1 FROM boots WHERE bin_id LIKE 'sim-%'").fetchone()[0]
        session=secrets.token_hex(6);count=0;latest={}
        for r in generate(a.bins,days=.1,seed=a.seed):
            r['message']['boot_no']=boot;r['message']['boot_id']=f'demo-{session}'
            db.ingest(Message.model_validate(r['message']));count+=1
            latest[r['message']['bin_id']]=r['message']
        print(f'Đã nạp {count} bản tin MÔ PHỎNG, {a.bins} thùng, DB={cfg.db}. Telegram chưa được gửi.')
        if a.watch:
            from simulator.live import watch
            try:watch(db,latest,a.seed)
            except KeyboardInterrupt:print('Đã dừng mô phỏng.')
    elif a.command=='import':
        count=0
        with a.file.open(encoding='utf-8') as f:
            for line in f:
                envelope=json.loads(line);m=Message.model_validate(envelope['message'])
                if m.source!=a.source:raise ValueError('Sai nguồn dữ liệu; không tự đổi nhãn real/simulated')
                db.ingest(m);count+=1
        print(f'Nhập {count} bản tin. Thùng phải được đăng ký trước bằng API quản lý.')
    elif a.command=='train':
        from .ml import train as fit
        report=fit(a.file,a.output,a.horizon_minutes*60)
        print(json.dumps({'source':report['source'],'selected':report['selected_using_validation'],'test':report['test']},ensure_ascii=False,indent=2))
    elif a.command=='evaluate':
        print(a.model.with_suffix('.metrics.json').read_text(encoding='utf-8'))
    elif a.command=='predict':
        from .ml import Predictor,current_prediction
        state=next((b for b in db.states() if b['id']==a.bin_id),None)
        print(json.dumps(current_prediction(db,Predictor(cfg.model),cfg,state) if state else {'status':'unavailable','reason':'Không có mã thùng'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
