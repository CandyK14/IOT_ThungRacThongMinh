"""Một worker cho mỗi DB/bot. Dry-run mặc định, không log token hoặc URL."""
import json
import logging
import re
import time

import httpx


class _RedactBotURL(logging.Filter):
    def filter(self,record):
        record.msg=re.sub(r'(api\.telegram\.org/bot)[^/\s\'\"]+',r'\1[REDACTED]',record.getMessage())
        record.args=()
        return True


# httpx logs complete request URLs at INFO when operators enable verbose logging.
logging.getLogger('httpx').addFilter(_RedactBotURL())


class TelegramWorker:
    def __init__(self,db,settings,transport=None):
        self.db=db;self.settings=settings
        self.poll_after=0
        self.http=httpx.Client(timeout=httpx.Timeout(10,connect=4),transport=transport,follow_redirects=False)

    def close(self): self.http.close()

    def request(self,method,body):
        try:
            response=self.http.post(f'https://api.telegram.org/bot{self.settings.telegram_token}/{method}',json=body)
            data=response.json()
            if response.status_code==200 and data.get('ok') is True:return True,data,0
            delay=max(1,min(86400,int(data.get('parameters',{}).get('retry_after',30))))
            return False,{},delay
        except (httpx.HTTPError,ValueError,TypeError,AttributeError):
            return False,{},30

    def deliver(self,now=None,stop=None):
        now=time.time() if now is None else now
        with self.db.connect() as c:
            rows=c.execute("SELECT * FROM outbox WHERE status='pending' AND next_at<=? ORDER BY id LIMIT 4",(now,)).fetchall()
        for r in rows:
            if stop is not None and stop.is_set():break
            if self.settings.telegram_dry_run:
                status='dry_run';ok=True;delay=0
            else:
                ok,_,delay=self.request('sendMessage',{'chat_id':r['chat_id'] or self.settings.telegram_chat,'text':r['text']})
                status='sent' if ok else 'failed' if r['attempts']+1>=8 else 'pending'
            with self.db.connect() as c:
                c.execute('UPDATE outbox SET status=?,attempts=attempts+1,next_at=?,last_error=? WHERE id=?',
                          (status,now+max(delay,min(3600,2**(r['attempts']+1))),None if ok else 'Telegram/API/timeout; xem cấu hình, không log URL',r['id']))

    def process_update(self,update,now=None):
        now=time.time() if now is None else now
        message=update.get('message',{});chat=str(message.get('chat',{}).get('id',''))
        user=str(message.get('from',{}).get('id',''))
        allowed={s.strip() for s in self.settings.telegram_users.split(',') if s.strip()}
        if chat!=self.settings.telegram_chat or (allowed and user not in allowed):return False
        text=message.get('text','').split();command=text[0].split('@')[0] if text else ''
        if command not in ('/status','/trangthai','/predict','/collect'):return False
        states=self.db.states(self.settings.stale_seconds,now)
        if len(text)>1: states=[b for b in states if b['id']==text[1]]
        if command=='/collect':states=[b for b in states if b['usable'] and b['fill_pct']>=b['full_on_pct']]
        lines=[]
        for b in states[:30]:
            label='MÔ PHỎNG' if b['source']=='simulated' else 'THIẾT BỊ'
            value=f'{b["fill_pct"]:.1f}%' if b['fill_pct'] is not None else 'chưa biết'
            if command=='/predict':
                p=b['prediction'];value=f'DỰ ĐOÁN {p.get("fill_pct","chưa có")}% / {p.get("method","unavailable")}' if p.get('valid_until',0)>=now else 'dự đoán chưa có/hết hiệu lực'
            lines.append(f'[{label}] {b["id"]}: {value}; {"dữ liệu hợp lệ" if b["usable"] else "dữ liệu cũ/lỗi/offline"}')
        with self.db.connect() as c:
            self.db.enqueue(c,f'update:{update["update_id"]}','\n'.join(lines) or 'Không tìm thấy thùng phù hợp.',now,chat)
        return True

    def poll(self):
        if self.settings.telegram_dry_run:return
        if time.time()<self.poll_after:return
        with self.db.connect() as c:
            value=c.execute("SELECT value FROM kv WHERE key='telegram_offset'").fetchone()
        offset=int(value[0]) if value else 0
        ok,data,delay=self.request('getUpdates',{'offset':offset,'timeout':0,'limit':20,'allowed_updates':['message']})
        if not ok:self.poll_after=time.time()+delay
        if ok:
            for update in data.get('result',[]):
                self.process_update(update)
                with self.db.connect() as c:
                    c.execute("INSERT OR REPLACE INTO kv VALUES('telegram_offset',?)",(str(update['update_id']+1),))
