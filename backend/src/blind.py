"""Two-versus-three group blind tests against a later published window.

A blind test freezes both sampling windows when it is created. The earlier window fits
the scaler and both mixtures; the later window is only transformed and labelled with
those frozen models. Nothing here publishes labels or touches irrigation scheduling.
"""

from datetime import timedelta

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .db import event
from .fieldbook import one
from .mixture import blind_compare


def _run(db, run_id):
    return one(db, '''
        SELECT id,window_end,status,snapshot,digest,coverage
        FROM climate_run WHERE id=%s
    ''', (run_id,), '识别批次')


def _sources(snapshot):
    return sorted({reading['source'] for item in snapshot for reading in item.get('readings') or []
                   if reading.get('source')})


def _window(run):
    start = run['window_end'] - timedelta(days=2)
    return {
        'run_id': run['id'],
        'window_start': start.isoformat(),
        'window_end': run['window_end'].isoformat(),
        'digest': run['digest'],
        'sources': _sources(run['snapshot']),
        'blocks': len(run['snapshot']),
    }


def list_tests(db):
    return db.execute('''
        SELECT t.id,t.train_run_id,t.test_run_id,t.status,t.error,t.attempts,t.actor,t.created_at,
               train.window_end AS train_window_end,
               test.window_end AS test_window_end,
               t.result->'summary'->>'eligible' AS eligible,
               t.result->'summary'->>'hit_2' AS hit_2,
               t.result->'summary'->>'hit_3' AS hit_3
        FROM climate_blind_test t
        JOIN climate_run train ON train.id=t.train_run_id
        JOIN climate_run test ON test.id=t.test_run_id
        ORDER BY t.id DESC LIMIT 60
    ''').fetchall()


def detail(db, test_id):
    row = one(db, '''
        SELECT id,train_run_id,test_run_id,status,error,attempts,actor,created_at,provenance,published,result,digests
        FROM climate_blind_test WHERE id=%s
    ''', (test_id,), '盲测批次')
    row['train_window_end'] = row['provenance']['train']['window_end']
    row['test_window_end'] = row['provenance']['test']['window_end']
    return row


def create(db, train_run_id, test_run_id, actor):
    if train_run_id == test_run_id:
        raise HTTPException(409, '训练窗口与盲测窗口不能是同一批次')
    train = _run(db, train_run_id)
    test = _run(db, test_run_id)
    if train['status'] != 'effective':
        raise HTTPException(409, '训练窗口必须是已生效的识别批次')
    if test['status'] != 'effective':
        raise HTTPException(409, '盲测窗口必须是已生效的识别批次')
    if test['window_end'] <= train['window_end']:
        raise HTTPException(409, '盲测窗口须晚于训练窗口')
    if test['window_end'] - timedelta(days=2) <= train['window_end']:
        raise HTTPException(409, '两个采样窗口重叠，请选用不重叠的窗口')
    existing = db.execute('''
        SELECT id FROM climate_blind_test WHERE train_run_id=%s AND test_run_id=%s
    ''', (train_run_id, test_run_id)).fetchone()
    if existing:
        return detail(db, existing['id'])
    labels = db.execute('''
        SELECT block_id,profile,revision FROM climate_label
        WHERE run_id=%s AND state IN ('active','superseded') ORDER BY block_id
    ''', (test_run_id,)).fetchall()
    published = {str(row['block_id']): {'profile': row['profile'], 'revision': row['revision']}
                 for row in labels}
    names = {str(row['id']): row['name'] for row in db.execute('SELECT id,name FROM vine_block')}
    provenance = {'train': _window(train), 'test': _window(test), 'block_names': names}
    row = db.execute('''
        INSERT INTO climate_blind_test(train_run_id,test_run_id,status,train_snapshot,test_snapshot,
            coverage,published,provenance,digests,actor)
        VALUES (%s,%s,'queued',%s,%s,%s,%s,%s,%s,%s) RETURNING id
    ''', (train_run_id, test_run_id, Jsonb(train['snapshot']), Jsonb(test['snapshot']),
          Jsonb(test['coverage']), Jsonb(published), Jsonb(provenance),
          Jsonb({'train': train['digest'], 'test': test['digest']}), actor)).fetchone()['id']
    event(db, actor, 'blind_test_queued', row, train_run_id=train_run_id, test_run_id=test_run_id,
          train_digest=train['digest'], test_digest=test['digest'])
    return detail(db, row)


def retry(db, test_id, actor):
    row = one(db, 'SELECT id,status,train_run_id,test_run_id FROM climate_blind_test WHERE id=%s',
              (test_id,), '盲测批次')
    if row['status'] != 'failed':
        raise HTTPException(409, '只有失败的盲测可以按原快照重试')
    db.execute("UPDATE climate_blind_test SET status='queued',error=NULL WHERE id=%s", (test_id,))
    event(db, actor, 'blind_test_retried', test_id, train_run_id=row['train_run_id'],
          test_run_id=row['test_run_id'])
    return detail(db, test_id)


def claim(db):
    """Take the oldest queued blind test, skipping rows another worker is fitting."""
    return db.execute('''
        SELECT id,train_snapshot,test_snapshot,coverage,published,provenance
        FROM climate_blind_test WHERE status='queued'
        ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
    ''').fetchone()


def store(db, test_id, row):
    provenance = row['provenance']
    published = [{'block_id': int(block_id), 'profile': entry['profile']}
                 for block_id, entry in row['published'].items()]
    result = blind_compare(row['train_snapshot'], row['test_snapshot'], published, row['coverage'],
                           provenance.get('block_names'))
    result['provenance'] = provenance
    result['train_run_id'] = provenance['train']['run_id']
    result['test_run_id'] = provenance['test']['run_id']
    db.execute('''
        UPDATE climate_blind_test SET status='completed',result=%s,error=NULL,attempts=attempts+1
        WHERE id=%s
    ''', (Jsonb(result), test_id))
    event(db, 'worker', 'blind_test_completed', test_id,
          eligible=result['summary']['eligible'], hit_2=result['summary']['hit_2'],
          hit_3=result['summary']['hit_3'])
    return result


def fail(db, test_id, reason):
    db.execute('''
        UPDATE climate_blind_test SET status='failed',error=%s,attempts=attempts+1 WHERE id=%s
    ''', (reason, test_id))
    event(db, 'worker', 'blind_test_failed', test_id, reason=reason)


def window_options(db):
    """Distinct effective windows a blind test can draw from, oldest first."""
    return db.execute('''
        SELECT DISTINCT ON (window_end) id,window_end,(window_end - 2) AS window_start,digest
        FROM climate_run WHERE status='effective'
        ORDER BY window_end,id DESC
    ''').fetchall()
