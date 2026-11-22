import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from redis import Redis

QUEUE = 'vineyard:identify'
EVIDENCE_DIR = Path(os.getenv('EVIDENCE_DIR', '/evidence'))


def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, connect_timeout=3)


def redis_client():
    return Redis.from_url(os.environ['REDIS_URL'], socket_timeout=5, socket_connect_timeout=3)


def migrate():
    migrations = Path(__file__).resolve().parents[1] / 'migrations'
    with connect() as db:
        lock_ledger(db)
        for path in sorted(migrations.glob('*.sql')):
            db.execute(path.read_text())


def lock_ledger(db):
    # Serialize schedule, label publication, and sample snapshot changes for this orchard.
    db.execute('SELECT pg_advisory_xact_lock(1071)')


def event(db, actor, name, subject, **details):
    db.execute('INSERT INTO field_event(actor,event,subject,details) VALUES (%s,%s,%s,%s)',
               (actor, name, str(subject), Jsonb(details)))
