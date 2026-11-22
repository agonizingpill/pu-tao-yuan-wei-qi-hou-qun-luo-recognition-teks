from fastapi import HTTPException

from .db import event


def one(db, sql, params, what):
    row = db.execute(sql, params).fetchone()
    if row is None:
        raise HTTPException(404, f'{what}不存在')
    return row


def block_list(db):
    return db.execute('''
        SELECT b.*, l.profile, l.revision, l.confidence
        FROM vine_block b LEFT JOIN climate_label l ON l.block_id=b.id AND l.state='active'
        ORDER BY b.code
    ''').fetchall()


def register(db, data, actor):
    existing = db.execute('''
        SELECT code FROM vine_block
        WHERE int4range(east_m,east_m+width_m) && int4range(%(east_m)s,%(east_m)s+%(width_m)s)
          AND int4range(north_m,north_m+height_m) && int4range(%(north_m)s,%(north_m)s+%(height_m)s)
    ''', data).fetchone()
    if existing:
        raise HTTPException(409, f"勘测边界与 {existing['code']} 重叠")
    row = db.execute('''
        INSERT INTO vine_block(code,name,cultivar,area_ha,sensor,east_m,north_m,width_m,height_m)
        VALUES (%(code)s,%(name)s,%(cultivar)s,%(area_ha)s,%(sensor)s,%(east_m)s,%(north_m)s,%(width_m)s,%(height_m)s)
        RETURNING *
    ''', data).fetchone()
    event(db, actor, 'block_registered', row['code'], sensor=row['sensor'])
    return row


def record_sample(db, data, actor):
    block = one(db, 'SELECT code,sensor FROM vine_block WHERE id=%s', (data['block_id'],), '地块')
    if data['sensor'] != block['sensor']:
        raise HTTPException(409, f"{block['code']} 只接受绑定探头 {block['sensor']} 的读数")
    row = db.execute('''
        INSERT INTO microclimate_sample(block_id,sensor,observed_day,slot,temp_c,rh_pct,source,actor)
        VALUES (%(block_id)s,%(sensor)s,%(observed_day)s,%(slot)s,%(temp_c)s,%(rh_pct)s,%(source)s,%(actor)s)
        RETURNING *
    ''', dict(data, actor=actor)).fetchone()
    event(db, actor, 'sample_recorded', block['code'], sample_id=row['id'], slot=row['slot'],
          day=row['observed_day'].isoformat(), source=row['source'])
    return row


def sample_list(db, block_id):
    one(db, 'SELECT id FROM vine_block WHERE id=%s', (block_id,), '地块')
    return db.execute('''
        SELECT * FROM microclimate_sample WHERE block_id=%s
        ORDER BY observed_day DESC, slot LIMIT 120
    ''', (block_id,)).fetchall()
