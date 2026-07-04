"""§3.4.7  数据库物理脚本可执行性验证
用 :memory: 数据库完整执行 sql/database_schema.sql，然后校验：
    1) 表/视图/索引数量齐全
    2) 5 个视图返回正确行数
    3) 9 条业务查询中关键 7 条返回与样例数据匹配的结果
任何一步 assert 失败都立即退出，便于定位问题。
"""
import sqlite3
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_PATH = os.path.join(ROOT, 'sql', 'database_schema.sql')

# ---------- STEP 1: 执行全量脚本 ----------
print(f'--- STEP 1: 执行全量 SQL 脚本 ({SQL_PATH}) ---')
conn = sqlite3.connect(':memory:')
with open(SQL_PATH, 'r', encoding='utf-8') as f:
    conn.executescript(f.read())
print('✅ 脚本执行完毕（无异常）')

# ---------- STEP 2: 检查对象数量 ----------
print()
print('--- STEP 2: 检查表/视图/索引是否创建 ---')
objs = conn.execute(
    "SELECT type, name FROM sqlite_master "
    "WHERE type IN ('table','view','index') AND name NOT LIKE 'sqlite_%' "
    "ORDER BY type, name"
).fetchall()
t_cnt = sum(1 for x in objs if x[0] == 'table')
v_cnt = sum(1 for x in objs if x[0] == 'view')
i_cnt = sum(1 for x in objs if x[0] == 'index')
print(f'表: {t_cnt}  视图: {v_cnt}  索引: {i_cnt}')
for o in objs:
    print(f'  [{o[0]:5s}] {o[1]}')
assert t_cnt >= 1 and v_cnt >= 5 and i_cnt >= 7, (
    f'对象数目不足 (期望 1+5+7, 实际 {t_cnt}+{v_cnt}+{i_cnt})'
)

# ---------- STEP 3: 插入 3 条样例数据 ----------
print()
print('--- STEP 3: 插入 3 条样例数据并提交 ---')
conn.executemany(
    'INSERT INTO data(post,company,address,salary_min,salary_max,dateT,edu,exper) '
    'VALUES(?,?,?,?,?,?,?,?)',
    [
        ('PLC电气工程师',  '博易智汇科技（北京）', '北京-昌平区',   10, 15,
         '2026-05-06 10:26:42', '大专', '无需经验'),
        ('Python开发',    '上海联影医疗',        '上海-浦东新区', 15, 25,
         '2026-06-20 09:12:00', '本科', '3-5年'),
        ('电气工程师',    '北京生命科学研究所',  '北京-昌平区',   10, 20,
         '2026-06-17 09:27:22', '本科', '1年'),
    ],
)
conn.commit()
n_rows = conn.execute('SELECT COUNT(*) FROM data').fetchone()[0]
print(f'✅ data 表现有 {n_rows} 行 (期望 3)')
assert n_rows == 3, f'数据行数异常: {n_rows}'

# ---------- STEP 4: 5 个视图 ----------
print()
print('--- STEP 4: 验证 5 个视图 ---')

bkt = conn.execute(
    'SELECT bucket, cnt FROM v_salary_bucket ORDER BY bucket'
).fetchall()
print(f'  v_salary_bucket 返回 {len(bkt)} 行: {bkt}')
assert len(bkt) >= 2, f'分桶数量异常: {len(bkt)}'

city = conn.execute('SELECT city_name, cnt FROM v_city_rank').fetchall()
print(f'  v_city_rank 返回 {len(city)} 行: {city}')
assert len(city) == 2 and city[0][1] >= city[-1][1], (
    f'城市排序或数量异常: {city}'
)

edu = conn.execute('SELECT edu, cnt FROM v_edu_dist').fetchall()
print(f'  v_edu_dist 返回 {len(edu)} 行: {edu}')
assert len(edu) == 2 and sum(x[1] for x in edu) == 3

exp = conn.execute('SELECT exper, cnt FROM v_exper_dist').fetchall()
print(f'  v_exper_dist 返回 {len(exp)} 行: {exp}')
assert len(exp) >= 2

