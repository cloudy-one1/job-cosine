"""
完整Flask主程序 —— 替代教材 app.py。

跟教材的主要区别:
1. 数据库换成SQLite,不再需要Flask-SQLAlchemy这层ORM,
   直接用sqlite3做查询,跟项目里其他模块(region.py/jobtitle.py等)风格一致
2. 首页不再触发"实时爬虫",数据采集(collect_data.py)和网站展示是分离的两步
   ——这本身也是更合理的架构:数据采集可以独立、定期运行,
   网站只负责读取已采集好的数据并展示,不需要每次访问都现场爬一次
3. 新增 /advice 路由,接入Agent模块

项目包结构:
  data/       — 数据采集与清洗 (scraper, parser, cleaner)
  analysis/   — 描述性统计 (薪资、学历、经验、地区、职位分类)
  modeling/   — 机器学习与统计模型 (聚类、薪资分析)
  agent/      — 轻量 Agent (预加载DB概览+单次LLM调用, DeepSeek/千问双模型 fallback)
  templates/  — Flask 模板

运行: python app.py
访问: http://127.0.0.1:5000
"""
import os
import sys
import json
import uuid
import time
import requests
import warnings

# 消掉 jieba → pkg_resources 的弃用警告
warnings.filterwarnings('ignore', message='pkg_resources is deprecated', category=UserWarning)

import sqlite3
import re as _re
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, request, redirect, g, url_for, session, abort

from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config

# --- 日志系统 ----------------------------------------------------------------
# 同时输出到旋转日志文件(每5MB切一个,保留3个备份)和控制台
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(_log_dir, exist_ok=True)

_logger = logging.getLogger('job_analysis')
_logger.setLevel(logging.INFO)

_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, 'app.log'), maxBytes=5 * 1024 * 1024, backupCount=3,
    encoding='utf-8'
)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
))
_logger.addHandler(_file_handler)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
_logger.addHandler(_console_handler)

# --- 数据层 ---
from data.python_job_scraper import scrape_jobs
from data.salary_parser import parse_salary

# --- 聚类模型懒加载（无薪资预测模型） ---

app = Flask(__name__)

# --- 安全基础配置 ------------------------------------------------------------
# secret_key 用于 Flask session 签名与 Flask-WTF CSRF token 校验。
# 生产环境必须通过 FLASK_SECRET 环境变量注入固定值(否则重启后所有 session/token 失效)。
app.secret_key = os.environ.get('FLASK_SECRET') or os.urandom(32)

# 启用 Flask-WTF CSRF 保护。所有 POST 表单必须带 {{ csrf_token() }} 隐藏字段,
# 否则返回 400 Bad Request (防止跨站请求伪造)。
csrf = CSRFProtect(app)

# Flask-Limiter 速率限制: 全局限流 + 对危险路由(/collect)单独收紧
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
)

# SQLite WAL 模式: 设一次即持久化到数据库文件,后续所有连接自动受益(并发读不阻塞写)
try:
    if os.path.exists(config.DB_PATH):
        _wal_conn = sqlite3.connect(config.DB_PATH)
        _wal_conn.execute("PRAGMA journal_mode=WAL")
        _wal_conn.close()
except Exception:
    pass

PER_PAGE = 12

# =============================================================================
# 模块级状态 / 缓存变量（集中在此处，禁止分散定义）
# =============================================================================
_chart_analysis_cache = {}          # 图表 AI 分析结果缓存: {section: (timestamp, text)}
_ml_analysis_cache = {}             # /ml 页面 AI 分析结果缓存: {section: (timestamp, text)}
_CHART_CACHE_TTL = 300              # AI 分析缓存有效期，秒（5 分钟）
_ML_CACHE_TTL = 120                 # /ml AI 分析缓存有效期，秒（2 分钟，保证实时性）
_chart_data_cache = None            # 图表数据缓存: (timestamp, data_dict)
_CHART_DATA_CACHE_TTL = 300         # 图表数据缓存有效期，秒（5 分钟）
_clustering_cache = None            # 聚类结果懒加载缓存（首次 /ml 访问时训练填充）
_skill_heatmap_cache = None         # 技能供需热力图缓存
_job_similarity_cache = None        # 岗位相似度网络缓存
_salary_curve_cache = None          # 薪资成长曲线缓存
_edu_premium_cache = None           # 学历溢价分析缓存
_conversations = {}                 # Agent 对话持久化: {chat_uuid: {question, answer, trace}}


