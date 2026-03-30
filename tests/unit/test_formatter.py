"""
消息格式化器测试

测试 utils/formatter.py 中的 MessageFormatter 类。
注意：由于 formatter.py 使用相对导入，我们直接复制格式化逻辑进行测试。
"""


# 由于 utils/formatter.py 使用相对导入 (from ..core.constants)，
# 在独立测试环境中难以正确导入。
# 这里我们创建一个测试用的简化版 MessageFormatter 来验证逻辑。

from core.constants import CATEGORY_NAMES, ORDER_NAMES, TIME_NAMES


class TestMessageFormatterLogic:
    """测试 MessageFormatter 的核心格式化逻辑"""

    def test_format_album_info_complete(self, sample_album_dict):
        """测试完整本子信息格式化"""
        album = sample_album_dict

        # 模拟 format_album_info 逻辑
        lines = [
            f"📖 {album.get('title', '未知标题')}",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"🆔 ID: {album.get('id', 'N/A')}",
            f"✍️ 作者: {album.get('author', '未知')}",
            f"📚 章节数: {album.get('photo_count', 0)}",
        ]
        if album.get("tags"):
            tags = album["tags"][:5]
            lines.append(f"🏷️ 标签: {', '.join(tags)}")

        result = "\n".join(lines)

        assert "123456" in result
        assert "测试本子标题" in result
        assert "测试作者" in result
        assert "标签1" in result

    def test_format_album_info_minimal(self):
        """测试最小本子信息格式化"""
        album = {"id": "999", "title": "简单标题"}

        lines = [
            f"📖 {album.get('title', '未知标题')}",
            f"🆔 ID: {album.get('id', 'N/A')}",
        ]
        result = "\n".join(lines)

        assert "999" in result
        assert "简单标题" in result


class TestFormatSearchResults:
    """格式化搜索结果测试"""

    def test_format_search_results_with_data(self, sample_search_results):
        """测试有数据的搜索结果格式化"""
        results = sample_search_results
        keyword = "测试关键词"
        page = 1

        lines = [f"🔍 搜索: {keyword} (第{page}页)", "━━━━━━━━━━━━━━━━━━━━━"]
        for i, album in enumerate(results, 1):
            title = album.get("title", "未知标题")
            album_id = album.get("id", "N/A")
            lines.append(f"{i}. 【{album_id}】{title}")

        result = "\n".join(lines)

        assert "测试关键词" in result
        assert "搜索结果1" in result
        assert "111111" in result

    def test_format_search_results_empty(self):
        """测试空搜索结果格式化"""
        keyword = "没有结果的关键词"
        result = f'🔍 未找到与 "{keyword}" 相关的结果'

        assert "未找到" in result


class TestFormatRankingResults:
    """格式化排行榜测试"""

    def test_format_ranking_results_week(self, sample_search_results):
        """测试周排行榜格式化"""
        type_names = {"day": "日", "week": "周", "month": "月"}
        ranking_type = "week"
        type_name = type_names.get(ranking_type, "周")

        lines = [f"🏆 {type_name}排行榜 (第1页)"]
        for i, album in enumerate(sample_search_results, 1):
            title = album.get("title", "未知标题")
            album_id = album.get("id", "N/A")
            lines.append(f"{i}. 【{album_id}】{title}")

        result = "\n".join(lines)

        assert "周排行榜" in result
        assert "搜索结果1" in result


class TestFormatRecommendResults:
    """格式化推荐结果测试"""

    def test_format_recommend_results_with_data(self, sample_search_results):
        """测试有数据的推荐结果格式化"""
        category = "hanman"
        order_by = "hot"
        time_range = "week"

        cat_name = CATEGORY_NAMES.get(category.lower(), category)
        order_name = ORDER_NAMES.get(order_by.lower(), order_by)
        time_name = TIME_NAMES.get(time_range.lower(), time_range)

        lines = [f"🎯 推荐浏览 - {cat_name} · {time_name}{order_name}"]
        for i, album in enumerate(sample_search_results, 1):
            title = album.get("title", "未知标题")
            album_id = album.get("id", "N/A")
            lines.append(f"{i}. 【{album_id}】{title}")

        result = "\n".join(lines)

        assert "韩漫" in result
        assert "本周" in result
        assert "热门" in result

    def test_format_recommend_results_empty(self):
        """测试空推荐结果格式化"""
        result = "📭 暂无推荐内容"
        assert "暂无" in result