cat = conn.execute('SELECT category, cnt FROM v_category_rank').fetchall()
print(f'  v_category_rank 返回 {len(cat)} 行: {cat}')
assert sum(x[1] for x in cat) == 3

# ---------- STEP 5: 业务查询验证 ----------
print()
print('--- STEP 5: 验证 9 条典型查询 (节选 7 条) ---')

# Q1 列表：关键词=电气 + 城市=北京 + 分页
# （样例中 1 和 3 号匹配电气+北京，2 号为上海不匹配）
q1 = conn.execute(
    "SELECT post, company, address, salary_min, salary_max, dateT "
    "FROM data "
    "WHERE post LIKE '%电气%' AND address LIKE '北京%' "
    "ORDER BY dateT DESC "
    "LIMIT 12 OFFSET 0"
).fetchall()
print(f'  Q1 职位列表(电气/北京): {len(q1)} 条, 首条={q1[0][0] if q1 else None}')
assert len(q1) == 2, f'Q1 返回行数异常: {len(q1)} (期望 2)'

# Q2 分页总条数
q2 = conn.execute(
    "SELECT COUNT(*) FROM data WHERE post LIKE '%电气%' AND address LIKE '北京%'"
).fetchone()[0]
print(f'  Q2 同条件总条数: {q2} (期望 2)')
assert q2 == 2

# Q6 聚类训练集
q6 = conn.execute('SELECT post FROM data WHERE post IS NOT NULL').fetchall()
print(f'  Q6 聚类训练集: {len(q6)} 条职位名')
assert len(q6) == 3

# Q7 回归训练集（4 特征 + 标签）
q7 = conn.execute(
    "SELECT substr(address,1,instr(address||'-','-')-1), edu, exper, "
    "ROUND((salary_min+salary_max)/2,2) "
    "FROM data WHERE salary_min>0 OR salary_max>0"
).fetchall()
print(f'  Q7 回归训练集: {len(q7)} 条 4 特征+标签')
assert len(q7) == 3

# Q8 Agent: 北京各学历平均薪资
#   大专（北京昌平 10-15k）:  avg = 12.5
#   本科（北京昌平 10-20k）:  avg = 15.0
#   另一条为上海，被 WHERE 条件过滤
q8 = conn.execute(
    "SELECT edu, ROUND(AVG((salary_min+salary_max)/2),2) "
    "FROM data WHERE address LIKE '北京%' AND (salary_min>0 OR salary_max>0) "
    "GROUP BY edu ORDER BY edu"
).fetchall()
print(f'  Q8 北京-学历-平均薪资: {q8}')
expect = [('大专', 12.5), ('本科', 15.0)]
got = [(e, float(v)) for (e, v) in q8]
for pair in expect:
    assert pair in got, f'Q8 缺少期望条目 {pair}, 实际 {got}'

# Q9 >= 20k 高薪城市分布
q9 = conn.execute(
    "SELECT substr(address,1,instr(address||'-','-')-1) AS city, COUNT(*) "
    "FROM data WHERE salary_max >= 20 GROUP BY 1 ORDER BY 2 DESC"
).fetchall()
print(f'  Q9 >=20k 城市分布: {q9}')
assert ('北京', 1) in q9, f'Q9 期望 (北京,1) 在 {q9} 中'

# 交叉热力图：经验 × 学历 → 平均薪资
q_cross = conn.execute(
    "SELECT exper, edu, ROUND(AVG((salary_min+salary_max)/2),2) AS avg_k, COUNT(*) "
    "FROM data WHERE salary_min>0 OR salary_max>0 "
    "GROUP BY exper, edu ORDER BY COUNT(*) DESC"
).fetchall()
print(f'  Q 交叉热力图: {len(q_cross)} 组，首组={q_cross[0] if q_cross else None}')
assert len(q_cross) == 3, f'交叉组数异常: {len(q_cross)}'

# ---------- FINISH ----------
conn.close()
print()
print('===== 🎉 全部验证通过 =====')
sys.exit(0)
