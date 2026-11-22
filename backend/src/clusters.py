import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .db import event
from .domain import Slot
from .fieldbook import one

RUN_FIELDS = 'id,window_end,status,digest,coverage,result,error,attempts,actor,created_at'


def run_detail(db, run_id):
    run = one(db, f'SELECT {RUN_FIELDS} FROM climate_run WHERE id=%s', (run_id,), '识别批次')
    run['affected'] = affected_rounds(db, run_id) if run['status'] == 'review' else []
    return run


def make_snapshot(db, end):
    start = end - timedelta(days=2)
    blocks = db.execute('SELECT id,code,sensor FROM vine_block ORDER BY code').fetchall()
    samples = db.execute('''
        SELECT id,block_id,observed_day,slot,temp_c,rh_pct,source
        FROM microclimate_sample WHERE observed_day BETWEEN %s AND %s ORDER BY observed_day,slot,id
    ''', (start, end)).fetchall()
    snapshot, coverage = [], []
    expected = {(start + timedelta(days=i), slot.value) for i in range(3) for slot in Slot}
    for block in blocks:
        readings = [row for row in samples if row['block_id'] == block['id']]
        missing = sorted(expected - {(row['observed_day'], row['slot']) for row in readings})
        snapshot.append(dict(block_id=block['id'], code=block['code'], sensor=block['sensor'],
                             readings=[dict(row, observed_day=row['observed_day'].isoformat()) for row in readings]))
        coverage.append(dict(code=block['code'], block_id=block['id'], sensor=block['sensor'],
                             received=len(readings), expected=len(expected),
                             missing=[{'day': day.isoformat(), 'slot': slot} for day, slot in missing],
                             deficient=len(missing) >= 2))
    return snapshot, coverage


def submit(db, end, actor):
    if db.execute("SELECT 1 FROM climate_run WHERE status IN ('queued','review')").fetchone():
        raise HTTPException(409, '请先处理当前识别批次')
    latest = db.execute("SELECT max(window_end) AS day FROM climate_run WHERE status='effective'").fetchone()['day']
    if latest is not None and end < latest:
        raise HTTPException(409, '窗口早于当前生效标签的采样窗口')
    snapshot, coverage = make_snapshot(db, end)
    digest = hashlib.sha256(json.dumps({'window_end': end.isoformat(), 'blocks': snapshot},
                                       ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    prior = db.execute('''
        SELECT id FROM climate_run WHERE digest=%s AND status='effective' ORDER BY id DESC LIMIT 1
    ''', (digest,)).fetchone()
    if prior:
        return run_detail(db, prior['id'])
    reason = None
    if len(snapshot) < 6:
        reason = '至少需要 6 个地块才能识别群落。'
    deficient = [entry['code'] for entry in coverage if entry['deficient']]
    if deficient:
        reason = '缺测超过 25%，请补录后再次提交：' + '、'.join(deficient)
    state = 'blocked' if reason else 'queued'
    run_id = db.execute('''
        INSERT INTO climate_run(window_end,status,snapshot,digest,coverage,error,actor)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
    ''', (end, state, Jsonb(snapshot), digest, Jsonb(coverage), reason, actor)).fetchone()['id']
    event(db, actor, 'cluster_blocked' if reason else 'snapshot_queued', run_id,
          digest=digest, reason=reason, deficient=deficient)
    return run_detail(db, run_id)


def affected_rounds(db, run_id):
    return db.execute('''
        SELECT r.id,r.code,b.code AS block,p.profile AS proposed_profile,a.profile AS basis_profile,r.starts_at
        FROM irrigation_round r JOIN vine_block b ON b.id=r.block_id
        JOIN climate_label p ON p.block_id=r.block_id AND p.run_id=%s AND p.state='proposed'
        JOIN climate_label a ON a.id=r.label_id
        WHERE r.state='scheduled' AND a.profile<>p.profile
        ORDER BY r.starts_at,r.code
    ''', (run_id,)).fetchall()


def publish(db, run_id, actor, reason, affected):
    db.execute('''
        UPDATE climate_label current SET state='superseded'
        FROM climate_label proposed
        WHERE current.state='active' AND proposed.run_id=%s AND proposed.state='proposed'
          AND proposed.block_id=current.block_id
    ''', (run_id,))
    db.execute("UPDATE climate_label SET state='active' WHERE run_id=%s AND state='proposed'", (run_id,))
    if affected:
        db.execute("UPDATE irrigation_round SET state='needs_replan' WHERE id=ANY(%s)",
                   ([item['id'] for item in affected],))
    db.execute("UPDATE climate_run SET status='effective' WHERE id=%s", (run_id,))
    event(db, actor, 'labels_published', run_id, reason=reason, impact=[item['code'] for item in affected])


def store_fit(db, run_id, result):
    for item in result['assignments']:
        block_id = item['block_id']
        db.execute('''
            INSERT INTO climate_label(block_id,run_id,revision,profile,confidence,state)
            SELECT %s,%s,COALESCE(max(revision),0)+1,%s,%s,'proposed'
            FROM climate_label WHERE block_id=%s
        ''', (block_id, run_id, item['profile'], item['confidence'], block_id))
    impacted = affected_rounds(db, run_id)
    db.execute('UPDATE climate_run SET status=%s,result=%s,error=NULL,attempts=attempts+1 WHERE id=%s',
               ('review' if impacted else 'queued', Jsonb(result), run_id))
    if impacted:
        event(db, 'worker', 'review_required', run_id, rounds=[item['code'] for item in impacted])
    else:
        publish(db, run_id, 'worker', '没有已排轮次受到影响', [])


def decide(db, run_id, approve, reason, actor):
    run = run_detail(db, run_id)
    if run['status'] != 'review':
        raise HTTPException(409, '该识别批次不在主管确认阶段')
    if approve:
        publish(db, run_id, actor, reason, run['affected'])
    else:
        db.execute("UPDATE climate_label SET state='rejected' WHERE run_id=%s AND state='proposed'", (run_id,))
        db.execute("UPDATE climate_run SET status='rejected' WHERE id=%s", (run_id,))
        event(db, actor, 'labels_rejected', run_id, reason=reason)
    return run_detail(db, run_id)


def retry(db, run_id, actor):
    run = run_detail(db, run_id)
    newer = db.execute('SELECT 1 FROM climate_run WHERE id>%s LIMIT 1', (run_id,)).fetchone()
    if run['status'] != 'failed' or newer:
        raise HTTPException(409, '只有最新一笔失败的计算可以按原快照重试')
    db.execute("UPDATE climate_run SET status='queued',error=NULL WHERE id=%s", (run_id,))
    event(db, actor, 'snapshot_retried', run_id, digest=run['digest'])
    return run_detail(db, run_id)
