from datetime import date, timedelta

from backend.src.auth import hash_password
from backend.src.clusters import submit
from backend.src.db import connect, lock_ledger

BASE_END = date(2026, 11, 14)
NEXT_END = date(2026, 11, 20)
PASSWORD = 'Vineyard271!'
BLOCKS = (
    ('V-01', '河湾低畦', '霞多丽', 1.22, 'WX-301', 90, 430, 195, 144),
    ('V-02', '北坡旧藤', '霞多丽', 1.56, 'WX-302', 317, 610, 243, 177),
    ('V-03', '石墙中段', '马瑟兰', 1.84, 'WX-303', 366, 369, 224, 174),
    ('V-04', '风口平台', '马瑟兰', 1.32, 'WX-304', 649, 590, 205, 162),
    ('V-05', '南向砾石台', '赤霞珠', 1.90, 'WX-305', 658, 319, 258, 175),
    ('V-06', '东侧新垄', '赤霞珠', 1.45, 'WX-306', 383, 108, 236, 140),
)
BASE = ((22.0, 11.5, 72, 89), (22.2, 11.7, 71, 88), (25.1, 14.0, 57, 76),
        (25.0, 14.2, 58, 76), (31.0, 20.0, 35, 55), (31.1, 20.2, 36, 54))


def seed():
    with connect() as db:
        lock_ledger(db)
        for name in ('operator', 'supervisor', 'viewer'):
            if not db.execute('SELECT 1 FROM account WHERE username=%s', (name,)).fetchone():
                db.execute('INSERT INTO account VALUES (%s,%s,%s)', (name, name, hash_password(PASSWORD)))
        for index, block in enumerate(BLOCKS):
            db.execute('''
                INSERT INTO vine_block(code,name,cultivar,area_ha,sensor,east_m,north_m,width_m,height_m)
                SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s WHERE NOT EXISTS (SELECT 1 FROM vine_block WHERE code=%s)
            ''', (*block, block[0]))
            row = db.execute('SELECT id,sensor FROM vine_block WHERE code=%s', (block[0],)).fetchone()
            for end in (BASE_END, NEXT_END):
                climate = (31.2, 20.0, 35, 55) if index == 1 and end == NEXT_END else BASE[index]
                for offset in (2, 1, 0):
                    day = end - timedelta(days=offset)
                    for j, phase in enumerate(('day', 'night')):
                        if index == 5 and end == NEXT_END and phase == 'night' and offset in (0, 1):
                            continue
                        db.execute('''
                            INSERT INTO microclimate_sample(block_id,sensor,observed_day,slot,temp_c,rh_pct,source,actor)
                            SELECT %s,%s,%s,%s,%s,%s,%s,'operator' WHERE NOT EXISTS (
                                SELECT 1 FROM microclimate_sample WHERE block_id=%s AND observed_day=%s AND slot=%s
                            )
                        ''', (row['id'], row['sensor'], day, phase, climate[j] + (1-offset)*0.2,
                              climate[j+2] + offset-1, f'wx-{end:%Y%m%d}.csv', row['id'], day, phase))
        if not db.execute('SELECT 1 FROM climate_run LIMIT 1').fetchone():
            submit(db, BASE_END, 'operator')


if __name__ == '__main__':
    seed()
    print('Seed ready: six blocks, two field windows, and three accounts.')
