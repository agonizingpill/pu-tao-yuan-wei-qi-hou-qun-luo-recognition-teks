"""Business queries over authoritative project records."""

VIEWS = {
    'watering-evidence': (
        '灌溉与采收对照',
        '按生效群落汇总已完成灌溉分钟数、观察覆盖率和平均糖度，并标记缺观察的群落。',
        ['群落', '完成轮次', '累计 分', '有采收观察', '覆盖 %', '平均糖度 Brix'],
        """
SELECT l.profile,COUNT(r.id) AS round_count,SUM(r.minutes),COUNT(h.id) AS observed_rounds,100.0*COUNT(h.id)/COUNT(r.id),AVG(h.brix)
FROM irrigation_round r JOIN climate_label l ON r.label_id=l.id LEFT JOIN harvest_note h ON h.round_id=r.id
WHERE r.state='completed' GROUP BY l.profile ORDER BY l.profile
""",
    ),
}
