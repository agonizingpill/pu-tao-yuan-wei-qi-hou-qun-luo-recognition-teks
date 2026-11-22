from datetime import timedelta

from fastapi import HTTPException

from .db import event
from .domain import MINUTES, Profile, RoundState
from .fieldbook import one

ROUND_VIEW = '''
    SELECT r.*,b.code AS block_code,b.name AS block_name,l.profile,l.revision,
           a.profile AS active_profile, a.revision AS active_revision,
           p.profile AS proposed_profile, p.run_id AS pending_run_id,
           coalesce(p.profile<>l.profile AND r.state='scheduled', false) AS review_hold
    FROM irrigation_round r JOIN vine_block b ON r.block_id=b.id
    JOIN climate_label l ON r.label_id=l.id
    LEFT JOIN climate_label a ON a.block_id=b.id AND a.state='active'
    LEFT JOIN climate_label p ON p.block_id=b.id AND p.state='proposed'
'''


def rounds(db):
    return db.execute(ROUND_VIEW + ' ORDER BY r.starts_at,r.code').fetchall()


def existing_round(db, round_id):
    return one(db, ROUND_VIEW + ' WHERE r.id=%s', (round_id,), '灌溉轮次')


def scheduling_basis(db, block_id):
    block = one(db, '''
        SELECT b.code,l.id AS label_id,l.profile,p.profile AS proposed_profile
        FROM vine_block b LEFT JOIN climate_label l ON b.id=l.block_id AND l.state='active'
        LEFT JOIN climate_label p ON p.block_id=b.id AND p.state='proposed' WHERE b.id=%s
    ''', (block_id,), '地块')
    if block['proposed_profile'] and block['proposed_profile'] != block['profile']:
        raise HTTPException(409, '新标签需要主管确认，暂缓编排该地块')
    if not block['label_id']:
        raise HTTPException(409, '请先为该地块生成生效群落标签')
    return block


def require_free_slot(db, block_id, begins, minutes, excluding=0):
    ends = begins + timedelta(minutes=minutes)
    if db.execute('''
        SELECT 1 FROM irrigation_round
        WHERE block_id=%s AND id<>%s AND state<>'cancelled'
          AND starts_at < %s AND starts_at + minutes * interval '1 minute' > %s
    ''', (block_id, excluding, ends, begins)).fetchone():
        raise HTTPException(409, '同一地块的灌溉时段重叠')


def schedule(db, data, actor):
    basis = scheduling_basis(db, data.block_id)
    minutes = MINUTES[Profile(basis['profile'])]
    require_free_slot(db, data.block_id, data.starts_at, minutes)
    row = db.execute('''
        INSERT INTO irrigation_round(code,block_id,original_label_id,label_id,starts_at,minutes,state)
        VALUES (%s,%s,%s,%s,%s,%s,'scheduled') RETURNING id
    ''', (data.code, data.block_id, basis['label_id'], basis['label_id'], data.starts_at, minutes)).fetchone()
    event(db, actor, 'irrigation_scheduled', data.code, label_id=basis['label_id'], minutes=minutes,
          starts_at=data.starts_at.isoformat())
    return existing_round(db, row['id'])


def replan(db, round_id, data, actor):
    row = existing_round(db, round_id)
    if row['state'] != RoundState.NEEDS_REPLAN:
        raise HTTPException(409, '只有确认受影响的轮次可重新排灌')
    basis = scheduling_basis(db, row['block_id'])
    minutes = MINUTES[Profile(basis['profile'])]
    require_free_slot(db, row['block_id'], data.starts_at, minutes, round_id)
    db.execute('''
        UPDATE irrigation_round SET label_id=%s, starts_at=%s,minutes=%s,state='scheduled' WHERE id=%s
    ''', (basis['label_id'], data.starts_at, minutes, round_id))
    event(db, actor, 'irrigation_replanned', row['code'], reason=data.reason,
          previous_label_id=row['label_id'], previous_minutes=row['minutes'], previous_start=row['starts_at'].isoformat(),
          label_id=basis['label_id'], minutes=minutes, starts_at=data.starts_at.isoformat())
    return existing_round(db, round_id)


def finish(db, round_id, completed_at, actor):
    row = existing_round(db, round_id)
    if row['state'] != RoundState.SCHEDULED or row['review_hold']:
        raise HTTPException(409, '轮次须处于可执行的已排状态，待确认或改排轮次不能登记完灌')
    if completed_at < row['starts_at'] + timedelta(minutes=row['minutes']):
        raise HTTPException(409, '完灌时间早于排定结束时间')
    db.execute("UPDATE irrigation_round SET state='completed',completed_at=%s WHERE id=%s",
               (completed_at, round_id))
    event(db, actor, 'irrigation_completed', row['code'], completed_at=completed_at.isoformat())
    return existing_round(db, round_id)


def cancel(db, round_id, reason, actor):
    row = existing_round(db, round_id)
    if row['state'] not in (RoundState.SCHEDULED, RoundState.NEEDS_REPLAN):
        raise HTTPException(409, '该轮次已完灌或已取消')
    db.execute("UPDATE irrigation_round SET state='cancelled' WHERE id=%s", (round_id,))
    event(db, actor, 'irrigation_cancelled', row['code'], reason=reason)
    return existing_round(db, round_id)


def observe(db, data, actor):
    basis = existing_round(db, data.round_id)
    if basis['state'] != RoundState.COMPLETED or data.observed_at < basis['completed_at']:
        raise HTTPException(409, '采收观察需要关联已完灌轮次，且观察时间不能早于完灌')
    row = db.execute('''
        INSERT INTO harvest_note(round_id,observed_at,brix,berry_count,note,actor)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
    ''', (data.round_id, data.observed_at, data.brix, data.berry_count, data.note, actor)).fetchone()
    event(db, actor, 'harvest_observed', basis['code'], note_id=row['id'], label_id=basis['label_id'])
    return row


def observations(db):
    return db.execute('''
        SELECT h.*,r.code AS round_code,r.completed_at,b.code AS block_code,b.name AS block_name,
               l.profile,l.revision
        FROM harvest_note h JOIN irrigation_round r ON h.round_id=r.id
        JOIN vine_block b ON r.block_id=b.id JOIN climate_label l ON r.label_id=l.id
        ORDER BY h.observed_at DESC,h.id DESC
    ''').fetchall()
