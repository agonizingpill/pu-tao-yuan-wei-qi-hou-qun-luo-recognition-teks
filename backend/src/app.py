import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

import os
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from psycopg.errors import UniqueViolation
from redis.exceptions import RedisError

from backend.scripts.seed_demo import seed
from .operations_evidence import router as operations_evidence
from . import clusters, fieldbook, irrigation, schemas
from .auth import check_password, identity, issue, require
from .db import EVIDENCE_DIR, QUEUE, connect, lock_ledger, migrate, redis_client
from .domain import Role

logger = logging.getLogger('uvicorn.error')
editable = Depends(require(Role.OPERATOR, Role.SUPERVISOR))
supervised = Depends(require(Role.SUPERVISOR))
readable = Depends(identity)


@asynccontextmanager
async def lifespan(_app):
    migrate()
    if os.getenv('SEED_DEMO', 'true').lower() == 'true':
        try:
            seed()
        except Exception:
            logger.exception('Demo data could not be seeded')
    yield


app = FastAPI(title='坡畦勘测册 · 葡萄园微气候', lifespan=lifespan)
app.include_router(operations_evidence)


@app.middleware('http')
async def identify_request(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Request-ID'] = uuid4().hex
    return response


@app.middleware('http')
async def time_request(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    response.headers['Server-Timing'] = f'app;dur={(perf_counter()-started)*1000:.1f}'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(UniqueViolation)
async def duplicate(_request, exc):
    messages = {'vine_block_code_key': '地块编号已登记', 'vine_block_sensor_key': '探头已绑定另一地块',
                'microclimate_sample_block_id_observed_day_slot_key': '该地块的班次采样已封存',
                'irrigation_round_code_key': '灌溉轮次编号已使用', 'harvest_note_round_id_key': '该轮次已有采收观察'}
    return JSONResponse(status_code=409, content={'detail': messages.get(exc.diag.constraint_name, '记录已存在')})


@app.get('/health')
def health():
    with connect() as db:
        db.execute('SELECT 1 FROM vine_block LIMIT 1')
    redis_client().ping()
    return {'status': 'ready'}


@app.post('/login')
def login(data: schemas.Credentials):
    with connect() as db:
        row = db.execute('SELECT * FROM account WHERE username=%s', (data.username,)).fetchone()
    if row is None or not check_password(data.password, row['password_hash']):
        raise HTTPException(401, '账号或密码不正确')
    return {'token': issue(row), 'name': row['username'], 'role': row['role']}


@app.get('/me')
def me(user=readable):
    return user


@app.get('/blocks')
def blocks(_user=readable):
    with connect() as db:
        return fieldbook.block_list(db)


@app.post('/blocks', status_code=201)
def new_block(data: schemas.BlockInput, user=editable):
    with connect() as db:
        lock_ledger(db)
        return fieldbook.register(db, data.model_dump(), user['name'])


@app.get('/blocks/{block_id}/samples')
def samples(block_id: int, _user=readable):
    with connect() as db:
        return fieldbook.sample_list(db, block_id)


@app.post('/samples', status_code=201)
def add_sample(data: schemas.SampleInput, user=editable):
    with connect() as db:
        lock_ledger(db)
        return fieldbook.record_sample(db, data.model_dump(), user['name'])


@app.get('/labels')
def labels(_user=readable):
    with connect() as db:
        return db.execute('''
            SELECT l.*,b.code,r.window_end FROM climate_label l
            JOIN vine_block b ON b.id=l.block_id JOIN climate_run r ON r.id=l.run_id
            ORDER BY b.code,l.revision DESC
        ''').fetchall()


@app.get('/runs')
def runs(_user=readable):
    with connect() as db:
        return db.execute('''
            SELECT id,window_end,status,created_at,attempts,actor FROM climate_run ORDER BY id DESC LIMIT 60
        ''').fetchall()


@app.get('/runs/{run_id}')
def run_detail(run_id: int, _user=readable):
    with connect() as db:
        return clusters.run_detail(db, run_id)


@app.get('/runs/{run_id}/evidence')
def run_evidence(run_id: int, _user=readable):
    artifact = EVIDENCE_DIR / f'run-{run_id}.json'
    if artifact.is_file():
        return FileResponse(artifact, media_type='application/json', filename=artifact.name)
    with connect() as db:
        return fieldbook.one(db, '''
            SELECT id,window_end,digest,snapshot,result FROM climate_run WHERE id=%s
        ''', (run_id,), '识别批次')


def notify(run):
    if run['status'] == 'queued':
        try:
            redis_client().rpush(QUEUE, str(run['id']))
        except RedisError:
            logger.exception('Redis notification failed; run %s is persisted', run['id'])
    return run


@app.post('/runs', status_code=202)
def create_run(data: schemas.RunInput, user=editable):
    with connect() as db:
        lock_ledger(db)
        run = clusters.submit(db, data.window_end, user['name'])
    return notify(run)


@app.post('/runs/{run_id}/decision')
def decide(run_id: int, data: schemas.DecisionInput, user=supervised):
    with connect() as db:
        lock_ledger(db)
        return clusters.decide(db, run_id, data.approve, data.reason, user['name'])


@app.post('/runs/{run_id}/retry', status_code=202)
def retry(run_id: int, user=editable):
    with connect() as db:
        lock_ledger(db)
        run = clusters.retry(db, run_id, user['name'])
    return notify(run)


@app.get('/rounds')
def rounds(_user=readable):
    with connect() as db:
        return irrigation.rounds(db)


@app.post('/rounds', status_code=201)
def schedule(data: schemas.ScheduleInput, user=editable):
    with connect() as db:
        lock_ledger(db)
        return irrigation.schedule(db, data, user['name'])


@app.post('/rounds/{round_id}/replan')
def replan(round_id: int, data: schemas.ReplanInput, user=editable):
    with connect() as db:
        lock_ledger(db)
        return irrigation.replan(db, round_id, data, user['name'])


@app.post('/rounds/{round_id}/complete')
def complete(round_id: int, data: schemas.CompletionInput, user=editable):
    with connect() as db:
        lock_ledger(db)
        return irrigation.finish(db, round_id, data.completed_at, user['name'])


@app.post('/rounds/{round_id}/cancel')
def cancel(round_id: int, data: schemas.ReasonInput, user=supervised):
    with connect() as db:
        lock_ledger(db)
        return irrigation.cancel(db, round_id, data.reason, user['name'])


@app.get('/harvest')
def harvest(_user=readable):
    with connect() as db:
        return irrigation.observations(db)


@app.post('/harvest', status_code=201)
def observe(data: schemas.HarvestInput, user=editable):
    with connect() as db:
        lock_ledger(db)
        return irrigation.observe(db, data, user['name'])


@app.get('/audit')
def audit(_user=supervised):
    with connect() as db:
        return db.execute('SELECT * FROM field_event ORDER BY id DESC LIMIT 100').fetchall()
