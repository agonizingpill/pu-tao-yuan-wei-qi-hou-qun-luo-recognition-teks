import logging
import time
from pathlib import Path

from .clusters import store_fit
from .db import EVIDENCE_DIR, QUEUE, connect, event, lock_ledger, redis_client
from .mixture import fit_profiles

logger = logging.getLogger('vineyard.worker')


def consume_one():
    with connect() as db:
        lock_ledger(db)
        run = db.execute("SELECT id,snapshot,digest FROM climate_run WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
        if not run:
            return
        run_id = run['id']
        try:
            result = fit_profiles(run['snapshot'])
        except Exception as exc:
            logger.exception('Fit failed for run %s', run_id)
            reason = str(exc) if isinstance(exc, ValueError) else '混合模型计算失败，可按原快照重试。'
            db.execute("UPDATE climate_run SET status='failed',error=%s,attempts=attempts+1 WHERE id=%s",
                       (reason, run_id))
            event(db, 'worker', 'fit_failed', run_id, digest=run['digest'], reason=reason)
            return
        store_fit(db, run_id, result)
    # PostgreSQL remains authoritative if archiving fails after the transaction commits.
    try:
        with connect() as db:
            row = db.execute('''
                SELECT jsonb_build_object('id',id,'window_end',window_end,'digest',digest,
                    'snapshot',snapshot,'result',result)::text AS payload
                FROM climate_run WHERE id=%s
            ''', (run_id,)).fetchone()
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = EVIDENCE_DIR / f'run-{run_id}.tmp'
        tmp.write_text(row['payload'], encoding='utf-8')
        tmp.replace(EVIDENCE_DIR / f'run-{run_id}.json')
    except Exception:
        logger.exception('Could not archive run %s', run_id)
    logger.info('Committed climate run %s (%s components)', run_id, result['chosen_k'])


def main():
    logging.basicConfig(level=logging.INFO)
    client = redis_client()
    heartbeat = Path('/tmp/field-heartbeat')
    while True:
        try:
            client.blpop(QUEUE, timeout=2)
            # The persisted status recovers work even if a notification or worker is lost.
            consume_one()
            heartbeat.touch()
        except Exception:
            logger.exception('Worker iteration failed')
            time.sleep(2)


if __name__ == '__main__':
    main()