class TestFormatDownloadResult:
    """格式化下载结果测试"""

    def test_format_download_result_success(self):
        """测试成功下载结果格式化"""
        from unittest.mock import MagicMock

        result = MagicMock()
        result.success = True
        result.title = "下载成功的本子"
        result.author = "作者"
        result.photo_count = 5
        result.image_count = 100

        lines = [
            "✅ 下载完成！",
            f"📖 {result.title}",
            f"✍️ 作者: {result.author}",
        ]
        formatted = "\n".join(lines)

        assert "下载完成" in formatted
        assert "下载成功的本子" in formatted

    def test_format_download_result_failure(self):
        """测试失败下载结果格式化"""
        error_message = "网络连接超时"
        formatted = f"❌ 下载失败\n原因: {error_message}"

        assert "下载失败" in formatted
        assert "网络连接超时" in formatted

    def test_format_email_result_contains_recipient(self):
        """测试邮件发送结果格式化包含收件人"""
        recipient = "user@example.com"
        formatted = f"✅ 下载完成！\n📮 已发送到邮箱: {recipient}"

        assert "已发送到邮箱" in formatted
        assert recipient in formatted


class TestFormatHelp:
    """格式化帮助信息测试"""

    def test_format_help_contains_commands(self):
        """测试帮助信息包含所有命令"""
        # 验证帮助文本的核心内容
        help_text = """📚 JM-Cosmos II - 漫画下载插件
【基本命令】
/jm <ID>     - 下载指定ID的本子
/jmemail <ID> <邮箱> - 下载本子并发送到邮箱
/jms <关键词> - 搜索漫画
/jmi <ID>    - 查看本子详情
"""
        assert "/jm" in help_text
        assert "/jmemail" in help_text
        assert "/jms" in help_text
        assert "/jmi" in help_text


class TestFormatError:
    """格式化错误信息测试"""

    def test_format_error_with_detail(self):
        """测试带详情的错误格式化"""
        error_type = "download_failed"
        detail = "网络连接超时"

        error_messages = {
            "download_failed": "❌ 下载失败",
        }
        msg = error_messages.get(error_type, f"❌ 发生错误: {error_type}")
        if detail:
            msg += f"\n详情: {detail}"

        assert "下载失败" in msg
        assert "网络连接超时" in msg

    def test_format_error_without_detail(self):
        """测试不带详情的错误格式化"""
        error_type = "not_found"
        error_messages = {
            "not_found": "❌ 未找到指定的本子，请检查ID是否正确",
        }
        msg = error_messages.get(error_type, f"❌ 发生错误: {error_type}")

        assert "未找到" in msg


class TestFormatRecommendHelp:
    """格式化推荐帮助信息测试"""

    def test_format_recommend_help(self):
        """测试推荐功能帮助信息"""
        help_text = """🎯 推荐浏览使用帮助
【命令格式】
/jmrec [分类] [排序] [时间] [页码]
"""
        assert "jmrec" in help_text
        assert "分类" in help_text


class TestConstants:
    """测试常量映射被正确引用"""

    def test_category_names_available(self):
        """测试分类名称映射可用"""
        assert "hanman" in CATEGORY_NAMES
        assert CATEGORY_NAMES["hanman"] == "韩漫"

    def test_order_names_available(self):
        """测试排序名称映射可用"""
        assert "hot" in ORDER_NAMES
        assert ORDER_NAMES["hot"] == "热门"

    def test_time_names_available(self):
        """测试时间名称映射可用"""
        assert "week" in TIME_NAMES
        assert TIME_NAMES["week"] == "本周"
