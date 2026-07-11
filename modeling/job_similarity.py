"""
岗位相似度网络 — 基于聚类中心向量的余弦相似度，展示各方向之间的关联。

用于回答：当前方向附近有什么相近方向可以转型？

依赖 run_clustering() 的输出（TF-IDF 向量 + KMeans 聚类）。
若聚类未训练则返回空。
"""
import numpy as np


def _cosine_similarity(v1, v2):
    """计算两个向量的余弦相似度。"""
    dot = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot / (norm1 * norm2))


def compute_similarity_network(clustering):
    """从聚类结果计算方向间的相似度网络。

    Args:
        clustering: run_clustering() 返回的 dict，
                   必须包含 'clusters' 列表，每个元素有 'top_keywords'。

    Returns:
        dict: {
            nodes: [{name: str, size: int, avg_salary: float}],
            links: [{source: str, target: str, value: float}],
            cluster_count: int,
        }
        或 {'error': str} — 数据不足
    """
    if not clustering or clustering.get('k', 0) < 2:
        return {'error': '聚类数不足（需 ≥2 个方向），无法计算相似度网络'}

    clusters = clustering.get('clusters', [])
    if len(clusters) < 2:
        return {'error': '聚类数不足（需 ≥2 个方向），无法计算相似度网络'}

    # 构建每个簇的标签向量（基于关键词集合）
    all_keywords = set()
    cluster_kw_sets = []
    for c in clusters:
        kws = set(c.get('top_keywords', [])[:5])  # 用前5个关键词
        cluster_kw_sets.append(kws)
        all_keywords.update(kws)

    if len(all_keywords) < 2:
        return {'error': '聚类关键词过少，无法计算有意义相似度'}

    kw_list = sorted(all_keywords)
    kw_index = {kw: i for i, kw in enumerate(kw_list)}

    # 构建每个簇的二元组词向量
    vectors = []
    for kws in cluster_kw_sets:
        vec = np.zeros(len(kw_list))
        for kw in kws:
            if kw in kw_index:
                vec[kw_index[kw]] = 1
        vectors.append(vec)

    # 计算成对余弦相似度
    nodes = []
    for c in clusters:
        nodes.append({
            'name': c.get('auto_label', f'方向{c.get("cluster_id", "")}'),
            'size': c.get('count', 0),
            'avg_salary': c.get('avg_salary', 0),
            'cluster_id': c.get('cluster_id', 0),
        })

    links = []
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            sim = _cosine_similarity(vectors[i], vectors[j])
            if sim > 0.05:  # 过滤极低相似度
                links.append({
                    'source': nodes[i]['name'],
                    'target': nodes[j]['name'],
                    'value': round(sim, 3),
                })

    return {
        'nodes': nodes,
        'links': links,
        'cluster_count': len(clusters),
    }


if __name__ == '__main__':
    import json
    from modeling import job_clustering
    cl = job_clustering.run_clustering()
    result = compute_similarity_network(cl)
    print(json.dumps(result, ensure_ascii=False, indent=2))
