import hashlib
import json
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import login, session_user
from .config import Settings
from .db import Database
from .ml import Predictor, update_predictions
from .mqtt import Ingestor
from .routing import RouteRequest, solve
from .runtime import SingleWorker
from .schema import Message, parse_message
from .lab import LabService
from .telegram import TelegramWorker

ROOT=Path(__file__).resolve().parent.parent


class LoginBody(BaseModel):
    username:str=Field(min_length=1,max_length=64)
    password:str=Field(min_length=1,max_length=256)


class LabNotifications(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled:bool=Field(strict=True)
    after_seq:int=Field(strict=True,ge=0,le=4294967295)


class LabConnection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    seq:int=Field(strict=True,ge=1,le=9007199254740991)
    action:Literal['heartbeat','stop']='heartbeat'


class BinBody(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    name:str=Field(min_length=1,max_length=80)
    lat:float=Field(ge=-90,le=90)
    lon:float=Field(ge=-180,le=180)
    capacity_l:float=Field(gt=0,le=100000)
    source:str=Field(pattern=r'^(real|simulated)$')


def create_app(settings=None,background=True):
    cfg=settings or Settings();cfg.validate();db=Database(cfg.db)
    stop=threading.Event();worker_lock=SingleWorker(cfg.db);ingestor=None
    lab=LabService(db,cfg)
    login_attempts=defaultdict(deque);route_times=defaultdict(float);route_mutex=threading.Lock()
    health={'connection_monitor':'stopped','worker':'stopped','mqtt':'disabled','prediction_error':False}

    @asynccontextmanager
    async def lifespan(app):
        nonlocal ingestor
        worker_lock.acquire();stop.clear();thread=None;network_thread=None
        telegram=TelegramWorker(db,cfg)
        if cfg.mqtt_enabled:
            ingestor=Ingestor(db,cfg);ingestor.start()
        def work():
            predictor=Predictor(cfg.model);last_prediction=0;last_poll=0
            while not stop.is_set():
                now=time.time()
                try:
                    telegram.deliver(now,stop)
                    if not stop.is_set() and now-last_poll>=10:telegram.poll();last_poll=now
                    if not stop.is_set() and now-last_prediction>=30:
                        try:update_predictions(db,predictor,cfg);health['prediction_error']=False
                        except Exception:health['prediction_error']=True
                        last_prediction=now
                    health['worker']='running'
                except Exception:
                    health['worker']='degraded'
                    logging.getLogger(__name__).warning('Worker lỗi; không log credential hoặc payload')
                stop.wait(1)
        def monitor():
            while not stop.is_set():
                try:
                    lab.check_connections();health['connection_monitor']='running'
                except Exception:
                    health['connection_monitor']='degraded'
                    logging.getLogger(__name__).warning('Giám sát kết nối lab gặp lỗi; không log payload')
                stop.wait(1)
        try:
            lab.reset_connection_monitors()
            if background:
                network_thread=threading.Thread(target=monitor,daemon=True);network_thread.start()
                thread=threading.Thread(target=work,daemon=True);thread.start()
            yield
        finally:
            stop.set()
            if thread:thread.join(timeout=35)
            if network_thread:network_thread.join(timeout=11)
            if ingestor:ingestor.stop()
            if (thread and thread.is_alive()) or (network_thread and network_thread.is_alive()):
                # Keep ownership until process termination if a transport is still blocked.
                # Do not race a second worker or close a client in active use.
                health['worker']='stopping'
            else:
                telegram.close();worker_lock.release();health['worker']='stopped';health['connection_monitor']='stopped'

    app=FastAPI(title='Thùng rác thông minh',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.db=db;app.state.settings=cfg;app.state.lab=lab
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','[::1]','testserver'])

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,error):
        # Avoid echoing password/credential input through default validation errors.
        return JSONResponse({'detail':'Dữ liệu yêu cầu không hợp lệ'},status_code=422)

    @app.middleware('http')
    async def constraints(request,call_next):
        if request.method in ('POST','PUT','PATCH','DELETE'):
            origin=request.headers.get('origin')
            if origin and (urlsplit(origin).netloc!=request.url.netloc or urlsplit(origin).scheme!=request.url.scheme):
                return JSONResponse({'detail':'Nguồn yêu cầu không được phép'},status_code=403)
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>4096:return JSONResponse({'detail':'Yêu cầu quá lớn'},status_code=413)
                chunks.append(chunk)
            request._body=b''.join(chunks)
        result=await call_next(request)
        result.headers['X-Content-Type-Options']='nosniff'
        result.headers['Referrer-Policy']='same-origin'
        result.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        if request.url.path.startswith('/api/'):result.headers['Cache-Control']='no-store'
        return result

    def viewer(request:Request):
        u=session_user(db,request.cookies.get('session'))
        if not u:raise HTTPException(401,'Vui lòng đăng nhập')
        return u

    def manager(u=Depends(viewer)):
        if u['role']!='manager':raise HTTPException(403,'Cần quyền quản lý')
        return u

    @app.get('/health')
    def status():return {'status':'ok','service':'smartbin'}

    @app.post('/api/login')
    def signin(body:LoginBody,request:Request,response:Response):
        ip=request.client.host if request.client else 'local';q=login_attempts[ip];now=time.monotonic()
        while q and q[0]<now-60:q.popleft()
        if len(q)>=10:raise HTTPException(429,'Thử lại sau một phút')
        q.append(now);token=login(db,body.username,body.password,cfg.session_seconds)
        if not token:raise HTTPException(401,'Sai tài khoản hoặc mật khẩu')
        response.set_cookie('session',token,httponly=True,secure=cfg.secure_cookie,samesite='strict',max_age=cfg.session_seconds,path='/')
        return session_user(db,token)

    @app.post('/api/logout')
    def signout(request:Request,response:Response,u=Depends(viewer)):
        lab.close_owner(u['username'])
        with db.connect() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(request.cookies['session'].encode()).hexdigest(),))
        response.delete_cookie('session');return {'ok':True}

    @app.get('/api/me')
    def me(u=Depends(viewer)):return u

    @app.get('/api/health')
    def private_health(u=Depends(viewer)):
        return dict(health,mqtt='connected' if ingestor and ingestor.connected else 'offline' if ingestor else 'disabled',
                    telegram='dry_run' if cfg.telegram_dry_run else 'enabled')

    @app.get('/api/bins')
    def bins(u=Depends(viewer)):return db.states(cfg.stale_seconds)

    @app.post('/api/bins')
    def register(body:BinBody,u=Depends(manager)):
        try:db.register(body.id,body.name,body.lat,body.lon,body.capacity_l,body.source)
        except ValueError as e:raise HTTPException(409,str(e)) from None
        return {'ok':True}

    @app.get('/api/bins/{bin_id}/history')
    def history(bin_id:str,start:float=0,end:float=1e20,limit:int=500,u=Depends(viewer)):
        if start>end or not 1<=limit<=5000:raise HTTPException(422,'Khoảng thời gian/giới hạn không hợp lệ')
        return db.history(bin_id,start,end,limit)

    @app.get('/api/bins/{bin_id}/events')
    def events(bin_id:str,u=Depends(viewer)):
        with db.connect() as c:
            return [dict(r) for r in c.execute('SELECT e.type,t.measured_at,t.received_at,t.source,t.boot_id,t.seq FROM events e JOIN telemetry t ON t.id=e.telemetry_id WHERE t.bin_id=? ORDER BY t.id DESC LIMIT 200',(bin_id,))]

    @app.post('/api/demo/ingest')
    async def demo_ingest(request:Request,u=Depends(manager)):
        try:
            m=parse_message(await request.body(),cfg.max_payload)
            if m.source!='simulated':raise ValueError('Endpoint demo chỉ nhận nguồn simulated; thiết bị thật dùng MQTT TLS')
            if m.bin_id.startswith('lab-'):raise ValueError('Thùng lab phải dùng API phiên riêng')
            return db.ingest(m)
        except (ValueError,TypeError) as e:raise HTTPException(422,'Bản tin không hợp lệ hoặc thùng chưa đăng ký') from None

    @app.post('/api/lab/sessions')
    def lab_start(u=Depends(manager)):
        try:
            return lab.start(u['username'])
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.post('/api/lab/sessions/{session_id}/messages')
    def lab_message(session_id: str, body: Message, u=Depends(manager)):
        try:
            return lab.ingest(u['username'], session_id, body)
        except PermissionError as e:
            raise HTTPException(403, str(e)) from None
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

    @app.post('/api/lab/sessions/{session_id}/notifications')
    def lab_notifications(session_id: str, body: LabNotifications, u=Depends(manager)):
        try:
            return lab.set_notifications(u['username'], session_id, body.enabled, body.after_seq)
        except PermissionError as e:
            raise HTTPException(403, str(e)) from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.post('/api/lab/sessions/{session_id}/connection')
    def lab_connection(session_id: str, body: LabConnection, u=Depends(manager)):
        try:
            return lab.connection(u['username'], session_id, body.seq, body.action)
        except PermissionError as e:
            raise HTTPException(403, str(e)) from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.post('/api/routes')
    def route(body:RouteRequest,u=Depends(manager)):
        if time.monotonic()-route_times[u['username']]<5:raise HTTPException(429,'Chờ 5 giây giữa hai lần lập tuyến')
        if not route_mutex.acquire(False):raise HTTPException(409,'Đang lập một tuyến khác')
        try:
            route_times[u['username']]=time.monotonic()
            return solve(db.states(cfg.stale_seconds),body)
        except ValueError as e:raise HTTPException(422,str(e)) from None
        finally:route_mutex.release()

    @app.get('/api/export')
    def export(bin_id:str,start:float=0,end:float=1e20,u=Depends(manager)):
        records=db.history(bin_id,start,end,5000)
        return Response(''.join(json.dumps({'message':{k:v for k,v in m.items() if k not in ('received_at','measured_at')},'received_at':m['received_at']},ensure_ascii=False)+'\n' for m in records),media_type='application/x-ndjson',headers={'Content-Disposition':'attachment; filename="observations.jsonl"'})

    app.mount('/static',StaticFiles(directory=ROOT/'dashboard'),name='static')
    @app.get('/')
    def dashboard():return FileResponse(ROOT/'dashboard/index.html')
    return app


app=create_app()
