"""
测试岗位详情功能

测试内容:
1. 访问 /job/<id> 页面（存在的数据）
2. 访问 /job/<id> 页面（不存在的数据）
3. 验证数据列表页面的岗位名称链接是否正确
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app


@pytest.fixture
def client():
    """创建测试客户端"""
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # 测试时禁用 CSRF
    with app.test_client() as client:
        yield client


@pytest.fixture
def sample_job_id(client):
    """获取一个存在的岗位 ID"""
    # 从数据库获取一个有效的岗位 ID
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.execute('SELECT id FROM data LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return None


class TestJobDetailPage:
    """测试岗位详情页面"""

    def test_job_detail_page_exists(self, client, sample_job_id):
        """测试访问存在的岗位详情页返回 200"""
        if sample_job_id is None:
            pytest.skip('数据库中没有测试数据')

        response = client.get(f'/job/{sample_job_id}')
        assert response.status_code == 200

    def test_job_detail_page_not_found(self, client):
        """测试访问不存在的岗位详情页返回 404 或显示错误信息"""
        # 使用一个很大的 ID 确保不存在
        response = client.get('/job/999999')
        assert response.status_code in [200, 404]  # 可能是 404 或在页面显示错误

        if response.status_code == 200:
            # 如果在页面显示错误，应该包含错误信息
            assert b'\xe6\x9c\xaa\xe6\x89\xbe\xe5\x88\xb0' in response.data or b'not found' in response.data.lower()

    def test_job_detail_page_contains_job_info(self, client, sample_job_id):
        """测试岗位详情页包含岗位信息"""
        if sample_job_id is None:
            pytest.skip('数据库中没有测试数据')

        response = client.get(f'/job/{sample_job_id}')
        assert response.status_code == 200

        # 检查页面是否包含关键信息
        # 至少应该包含"职位档案详情"或类似的标题
        assert b'\xe8\x81\x8c\xe4\xbd\x8d\xe6\xa1\xa3\xe6\xa1\x88' in response.data or b'job' in response.data.lower()

    def test_job_detail_page_has_back_button(self, client, sample_job_id):
        """测试岗位详情页包含返回列表的链接"""
        if sample_job_id is None:
            pytest.skip('数据库中没有测试数据')

        response = client.get(f'/job/{sample_job_id}')
        assert response.status_code == 200

        # 检查是否包含返回列表的链接
        assert b'/list' in response.data or b'\xe8\xbf\x94\xe5\x9b\x9e\xe5\x88\x97\xe8\xa1\xa8' in response.data

    def test_job_detail_page_shows_salary(self, client, sample_job_id):
        """测试岗位详情页显示薪资信息"""
        if sample_job_id is None:
            pytest.skip('数据库中没有测试数据')

        response = client.get(f'/job/{sample_job_id}')
        assert response.status_code == 200

        # 检查是否包含薪资相关信息（K 或 千）
        assert b'K' in response.data or b'\xe5\x8d\x83' in response.data


class TestDataListPageLinks:
    """测试数据列表页面的链接"""

    @pytest.mark.usefixtures("temp_db")
    def test_list_page_contains_job_links(self, client):
        """测试数据列表页面包含岗位详情链接(需要库里有数据)。"""
        response = client.get('/list')
        assert response.status_code == 200

        # 检查是否包含 /job/ 的链接
        assert b'/job/' in response.data

    def test_list_page_job_link_format(self, client):
        """测试数据列表页面的岗位链接格式正确"""
        response = client.get('/list')
        assert response.status_code == 200

        # 检查链接格式是否为 /job/数字
        import re
        links = re.findall(rb'/job/(\d+)', response.data)
        if links:
            # 至少有一个链接，且 ID 应该是数字
            job_id = int(links[0].decode())
            assert job_id > 0

    def test_list_page_click_job_link(self, client):
        """测试点击数据列表中的岗位链接能正确跳转到详情页"""
        # 先获取列表页的第一个岗位链接
        response = client.get('/list')
        assert response.status_code == 200

        import re
        links = re.findall(rb'/job/(\d+)', response.data)
        if not links:
            pytest.skip('列表页没有找到岗位链接')

        job_id = int(links[0].decode())

        # 访问该链接
        detail_response = client.get(f'/job/{job_id}')
        assert detail_response.status_code == 200


class TestJobDetailAPI:
    """测试岗位详情的边界情况"""

    def test_job_detail_invalid_id_string(self, client):
        """测试使用字符串 ID 访问详情页（应该 404）"""
        response = client.get('/job/abc')
        assert response.status_code == 404

    def test_job_detail_negative_id(self, client):
        """测试使用负数 ID 访问详情页"""
        response = client.get('/job/-1')
        # Flask 的 <int:id> 转换器会接受负数，但数据库应该没有
        assert response.status_code in [200, 404]

    def test_job_detail_zero_id(self, client):
        """测试使用 0 作为 ID 访问详情页"""
        response = client.get('/job/0')
        # 数据库 ID 通常从 1 开始
        assert response.status_code in [200, 404]