# --- 数据库迁移 ----------------------------------------------------------------
def init_db():
    """初始化数据库，确保包含所有必要字段（含新增的 keywords）"""
    try:
        db = sqlite3.connect(config.DB_PATH)
        cursor = db.cursor()
        
        # 检查 data 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data'")
        if not cursor.fetchone():
            # 表不存在，创建新表
            cursor.execute("""
                CREATE TABLE data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post TEXT, company TEXT, address TEXT,
                    salary_min REAL, salary_max REAL,
                    dateT TEXT, edu TEXT, exper TEXT, content TEXT,
                    keywords TEXT, job_url TEXT
                )
            """)
        else:
            # 表存在，检查是否有新字段
            cursor.execute("PRAGMA table_info(data)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'job_url' not in columns:
                cursor.execute("ALTER TABLE data ADD COLUMN job_url TEXT")
            if 'keywords' not in columns:
                cursor.execute("ALTER TABLE data ADD COLUMN keywords TEXT")
                
        db.commit()
        db.close()
        _logger.info('数据库初始化完成')
    except Exception as e:
        _logger.error('数据库初始化失败: %s', e)


# 应用启动时初始化数据库
init_db()


# --- 数据库连接管理 (Flask g 复用) -----------------------------------------
def get_db():
    """获取当前请求上下文中的 SQLite 连接;不存在则创建。
    连接在整个请求生命周期内复用,teardown 时自动关闭。"""
    if 'db' not in g:
        g.db = sqlite3.connect(config.DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    """请求结束时关闭数据库连接,避免连接泄漏。"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def _raw_connect():
    """为非请求上下文(启动预计算等)提供独立连接,调用方自行关闭。"""
    return sqlite3.connect(config.DB_PATH)


# --- 模型持久化 ------------------------------------------------------------
# 启动时优先从磁盘加载已训练的模型,避免每次重启都重训 (joblib)
def _cluster_cache_has_job_ids(cluster):
    """检查聚类缓存是否包含方向岗位明细所需的 job_ids 字段。"""
    if not isinstance(cluster, dict) or 'clusters' not in cluster:
        return False
    return all('job_ids' in c for c in cluster['clusters'])


def _load_or_train_models():
    """尝试加载磁盘缓存的聚类模型;失败或不存在/格式过旧则重训并持久化。"""
    import joblib as _joblib
    import modeling.job_clustering as job_clustering

    _cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
    os.makedirs(_cache_dir, exist_ok=True)
    _cluster_path = os.path.join(_cache_dir, 'clustering_result.joblib')

    if not _has_data():
        _logger.warning('数据库为空,跳过模型预计算。请先执行数据采集后再使用 /ml 和 Agent 功能。')
        return None

    # 尝试加载持久化聚类模型
    cluster = None
    try:
        if os.path.exists(_cluster_path):
            cluster = _joblib.load(_cluster_path)
            if not _cluster_cache_has_job_ids(cluster):
                _logger.info('检测到旧版聚类缓存缺少 job_ids,将重新训练')
                cluster = None
            else:
                _logger.info('从磁盘加载聚类结果 (k=%d)', cluster['k'])
    except Exception as e:
        _logger.warning('聚类结果加载失败,将重新计算: %s', e)

    # 缺失则训练
    try:
        if cluster is None:
            cluster = job_clustering.run_clustering()
            _joblib.dump(cluster, _cluster_path)
            _logger.info('聚类模型已训练并保存到磁盘 (k=%d)', cluster['k'])
    except Exception as e:
        _logger.error('聚类训练失败: %s。部分功能可能不可用。', e)
        cluster = None

    return cluster


def _has_data():
    """检查数据库中是否有可用的招聘数据。"""
    try:
        db = _raw_connect()
        count = db.cursor().execute("SELECT COUNT(*) FROM data").fetchone()[0]
        db.close()
        return count > 0
    except Exception as e:
        _logger.warning('数据库读取失败: %s', e)
        return False


# 相关缓存变量（_chart_analysis_cache / _chart_data_cache 等）已集中定义在模块顶部「模块级状态」区块

def _invalidate_chart_analysis_cache():
    """清空图表 AI 分析缓存 + 图表数据缓存 + /ml 分析缓存，采集新数据后必须调用。"""
    global _chart_data_cache
    _chart_analysis_cache.clear()
    _ml_analysis_cache.clear()
    _chart_data_cache = None
    _logger.debug('图表 AI 分析缓存 + 数据缓存 + /ml 分析缓存已清空')


def _compute_chart_data():
    """计算图表所需全部统计数据（带 5 分钟缓存）。"""
    global _chart_data_cache
    now = time.time()
    if _chart_data_cache and now - _chart_data_cache[0] < _CHART_DATA_CACHE_TTL:
        return _chart_data_cache[1]

    import analysis.xinzi as xinzi
    import analysis.xueli as xueli
    import analysis.jinyan as jinyan
    import analysis.region as region
    import analysis.cross as cross
    from analysis.wordcloud_gen import generate_wordcloud_data

    data = {
        'xz': xinzi.xinzi(),
        'xl': xueli.xuelifun(),
        'jy': jinyan.jinyanfun(),
        'city_data': region.regionfun(),
        'cross_exper': cross.salary_vs_exper(),
        'cross_edu': cross.salary_vs_edu(),
        'wc_data': generate_wordcloud_data(top_n=60),
    }
    _logger.info('图表数据缓存已更新')
    _chart_data_cache = (now, data)
    return data


# 聚类结果懒加载设计说明：
# 不在启动时触发 sklearn/pandas 的首次 .pyc 编译，
# 等首个访问 /ml 的请求到来时才计算（避免误判启动卡死）。

def _get_clustering():
    """获取聚类结果（首次调用时训练+缓存，后续直接返回）。"""
    global _clustering_cache
    if _clustering_cache is not None:
        return _clustering_cache
    _logger.info('正在预计算职位聚类(只在第一次访问时跑一次)...')
    _clustering_cache = _load_or_train_models()
    if _clustering_cache is not None:
        _logger.info('预计算完成。')
    return _clustering_cache


def _get_skill_heatmap():
    """获取技能供需热力图数据（懒加载缓存）。"""
    global _skill_heatmap_cache
    if _skill_heatmap_cache is not None:
        return _skill_heatmap_cache
    try:
        from modeling.skill_heatmap import compute_skill_heatmap
        _skill_heatmap_cache = compute_skill_heatmap()
    except Exception as e:
        _logger.warning('技能热力图计算失败: %s', e)
        _skill_heatmap_cache = {'error': str(e), 'total_rows': 0}
    return _skill_heatmap_cache


def _get_similarity():
    """获取岗位相似度网络数据（懒加载缓存）。"""
    global _job_similarity_cache
    if _job_similarity_cache is not None:
        return _job_similarity_cache
    clustering = _get_clustering()
    if not clustering:
        _job_similarity_cache = {'error': '聚类模型未训练'}
        return _job_similarity_cache
    try:
        from modeling.job_similarity import compute_similarity_network
        _job_similarity_cache = compute_similarity_network(clustering)
    except Exception as e:
        _logger.warning('相似度网络计算失败: %s', e)
        _job_similarity_cache = {'error': str(e)}
    return _job_similarity_cache


def _get_salary_curve():
    """获取薪资成长曲线数据（懒加载缓存）。"""
    global _salary_curve_cache
    if _salary_curve_cache is not None:
        return _salary_curve_cache
    try:
        from modeling.salary_curve import compute_salary_curve
        _salary_curve_cache = compute_salary_curve()
    except Exception as e:
        _logger.warning('薪资曲线计算失败: %s', e)
        _salary_curve_cache = {'error': str(e), 'total_rows': 0}
    return _salary_curve_cache


def _get_edu_premium():
    """获取学历溢价分析数据（懒加载缓存）。"""
    global _edu_premium_cache
    if _edu_premium_cache is not None:
        return _edu_premium_cache
    try:
        from modeling.edu_premium import compute_edu_premium
        _edu_premium_cache = compute_edu_premium()
    except Exception as e:
        _logger.warning('学历溢价计算失败: %s', e)
        _edu_premium_cache = {'error': str(e), 'total_rows': 0}
    return _edu_premium_cache


def _invalidate_modeling_caches():
    """清空所有建模模块缓存（采集新数据/重训后调用）。"""
    global _skill_heatmap_cache, _job_similarity_cache, _salary_curve_cache, _edu_premium_cache
    _skill_heatmap_cache = None
    _job_similarity_cache = None
    _salary_curve_cache = None
    _edu_premium_cache = None
    _logger.debug('建模模块全部缓存已清空')


@app.route('/')
def index():
    from data.python_job_scraper import get_province_city_map
    city_map = get_province_city_map()
    return render_template('input.html', city_map_json=json.dumps(city_map, ensure_ascii=False))


@app.route('/api/warmup')
def api_warmup():
    """静默预热接口：首页加载后前端静默调用，提前计算图表数据 + 全部建模模块。
    此后用户点「图表分析」「薪资洞察」即可秒开，无需等待训练。"""
    # 图表数据（/chart 页面）
    try:
        _compute_chart_data()
    except Exception as e:
        _logger.warning('预热图表数据失败: %s', e)
    # 聚类模型（/ml 页面核心）
    try:
        _get_clustering()
    except Exception as e:
        _logger.warning('预热聚类模型失败: %s', e)
    # 技能热力图
    try:
        _get_skill_heatmap()
    except Exception as e:
        _logger.warning('预热技能热力图失败: %s', e)
    # 岗位相似度网络
    try:
        _get_similarity()
    except Exception as e:
        _logger.warning('预热相似度网络失败: %s', e)
    # 薪资成长曲线
    try:
        _get_salary_curve()
    except Exception as e:
        _logger.warning('预热薪资曲线失败: %s', e)
    # 学历溢价分析
    try:
        _get_edu_premium()
    except Exception as e:
        _logger.warning('预热学历溢价分析失败: %s', e)
    _logger.info('预热完成: 图表数据 + 聚类 + 热力图 + 相似度 + 薪资曲线 + 学历溢价均已就绪')
    return '{"ok":true}', 200, {'Content-Type': 'application/json'}


@app.route('/list')
def list_data():
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    page = max(1, page)  # 避免页码为0或负数
    kw = request.args.get('kw', '').strip()
    city_raw = request.args.get('city', '').strip()
    cities = [c.strip() for c in _re.split(r'[,，\s]+', city_raw) if c.strip()]

    db = sqlite3.connect(config.DB_PATH)
    cursor = db.cursor()

    conditions = []
    params = []
    if kw:
        conditions.append("LOWER(post) = LOWER(?)")
        params.append(kw)
    if cities:
        city_conditions = " OR ".join(["LOWER(address) = LOWER(?)"] * len(cities))
        conditions.append(f"({city_conditions})")
        params.extend(cities)
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        f"SELECT id, post, company, address, salary_min, salary_max, dateT FROM data "
        f"{where_clause} LIMIT ? OFFSET ?",
        (*params, PER_PAGE, (page - 1) * PER_PAGE)
    )
    rows = cursor.fetchall()
    cursor.execute(f"SELECT COUNT(*) FROM data {where_clause}", params)
    total = cursor.fetchone()[0]
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    return render_template(
        'data.html', rows=rows, kw=kw, city=city_raw, page=page,
        total=total, total_pages=total_pages
    )


@app.route('/job/<int:job_id>')
def job_detail(job_id):
    """岗位详情页面"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT id, post, company, address, salary_min, salary_max, dateT, edu, exper, content, job_url "
        "FROM data WHERE id = ?",
        (job_id,)
    )
    job = cursor.fetchone()

    if job is None:
        return render_template('job_detail.html', job=None, error='未找到该岗位信息')

    # 将 Row 对象转换为字典，方便模板访问
    job_dict = {
        'id': job['id'],
        'post': job['post'],
        'company': job['company'],
        'address': job['address'],
        'salary_min': job['salary_min'],
        'salary_max': job['salary_max'],
        'dateT': job['dateT'],
        'edu': job['edu'],
        'exper': job['exper'],
        'content': job['content'],
        'job_url': job['job_url'] or ''  # 兼容旧数据（NULL 回退为 ''）
    }

    return render_template('job_detail.html', job=job_dict, error=None)


@app.route('/chart')
@app.route('/chart/<section>')
def chart(section='city'):
    valid_sections = {'city', 'salary', 'xueli', 'jinyan', 'wordcloud', 'cross'}
    if section not in valid_sections:
        section = 'city'
    data = _compute_chart_data()
    return render_template('h.html', section=section, **data)


@app.route('/chart/analyze', methods=['POST'])
def chart_analyze():
    """DeepSeek 数据驱动图表分析接口（带 5 分钟服务端缓存）。
    首次调用后相同 section 的结果被缓存，后续请求直接返回，实现秒开。
    采集新数据后缓存由 /collect 主动清空。"""
    import json as _json
    data = request.get_json(silent=True) or {}
    section = data.get('section', 'city')
    valid_sections = {'city', 'salary', 'xueli', 'jinyan', 'wordcloud', 'cross'}
    if section not in valid_sections:
        return _json.dumps({'error': '无效的分析类型'}), 400

    # 缓存命中 → 直接返回
    cached = _chart_analysis_cache.get(section)
    if cached and (time.time() - cached[0]) < _CHART_CACHE_TTL:
        _logger.debug('图表 AI 缓存命中: section=%s', section)
        return cached[1]

    # 获取所有数据(复用图表数据缓存)
    try:
        chart_data = _compute_chart_data()
        xz_val = chart_data['xz']
        xl_val = chart_data['xl']
        jy_val = chart_data['jy']
        city_val = chart_data['city_data']
        cross_exper = chart_data['cross_exper']
        cross_edu = chart_data['cross_edu']
        wc_val = chart_data['wc_data']
    except Exception as e:
        return _json.dumps({'error': f'数据查询失败: {str(e)}'}), 500

    # 拼装面向 DeepSeek 的数据描述
    labels_xz = ['<5k', '5-8k', '8-11k', '11-14k', '14-17k', '17-20k', '20-23k', '23k+']
    total_jobs = sum(xz_val)
    salary_desc = '、'.join([f'{labels_xz[i]} {xz_val[i]}个' for i in range(len(xz_val))])
    city_desc_lines = [f'{c[0]} {c[1]}个' for c in city_val[:10]]
    xl_desc = '、'.join([f'{l[0]} {l[1]}个' for l in xl_val])
    jy_desc = '、'.join([f'{j[0]} {j[1]}个' for j in jy_val])
    wc_top_desc = '、'.join([f'{w[0]}({w[1]}次)' for w in (wc_val.get('words', []) or [])[:10]])

    exper_desc = ''
    if cross_exper and cross_exper.get('labels'):
        exper_desc = '、'.join([
            f'{cross_exper["labels"][i]} 平均{cross_exper["avg_salaries"][i]}k({cross_exper["counts"][i]}个)'
            for i in range(len(cross_exper['labels']))
        ])
    edu_desc = ''
    if cross_edu and cross_edu.get('labels'):
        edu_desc = '、'.join([
            f'{cross_edu["labels"][i]} 平均{cross_edu["avg_salaries"][i]}k({cross_edu["counts"][i]}个)'
            for i in range(len(cross_edu['labels']))
        ])

    section_map = {
        'city': (f'当前共有{total_jobs}个职位,分布在前10的城市为:{city_desc_lines}',
                 '请你只针对城市分布给出直观分析,指出岗位集中趋势、核心城市及求职建议。用中文,150-300字,直接说结论,不要问候语。'),
        'salary': (f'薪资分布(共{total_jobs}个有薪资的职位): {salary_desc}',
                   '请你只针对薪资分布给出直观分析,指出主力薪资区间、高薪与低薪占比、以及薪资结构特征。用中文,150-300字,直接说结论,不要问候语。'),
        'xueli': (f'学历分布: {xl_desc}',
                  '请你只针对学历要求分布给出直观分析,指出市场主流的学历门槛、各学历占比态势。用中文,150-300字,直接说结论,不要问候语。'),
        'jinyan': (f'经验要求分布: {jy_desc}',
                   '请你只针对经验要求分布给出直观分析,指出市场最需求的年资段。用中文,150-300字,直接说结论,不要问候语。'),
        'wordcloud': (f'岗位描述高频技能词TOP10: {wc_top_desc}',
                      '请你只针对这些高频技能词给出直观分析,指出当前市场对Python开发者的核心技能要求方向。用中文,150-300字,直接说结论,不要问候语。'),
        'cross': (f'交叉分析:\n1) 经验 vs 平均薪资: {exper_desc}\n2) 学历 vs 平均薪资: {edu_desc}',
                  '请分三段输出,每段加粗标题:\n'
                  '1) 【经验 vs 薪资 独立分析】只针对"薪资 vs 经验等级"图进行分析,指出各经验段的平均薪资趋势、职位数量分布特征、哪个经验段薪资溢价最高。\n'
                  '2) 【学历 vs 薪资 独立分析】只针对"薪资 vs 学历"图进行分析,指出各学历层次的平均薪资差异、学历溢价效应。\n'
                  '3) 【综合分析】对比两段分析,指出经验与学历对薪资的影响哪个更大,并给出求职者针对性的职业规划建议。\n'
                  '用中文,每段150-200字,直接说结论,不要问候语。'),
    }

    data_desc, instruction = section_map[section]

    prompt = f"""以下是当前招聘数据库中通过爬虫真实采集的数据。请严格据此给出分析。

【数据】
{data_desc}

【要求】
{instruction}

重要约束:
- 数据结论必须来自上述数据的具体数字,限定在"本数据库采集的岗位中"。
- 不得编造具体数字。数据不足时诚实说明"暂无相关数据"。
- 可适当补充普适性求职建议(非数据库内容),但必须用 **【普适性建议】** 前缀标注,与数据结论明确区分。"""
    api_key = getattr(config, 'DEEPSEEK_API_KEY', '')
    qwen_key = getattr(config, 'QWEN_API_KEY', '')
    if not api_key and not qwen_key:
        return _json.dumps({'error': 'DEEPSEEK_API_KEY 和 QWEN_API_KEY 均未配置,无法生成分析'}), 503

    try:
        from agent.agent_core import call_llm_with_fallback
        messages = [
            {'role': 'system', 'content': '你是招聘数据分析助手。数据结论必须来自提供的真实采集数据;可补充普适性建议但必须用**【普适性建议】**标注;数据不足时诚实说明;不编造具体数字。输出纯文本中文。'},
            {'role': 'user', 'content': prompt},
        ]
        analysis, _provider = call_llm_with_fallback(messages, deepseek_key=api_key)
        _chart_analysis_cache[section] = (time.time(), analysis)
        _logger.info('图表 AI 分析 provider=%s section=%s', _provider, section)
        return analysis
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
        msg = 'AI 服务暂时繁忙,请稍后再试' if status == 429 else f'AI 分析生成失败: {str(e)}'
        return _json.dumps({'error': msg}), 503
    except Exception as e:
        return _json.dumps({'error': f'AI 分析生成失败: {str(e)}'}), 500


@app.route('/ml/analyze', methods=['POST'])
def ml_analyze():
    """/ml 页面各图表 AI 解读接口（带 2 分钟服务端缓存，支持 fresh 参数强制刷新）。"""
    import json as _json
    data = request.get_json(silent=True) or {}
    section = data.get('section', 'cluster')
    force_fresh = data.get('fresh', False)
    valid_sections = {'cluster', 'heatmap', 'similarity', 'salary_curve', 'edu_premium'}
    if section not in valid_sections:
        return _json.dumps({'error': '无效的分析类型'}), 400

    # 缓存命中 → 直接返回（fresh=1 时跳过缓存）
    cached = _ml_analysis_cache.get(section)
    if not force_fresh and cached and (time.time() - cached[0]) < _ML_CACHE_TTL:
        _logger.debug('/ml AI 缓存命中: section=%s', section)
        return cached[1]

    # 获取各模块数据
    clustering = _get_clustering()
    if not clustering:
        return _json.dumps({'error': '请先采集数据'}), 503

    heatmap = _get_skill_heatmap()
    similarity = _get_similarity()
    salary_curve = _get_salary_curve()
    edu_premium = _get_edu_premium()

    # 组装各 section 的数据描述与指令
    section_map = {}

    # --- cluster ---
    clusters_desc_lines = []
    for c in clustering.get('clusters', []):
        kw_str = '、'.join(c.get('top_keywords', [])[:6])
        clusters_desc_lines.append(
            f"【{c.get('auto_label','')}】{c.get('count',0)}岗,"
            f"均薪{c.get('avg_salary',0):.1f}K,"
            f"区间{c.get('min_salary',0)}-{c.get('max_salary',0)}K,"
            f"关键词:{kw_str}"
        )
    cluster_desc = '\n'.join(clusters_desc_lines)
    section_map['cluster'] = (
        f'聚类将{clustering.get("total_jobs",0)}个岗位分为{clustering.get("k",0)}个方向:\n{cluster_desc}',
        '请分析各方向的岗位规模差异、薪资区间特征以及关键词反映的技术方向差异。'
        '指出规模最大/薪资最高的方向,并给 Python 开发者选择方向的具体建议。'
        '用中文,200-350字,直接说结论,不要问候语。'
    )

    # --- heatmap ---
    heatmap_desc = ''
    if heatmap and not heatmap.get('error'):
        skills = heatmap.get('skills', [])
        cities = heatmap.get('cities', [])
        matrix = heatmap.get('salary_matrix', [])
        top_skills = skills[:8]
        top_cities = cities[:6]
        highlights = []
        for i, skill in enumerate(top_skills):
            for j, city in enumerate(top_cities):
                if i < len(matrix) and j < len(matrix[i]) and matrix[i][j] is not None:
                    if matrix[i][j] >= 20:
                        highlights.append(f'{city}·{skill}={matrix[i][j]}K')
        heatmap_desc = f'技能: {",".join(top_skills)}; 城市: {",".join(top_cities)}; '
        heatmap_desc += f'高薪亮点: {"; ".join(highlights[:15]) if highlights else "各城市技能薪资大致在10-30K区间"}'
        section_map['heatmap'] = (
            heatmap_desc,
            '请根据热力图数据,分析不同技能在各城市的薪资冷热分布:哪些技能在多个城市都是高薪(通用高价值技能),'
            '哪些技能只在特定城市突出(地域性技能)。'
            '指出求职者如果想靠某项技能拿到更高薪资,应该重点关注哪些城市,以及哪些技能组合覆盖面最广。'
            '用中文,180-300字,直接说结论,不要问候语。'
        )

    # --- similarity ---
    sim_desc = ''
    if similarity and not similarity.get('error'):
        nodes = similarity.get('nodes', [])
        links = similarity.get('links', [])
        top_links = sorted(links, key=lambda x: x.get('value', 0), reverse=True)[:5]
        node_names = [n.get('name', '') for n in nodes[:10]]
        sim_desc = f'方向节点: {",".join(node_names)}; '
        sim_desc += '高相似度关系: ' + '; '.join([
            f'{lk.get("source","")}↔{lk.get("target","")}=({(lk.get("value",0)*100):.0f}%)'
            for lk in top_links
        ]) if top_links else '暂无显著相似关系'
        section_map['similarity'] = (
            sim_desc,
            '请分析岗位方向之间的可迁移性:哪些方向技能重叠度高、转方向容易;哪些方向相对独立。'
            '给出一条具体的转方向建议。'
            '用中文,180-300字,直接说结论,不要问候语。'
        )

    # --- salary_curve ---
    curve_desc = ''
    if salary_curve and not salary_curve.get('error'):
        overall = salary_curve.get('overall', [])
        curve_lines = [
            f'{d.get("exper","")}段 中位{d.get("median",0)}K 均值{d.get("mean",0)}K({d.get("count",0)}岗)'
            for d in overall
        ]
        curve_desc = '经验-薪资趋势: ' + '; '.join(curve_lines)
        if len(overall) >= 2:
            max_growth, max_idx = 0, 0
            for i in range(1, len(overall)):
                g = overall[i].get('median', 0) - overall[i-1].get('median', 0)
                if g > max_growth:
                    max_growth, max_idx = g, i
            curve_desc += f'\n薪资跃升最快阶段: {overall[max_idx-1].get("exper","")}→{overall[max_idx].get("exper","")}(+{max_growth}K)'
        section_map['salary_curve'] = (
            curve_desc,
            '请分析薪资随经验的成长规律:哪个阶段增幅最大、天花板在哪。'
            '给求职者关于经验积累与薪资预期的建议。'
            '用中文,180-300字,直接说结论,不要问候语。'
        )

    # --- edu_premium ---
    edu_desc = ''
    if edu_premium and not edu_premium.get('error'):
        overall_edu = edu_premium.get('overall', {})
        edu_lines = []
        for level in ['博士', '硕士', '本科', '大专', '高中']:
            if level in overall_edu:
                d = overall_edu[level]
                edu_lines.append(f'{level} 中位{d.get("median",0)}K 均值{d.get("avg_salary",0)}K({d.get("count",0)}岗)')
        edu_desc = '各学历整体薪资: ' + '; '.join(edu_lines)
        premiums = edu_premium.get('premiums', [])
        if premiums:
            top_p = []
            for p in premiums[:5]:
                for prem in p.get('premiums', [])[:3]:
                    top_p.append(
                        f'{p.get("city","")}-{p.get("category","")}: '
                        f'{prem.get("from","")}→{prem.get("to","")}溢价{prem.get("premium_pct",0)}%'
                    )
            edu_desc += '\n典型溢价案例: ' + '; '.join(top_p[:8])
        section_map['edu_premium'] = (
            edu_desc,
            '请分析学历对薪资的真实影响:高学历溢价是否显著、哪些方向学历溢价最高。'
            '给不同学历背景的求职者针对性建议。'
            '用中文,180-300字,直接说结论,不要问候语。'
        )

    if section not in section_map:
        return _json.dumps({'error': '数据不足,无法生成该分析'}), 503

    data_desc, instruction = section_map[section]

    prompt = f"""以下是当前招聘数据库中通过爬虫真实采集并建模后的数据。请严格据此给出分析。

【数据】
{data_desc}

【要求】
{instruction}

重要约束:
- 数据结论必须来自上述数据的具体数字,限定在"本数据库采集的岗位中"。
- 不得编造具体数字。数据不足时诚实说明"暂无相关数据"。
- 可适当补充普适性求职建议(非数据库内容),但必须用 **【普适性建议】** 前缀标注,与数据结论明确区分。"""

    api_key = getattr(config, 'DEEPSEEK_API_KEY', '')
    qwen_key = getattr(config, 'QWEN_API_KEY', '')
    if not api_key and not qwen_key:
        return _json.dumps({'error': 'DEEPSEEK_API_KEY 和 QWEN_API_KEY 均未配置,无法生成分析'}), 503

    try:
        from agent.agent_core import call_llm_with_fallback
        messages = [
            {'role': 'system', 'content': '你是招聘数据分析与建模解读助手。数据结论必须来自提供的真实采集数据;可补充普适性建议但必须用**【普适性建议】**标注;数据不足时诚实说明;不编造具体数字。输出纯文本中文。'},
            {'role': 'user', 'content': prompt},
        ]
        analysis, _provider = call_llm_with_fallback(messages, deepseek_key=api_key)
        _ml_analysis_cache[section] = (time.time(), analysis)
        _logger.info('/ml AI 分析 provider=%s section=%s', _provider, section)
        return analysis
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None
        msg = 'AI 服务暂时繁忙,请稍后再试' if status == 429 else f'AI 分析生成失败: {str(e)}'
        return _json.dumps({'error': msg}), 503
    except Exception as e:
        return _json.dumps({'error': f'AI 分析生成失败: {str(e)}'}), 500


@app.route('/ml')
def ml_page():
    clustering = _get_clustering()
    total_jobs = clustering.get('total_jobs', 0) if clustering else 0

    # 懒加载四个新功能的数据
    heatmap = _get_skill_heatmap() if clustering else {'error': '请先采集数据'}
    similarity = _get_similarity() if clustering else {'error': '请先采集数据'}
    salary_curve = _get_salary_curve() if clustering else {'error': '请先采集数据'}
    edu_premium = _get_edu_premium() if clustering else {'error': '请先采集数据'}

    return render_template(
        'ml.html',
        clustering=clustering,
        total_jobs=total_jobs,
        heatmap=heatmap,
        similarity=similarity,
        salary_curve=salary_curve,
        edu_premium=edu_premium,
    )


@app.route('/ml/cluster/<int:cluster_id>')
def cluster_jobs(cluster_id):
    """点击 /ml 页面的方向卡片后，展示该簇包含的所有岗位列表。"""
    clustering = _get_clustering()
    if not clustering:
        abort(404)

    cluster = None
    for c in clustering.get('clusters', []):
        if c.get('cluster_id') == cluster_id:
            cluster = c
            break
    if not cluster:
        abort(404)

    job_ids = cluster.get('job_ids', [])
    if not job_ids:
        rows = []
    else:
        db = sqlite3.connect(config.DB_PATH)
        db.row_factory = sqlite3.Row
        cursor = db.cursor()
        placeholders = ','.join('?' * len(job_ids))
        cursor.execute(
            f"SELECT id, post, company, address, salary_min, salary_max, dateT "
            f"FROM data WHERE id IN ({placeholders}) ORDER BY id DESC",
            job_ids,
        )

        rows = cursor.fetchall()
        db.close()

    return render_template(
        'cluster_jobs.html',
        cluster=cluster,
        rows=rows,
    )


@app.route('/collect', methods=['GET', 'POST'])
@limiter.limit("5 per hour")  # 采集接口单独限流,防止滥用
def collect():
    """
    用户指定关键词+城市,触发一次真实的51job实时采集(Playwright+stealth),
    采集结果写入data表,供后续所有分析(图表/聚类/预测/Agent)直接使用。

    表单本身在首页(input.html),这里只处理提交;GET请求优先从 session 恢复
    上次采集结果（若有），否则重定向回首页。

    注意: 这是同步阻塞调用,一次采集通常耗时5~10秒(过WAF)+每页约0.3秒,
    城市和页数设了上限,避免单次请求耗时过长。
    """
    if request.method != 'POST':
        # 支持清除: /collect?clear_collect=1
        if request.args.get('clear_collect') == '1':
            session.pop('collect_state', None)
            return redirect('/')
        # 尝试从 session 恢复上次采集结果
        collect_state = session.get('collect_state')
        if collect_state:
            return render_template('collect.html', restored=True, **collect_state)
        return redirect('/')

    # --- 采集口令校验 --------------------------------------------------------
    # 若 .env 中设置了 COLLECT_TOKEN,则要求表单中提交匹配的 token 字段,
    # 否则拒绝采集 —— 防止演示/教学场景下被人误操作清空数据。
    if config.COLLECT_TOKEN:
        form_token = request.form.get('token', '')
        if form_token != config.COLLECT_TOKEN:
            return render_template(
                'collect.html',
                error='采集口令不正确,请联系管理员获取',
                keyword=request.form.get('kw', '').strip(),
                city=request.form.get('city', '').strip(),
            ), 403

    keyword = request.form.get('kw', '').strip()
    city_raw = request.form.get('city', '').strip()
    # 同时支持中文逗号"，"、英文逗号","、空格分隔,
    # 之前只认英文逗号,用户用中文输入法打的全角逗号"，"不会被拆开,
    # 导致整段文字被当成一个城市名传进去(实测踩到的真实bug)
    cities = [c.strip() for c in _re.split(r'[,，\s]+', city_raw) if c.strip()]
    try:
        pages = int(request.form.get('pages', 2))
    except ValueError:
        pages = 2
    pages = max(1, min(pages, 5))  # 安全上限,防止单次请求耗时过长

    sort_type = request.form.get('sort_type', '0')
    if sort_type not in ('0', '1'):
        sort_type = '0'

    if not keyword:
        return render_template('collect.html', error='请输入采集关键词')

    sort_label = {'0': '综合排序', '1': '最新发布'}.get(sort_type, '未知')
    _logger.info('采集开始: 关键词=%s, 城市=%s, 页数=%d, 排序=%s', keyword, cities, pages, sort_label)
    try:
        jobs, pages_collected = scrape_jobs(keyword, cities, pages_per_city=pages, sort_type=sort_type)
    except Exception as e:
        _logger.error('采集异常: %s', e)
        # 不把原始异常信息直接抛给前端,避免泄露内部路径/堆栈信息
        return render_template('collect.html', error='采集过程发生错误,请稍后重试',
                                keyword=keyword, city=city_raw)

    if not jobs:
        return render_template(
            'collect.html',
            error='没有采集到任何数据,可能是WAF拦截了这次请求,或者关键词/城市没有匹配结果,换个关键词或稍后再试',
            keyword=keyword, city=city_raw,
        )

    # 先写入临时数据,确认成功后再替换旧数据(原子性保护:
    # 如果写入过程中途失败,旧数据依然保留,不会出现空库)
    db = get_db()
    cursor = db.cursor()
    success = 0
    for j in jobs:
        smin, smax = parse_salary(j['salary_raw'])
        try:
            cursor.execute(
                "insert into data (post,company,address,salary_min,salary_max,"
                "dateT,edu,exper,content,keywords,job_url) values(?,?,?,?,?,?,?,?,?,?,?)",
                (j['post'], j['company'], j['address'], smin, smax,
                 j['dateT'], j['edu'], j['exper'], j.get('content', ''),
                 j.get('keywords', ''), j.get('job_url', ''))
            )
            success += 1
        except Exception:
            pass
    # 只有成功写入至少一条数据后,才清空旧数据并提交
    if success > 0:
        cursor.execute(
            "DELETE FROM data WHERE rowid NOT IN "
            "(SELECT rowid FROM data ORDER BY rowid DESC LIMIT ?)",
            (success,)
        )
    db.commit()

    # 数据变了，图表 AI 缓存 + 模型缓存都要失效
    _invalidate_chart_analysis_cache()
    _invalidate_modeling_caches()

    # 数据变了,聚类模型也要跟着重新算一遍
    global _clustering_cache
    import joblib as _joblib
    import modeling.job_clustering as job_clustering
    _cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
    _cluster_path = os.path.join(_cache_dir, 'clustering_result.joblib')
    try:
        _clustering_cache = job_clustering.run_clustering()
        _joblib.dump(_clustering_cache, _cluster_path)
        _logger.info('采集后聚类模型已重新训练并持久化 (k=%d)', _clustering_cache['k'])
    except Exception as e:
        _logger.warning('采集后聚类模型重算失败: %s', e)

    # 保存采集结果到 session，跨页面导航后可恢复
    session['collect_state'] = {
        'success_count': success,
        'total_count': len(jobs),
        'keyword': keyword,
        'city': city_raw,
        'pages_per_city': pages,
        'pages_collected': pages_collected,
    }

    return render_template(
        'collect.html', success_count=success, total_count=len(jobs),
        keyword=keyword, city=city_raw,
        pages_per_city=pages, pages_collected=pages_collected,
    )


@app.route('/advice', methods=['GET', 'POST'])
def advice():
    if request.method != 'POST':
        # GET: 支持清除操作
        tool = request.args.get('tool', 'agent')

        # 清除 Agent 对话: /advice?clear_agent=1
        if request.args.get('clear_agent') == '1':
            chat_id = session.pop('chat_id', None)
            if chat_id:
                _conversations.pop(chat_id, None)
            return redirect(url_for('advice'))

        # 清除对比结果: /advice?clear_compare=1
        if request.args.get('clear_compare') == '1':
            session.pop('compare_state', None)
            return redirect(url_for('advice'))

        # 清除匹配结果: /advice?clear_match=1
        if request.args.get('clear_match') == '1':
            session.pop('match_state', None)
            return redirect(url_for('advice'))
        # 清除简历审查结果: /advice?clear_review=1
        if request.args.get('clear_review') == '1':
            session.pop('review_state', None)
            return redirect(url_for('advice'))

        # 尝试从 session 恢复上一次对话状态
        chat_id = session.get('chat_id')
        agent_state = _conversations.get(chat_id) if chat_id else None
        compare_state = session.get('compare_state')
        match_state = session.get('match_state')

        if agent_state:
            return render_template('advice.html', active_tab=tool,
                                   question=agent_state.get('question'),
                                   answer=agent_state.get('answer'),
                                   trace=agent_state.get('trace'),
                                   critique=agent_state.get('critique', ''),
                                   restored_agent=True)
        if compare_state:
            return render_template('advice.html', active_tab='compare',
                                   compare_result=compare_state.get('result'),
                                   compare_a=compare_state.get('a'),
                                   compare_b=compare_state.get('b'),
                                   restored_compare=True)
        if match_state:
            return render_template('advice.html', active_tab='match',
                                   match_result=match_state.get('result'),
                                   match_skills=match_state.get('skills'),
                                   match_city=match_state.get('city'),
                                   match_edu=match_state.get('edu'),
                                   match_exper=match_state.get('exper'),
                                   restored_match=True)

        review_state = session.get('review_state')
        if review_state:
            return render_template('advice.html', active_tab='review',
                                   review_result=review_state.get('result'),
                                   review_text=review_state.get('text'),
                                   review_city=review_state.get('city'),
                                   review_category=review_state.get('category'),
                                   restored_review=True)

        return render_template('advice.html', active_tab=tool)

    tool = request.form.get('tool', 'agent')

    # --- 综合 Agent 模式（默认） ---
    if tool == 'agent':
        question = request.form.get('question', '').strip()
        if not question:
            return render_template('advice.html', error='请输入你的问题', active_tab='agent')
        api_key = getattr(config, 'DEEPSEEK_API_KEY', '')
        qwen_key = getattr(config, 'QWEN_API_KEY', '')
        if not api_key and not qwen_key:
            return render_template('advice.html', error='请先在.env配置DEEPSEEK_API_KEY或QWEN_API_KEY',
                                   question=question, active_tab='agent')
        try:
            from agent.agent_core import run_agent
            answer, data_context = run_agent(question)
        except Exception:
            return render_template('advice.html', error='Agent调用失败,请稍后重试',
                                   question=question, active_tab='agent')

        # 保存 Agent 对话到服务端会话存储
        chat_id = str(uuid.uuid4())
        _conversations[chat_id] = {'question': question, 'answer': answer, 'data_context': data_context}
        session['chat_id'] = chat_id
        # 清理旧对比/技能结果（新对话后可能过时）
        session.pop('compare_state', None)
        session.pop('match_state', None)
        session.pop('review_state', None)

        return render_template('advice.html', question=question, answer=answer,
                               data_context=data_context, active_tab='agent')

    # --- 城市对比工具 ---
    if tool == 'compare':
        a = request.form.get('a', '').strip()
        b = request.form.get('b', '').strip()
        if not a or not b:
            return render_template('advice.html', compare_error='请输入两个要对比的城市',
                                   compare_a=a, compare_b=b, active_tab='compare')
        try:
            from agent.agent_tools import compare_jobs
            compare_result = compare_jobs('city', a, b)
        except Exception:
            return render_template('advice.html', compare_error='对比查询失败,请稍后重试',
                                   compare_a=a, compare_b=b, active_tab='compare')

        # 保存对比结果到 session
        session['compare_state'] = {'result': compare_result, 'a': a, 'b': b}

        return render_template('advice.html', compare_result=compare_result,
                               compare_a=a, compare_b=b, active_tab='compare')

    # --- 岗位匹配推荐工具 ---
    if tool == 'match':
        skills = request.form.get('skills', '').strip()
        city = request.form.get('city', '').strip()
        edu = request.form.get('edu', '').strip()
        exper = request.form.get('exper', '').strip()
        if not skills:
            return render_template('advice.html', match_error='请至少输入一个技能关键词',
                                   match_skills=skills, match_city=city,
                                   match_edu=edu, match_exper=exper, active_tab='match')
        try:
            from agent.agent_tools import match_jobs
            match_result = match_jobs(skills=skills, city=city, edu=edu, exper=exper)
        except Exception:
            return render_template('advice.html', match_error='匹配查询失败,请稍后重试',
                                   match_skills=skills, match_city=city,
                                   match_edu=edu, match_exper=exper, active_tab='match')

        # 保存匹配结果到 session
        session['match_state'] = {
            'result': match_result,
            'skills': skills,
            'city': city,
            'edu': edu,
            'exper': exper,
        }

        return render_template('advice.html', match_result=match_result,
                               match_skills=skills, match_city=city,
                               match_edu=edu, match_exper=exper, active_tab='match')

    # --- 简历审查与优化工具 ---
    if tool == 'review':
        resume_text = request.form.get('resume_text', '').strip()
        target_city = request.form.get('target_city', '').strip()
        target_category = request.form.get('target_category', '').strip()

        # 如果上传了文件，优先从文件提取文本
        uploaded_name = ''
        if 'resume_file' in request.files:
            file = request.files['resume_file']
            if file.filename:
                uploaded_name = file.filename
                try:
                    from agent.resume_parser import extract_text
                    file_bytes = file.read()
                    extracted = extract_text(file_bytes, file.filename)
                    if extracted:
                        resume_text = extracted.strip()
                except Exception:
                    _logger.warning('文件解析失败, 回退到手动输入')

        if not resume_text:
            hint = f'请粘贴简历文本或上传PDF/Word文件'
            if uploaded_name:
                hint = f'无法从 "{uploaded_name}" 提取文本(请确认文件非空或尝试粘贴文本)'
            return render_template('advice.html', review_error=hint,
                                   review_text='', review_city=target_city,
                                   review_category=target_category, active_tab='review')
        try:
            from agent.agent_tools import review_resume
            review_result = review_resume(resume_text, target_city=target_city,
                                          target_category=target_category)
        except Exception:
            return render_template('advice.html', review_error='简历分析失败,请稍后重试',
                                   review_text=resume_text, review_city=target_city,
                                   review_category=target_category, active_tab='review')

        session['review_state'] = {
            'result': review_result,
            'text': resume_text,
            'city': target_city,
            'category': target_category,
        }

        return render_template('advice.html', review_result=review_result,
                               review_text=resume_text, review_city=target_city,
                               review_category=target_category, active_tab='review')

    # 未知工具类型，回退到 Agent
    return render_template('advice.html', error='未知工具类型', active_tab='agent')


# --- 模板全局变量注入 ------------------------------------------------------------
@app.context_processor
def inject_globals():
    """向所有模板注入全局变量,避免每个路由手动传参。"""
    return {'collect_token_required': bool(config.COLLECT_TOKEN)}


if __name__ == '__main__':
    # --- 启动配置 ---------------------------------------------------------------
    # debug 默认关闭，避免 Flask 强制开启 reloader（reloader fork 子进程后，
    # 父进程的 print 输出丢失，且子进程启动失败时伪装为"正常退出"→ERR_CONNECTION_REFUSED）。
    # 如需热更新: 在项目根目录 touch 一个 .debug 文件即可（不建议日常使用）。
    # 局域网访问: $env:FLASK_HOST="0.0.0.0"
    _debug_flag = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.debug')
    debug = os.path.exists(_debug_flag)
    if debug:
        print("[WARN] 检测到 .debug 文件，已启用 debug 模式（含 reloader）", flush=True)
    host = os.environ.get('FLASK_HOST', '127.0.0.1')

    # SO_REUSEADDR: 允许端口立即重用，避免 Windows 上重启 Flask 时
    # 因 TIME_WAIT 导致 "Address already in use" 需要手动杀进程
    import socketserver
    socketserver.TCPServer.allow_reuse_address = True

    # threaded=True: 允许并发处理请求,避免/collect 阻塞其他页面浏览
    port = 5000
    print(f"\n  -> 本地访问: http://127.0.0.1:{port}", flush=True)
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.254.254.254', 1))
        lan_ip = s.getsockname()[0]
        s.close()
        print(f"  -> 局域网访问: http://{lan_ip}:{port}    (同局域网设备可用)\n", flush=True)
    except Exception:
        print(flush=True)
    app.run(debug=debug, host=host, port=port, threaded=True, use_reloader=debug)
