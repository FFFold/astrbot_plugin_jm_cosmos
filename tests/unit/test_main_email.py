"""邮件命令流程测试"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = PLUGIN_ROOT / "main.py"
MAIN_MODULE_NAME = "astrbot_plugin_jm_cosmos.main"

if MAIN_MODULE_NAME in sys.modules:
    main_module = sys.modules[MAIN_MODULE_NAME]
else:
    spec = importlib.util.spec_from_file_location(MAIN_MODULE_NAME, MAIN_PATH)
    main_module = importlib.util.module_from_spec(spec)
    sys.modules[MAIN_MODULE_NAME] = main_module
    assert spec.loader is not None
    spec.loader.exec_module(main_module)

JMCosmosPlugin = main_module.JMCosmosPlugin


class FakeEvent:
    """简化的事件对象"""

    def __init__(self, user_id: str = "10001", group_id: str | None = None):
        self.user_id = user_id
        self.group_id = group_id

    def get_sender_id(self) -> str:
        return self.user_id

    def get_group_id(self) -> str | None:
        return self.group_id

    def plain_result(self, message: str) -> str:
        return message


def build_plugin(pack_format: str = "zip") -> JMCosmosPlugin:
    """构造最小可测试插件实例"""
    plugin = JMCosmosPlugin.__new__(JMCosmosPlugin)
    plugin.config_manager = SimpleNamespace(
        pack_format=pack_format,
        email_subject_template="[JM] {title}",
        email_body_template="标题: {title}",
        auto_delete_after_send=True,
    )
    plugin.email_sender = MagicMock()
    plugin.email_sender.validate_config.return_value = (True, "")
    plugin.quota_manager = MagicMock()
    plugin.debug_mode = False
    plugin._check_permission = MagicMock(return_value=(True, ""))
    plugin._check_download_quota = MagicMock(return_value=(True, "", 3))
    plugin._cleanup_download_files = MagicMock()
    plugin._send_cover_preview_if_needed = AsyncMock(return_value=None)
    return plugin


def test_parse_recipient_emails_supports_multiple_delimiters_and_dedup():
    """应支持中英文逗号、空格并自动去重"""
    plugin = build_plugin()

    recipients, error = plugin._parse_recipient_emails(
        "a@example.com， b@example.com, a@example.com ,, c@example.com"
    )

    assert error == ""
    assert recipients == [
        "a@example.com",
        "b@example.com",
        "c@example.com",
    ]


def test_parse_recipient_emails_rejects_invalid_email():
    """存在非法邮箱时应返回具体错误"""
    plugin = build_plugin()

    recipients, error = plugin._parse_recipient_emails("a@example.com, bad-email")

    assert recipients == []
    assert error == "❌ 邮箱格式无效: bad-email"


def test_parse_recipient_emails_rejects_empty_input():
    """空邮箱参数应返回明确提示"""
    plugin = build_plugin()

    recipients, error = plugin._parse_recipient_emails("， ,  ")

    assert recipients == []
    assert error == "❌ 请提供至少一个有效邮箱地址"


def build_download_result():
    """构造下载结果"""
    return SimpleNamespace(
        success=True,
        album_id="123456",
        title="测试本子",
        author="测试作者",
        photo_count=3,
        image_count=25,
        save_path=Path("downloads/123456"),
    )


def build_pack_result():
    """构造打包结果"""
    return SimpleNamespace(
        success=True,
        output_path=Path("downloads/123456.zip"),
        format="zip",
        encrypted=False,
        error_message=None,
    )


@pytest.mark.asyncio
async def test_jmemail_checks_delivery_preconditions_before_download():
    """邮件命令应在下载前检查前置条件"""
    plugin = build_plugin(pack_format="none")
    plugin._prepare_album_download = AsyncMock(
        side_effect=AssertionError("should not run")
    )

    results = [
        item
        async for item in plugin.download_album_email_command(
            FakeEvent(),
            "123456",
            "user@example.com",
        )
    ]

    assert plugin._prepare_album_download.await_count == 0
    assert results == ["❌ 当前打包格式为 none，邮件命令仅支持 zip 或 pdf"]


@pytest.mark.asyncio
async def test_jmemail_rejects_invalid_email_before_download():
    """邮箱格式无效时不应开始下载"""
    plugin = build_plugin()
    plugin._prepare_album_download = AsyncMock(
        side_effect=AssertionError("should not run")
    )

    results = [
        item
        async for item in plugin.download_album_email_command(
            FakeEvent(),
            "123456",
            "not-an-email",
        )
    ]

    assert results == ["❌ 邮箱格式无效: not-an-email"]
    assert plugin._prepare_album_download.await_count == 0


@pytest.mark.asyncio
async def test_jmemail_accepts_multiple_emails_with_cn_comma_and_spaces():
    """应支持多个邮箱、中文逗号和空格"""
    plugin = build_plugin()
    result = build_download_result()
    pack_result = build_pack_result()
    plugin._prepare_album_download = AsyncMock(return_value=(result, pack_result))
    plugin._send_file_to_email = AsyncMock(return_value=(True, "发送成功"))

    results = [
        item
        async for item in plugin.download_album_email_command(
            FakeEvent(),
            "123456",
            "a@example.com， b@example.com",
        )
    ]

    plugin._send_file_to_email.assert_awaited_once_with(
        result,
        pack_result,
        ["a@example.com", "b@example.com"],
    )
    assert "a@example.com, b@example.com" in results[0]


@pytest.mark.asyncio
async def test_jmemail_ignores_empty_items_and_deduplicates_recipients():
    """空项应忽略，重复邮箱应去重"""
    plugin = build_plugin()
    result = build_download_result()
    pack_result = build_pack_result()
    plugin._prepare_album_download = AsyncMock(return_value=(result, pack_result))
    plugin._send_file_to_email = AsyncMock(return_value=(True, "发送成功"))

    async for _ in plugin.download_album_email_command(
        FakeEvent(),
        "123456",
        "a@example.com,,a@example.com,b@example.com",
    ):
        pass

    plugin._send_file_to_email.assert_awaited_once_with(
        result,
        pack_result,
        ["a@example.com", "b@example.com"],
    )


@pytest.mark.asyncio
async def test_jmemail_stops_when_quota_check_fails():
    """配额不足时不应开始下载"""
    plugin = build_plugin()
    plugin._check_download_quota = MagicMock(return_value=(False, "额度不足", 3))
    plugin._prepare_album_download = AsyncMock(
        side_effect=AssertionError("should not run")
    )

    results = [
        item
        async for item in plugin.download_album_email_command(
            FakeEvent(),
            "123456",
            "user@example.com",
        )
    ]

    assert results == ["额度不足"]
    assert plugin._prepare_album_download.await_count == 0


@pytest.mark.asyncio
async def test_jmemail_does_not_consume_quota_when_send_fails():
    """邮件发送失败时不应消耗配额"""
    plugin = build_plugin()
    plugin._prepare_album_download = AsyncMock(
        return_value=(build_download_result(), build_pack_result())
    )
    plugin._send_file_to_email = AsyncMock(return_value=(False, "SMTP 连接失败"))

    results = [
        item
        async for item in plugin.download_album_email_command(
            FakeEvent(),
            "123456",
            "user@example.com",
        )
    ]

    assert plugin.quota_manager.consume_quota.call_count == 0
    assert plugin._cleanup_download_files.call_count == 0
    assert any("邮件发送失败" in item for item in results)


@pytest.mark.asyncio
async def test_jmemail_reuses_cover_preview_flow():
    """jmemail 应与 jm 一样先发送封面/详情预览"""
    plugin = build_plugin()
    event = FakeEvent()
    plugin._prepare_album_download = AsyncMock(
        return_value=(build_download_result(), build_pack_result())
    )
    plugin._send_file_to_email = AsyncMock(return_value=(True, "发送成功"))
    plugin._send_cover_preview_if_needed = AsyncMock(return_value="预览消息")

    results = [
        item
        async for item in plugin.download_album_email_command(
            event,
            "123456",
            "user@example.com",
        )
    ]

    plugin._send_cover_preview_if_needed.assert_awaited_once_with(event, "123456")
    assert results[1] == "预览消息"


@pytest.mark.asyncio
async def test_jmcemail_matches_jmc_progress_messages():
    """jmcemail 应与 jmc 一样先提示章节解析结果"""
    plugin = build_plugin()
    plugin._prepare_photo_download = AsyncMock(
        return_value=(
            build_download_result(),
            build_pack_result(),
            ("第3话", 12),
        )
    )
    plugin._send_file_to_email = AsyncMock(return_value=(True, "发送成功"))

    results = [
        item
        async for item in plugin.download_photo_email_command(
            FakeEvent(),
            "123456",
            "3",
            "user@example.com",
        )
    ]

    assert results[0] == "⏳ 正在获取本子 123456 的第 3 章节信息..."
    assert results[1] == (
        "📖 找到章节: 第3话\n📚 章节: 3/12\n📮 开始下载并发送到邮箱 user@example.com..."
    )
    assert results[-1] == "发送成功"


@pytest.mark.asyncio
async def test_jmcemail_accepts_multiple_emails():
    """jmcemail 应支持多个收件邮箱"""
    plugin = build_plugin()
    result = build_download_result()
    pack_result = build_pack_result()
    plugin._prepare_photo_download = AsyncMock(
        return_value=(result, pack_result, ("第3话", 12))
    )
    plugin._send_file_to_email = AsyncMock(return_value=(True, "发送成功"))

    results = [
        item
        async for item in plugin.download_photo_email_command(
            FakeEvent(),
            "123456",
            "3",
            "a@example.com,b@example.com",
        )
    ]

    plugin._send_file_to_email.assert_awaited_once_with(
        result,
        pack_result,
        ["a@example.com", "b@example.com"],
    )
    assert "a@example.com, b@example.com" in results[1]


@pytest.mark.asyncio
async def test_jmemail_consumes_quota_after_send_success():
    """邮件发送成功后才消耗配额并清理文件"""
    plugin = build_plugin()
    result = build_download_result()
    pack_result = build_pack_result()
    plugin._prepare_album_download = AsyncMock(return_value=(result, pack_result))
    plugin._send_file_to_email = AsyncMock(return_value=(True, "发送成功"))

    results = [
        item
        async for item in plugin.download_album_email_command(
            FakeEvent(),
            "123456",
            "user@example.com",
        )
    ]

    plugin.quota_manager.consume_quota.assert_called_once_with("10001")
    plugin._cleanup_download_files.assert_called_once_with(result, pack_result)
    assert results[-1] == "发送成功"


@pytest.mark.asyncio
async def test_jmemail_download_failure_skips_quota_and_cleanup():
    """下载失败时不应扣配额或清理文件"""
    plugin = build_plugin()
    failed_result = SimpleNamespace(
        success=False,
        error_message="下载失败",
    )
    plugin._prepare_album_download = AsyncMock(return_value=(failed_result, None))

    results = [
        item
        async for item in plugin.download_album_email_command(
            FakeEvent(),
            "123456",
            "user@example.com",
        )
    ]

    assert any("下载失败" in item for item in results)
    assert plugin.quota_manager.consume_quota.call_count == 0
    assert plugin._cleanup_download_files.call_count == 0


@pytest.mark.asyncio
async def test_jmcemail_returns_not_found_message_when_chapter_missing():
    """章节不存在时应返回与 jmc 一致的错误信息"""
    plugin = build_plugin()
    plugin._prepare_photo_download = AsyncMock(return_value=(None, None, None))

    results = [
        item
        async for item in plugin.download_photo_email_command(
            FakeEvent(),
            "123456",
            "3",
            "user@example.com",
        )
    ]

    assert results[1] == (
        "❌ 无法获取章节信息\n可能的原因:\n• 本子 123456 不存在\n• 第 3 章节不存在"
    )


@pytest.mark.asyncio
async def test_jmcemail_download_failure_skips_quota_and_cleanup():
    """章节下载失败时不应扣配额或清理文件"""
    plugin = build_plugin()
    failed_result = SimpleNamespace(success=False, error_message="章节下载失败")
    plugin._prepare_photo_download = AsyncMock(
        return_value=(failed_result, None, ("第3话", 12))
    )

    results = [
        item
        async for item in plugin.download_photo_email_command(
            FakeEvent(),
            "123456",
            "3",
            "user@example.com",
        )
    ]

    assert any("章节下载失败" in item for item in results)
    assert plugin.quota_manager.consume_quota.call_count == 0
    assert plugin._cleanup_download_files.call_count == 0


@pytest.mark.asyncio
async def test_send_file_to_email_handles_invalid_template_format():
    """非法邮件模板应返回明确错误"""
    plugin = build_plugin()
    plugin.config_manager.email_subject_template = "[JM] {title"
    plugin.email_sender.send_file = AsyncMock()

    success, message = await plugin._send_file_to_email(
        build_download_result(),
        build_pack_result(),
        ["user@example.com"],
    )

    assert success is False
    assert "邮件模板格式无效" in message
    assert plugin.email_sender.send_file.await_count == 0


@pytest.mark.asyncio
async def test_send_file_to_email_sends_to_all_recipients():
    """应通过一次发送请求处理所有收件邮箱"""
    plugin = build_plugin()
    plugin.email_sender.send_file = AsyncMock(
        return_value=SimpleNamespace(success=True, error_message=None)
    )

    success, message = await plugin._send_file_to_email(
        build_download_result(),
        build_pack_result(),
        ["a@example.com", "b@example.com"],
    )

    assert success is True
    assert "a@example.com, b@example.com" in message
    plugin.email_sender.send_file.assert_awaited_once_with(
        recipients=["a@example.com", "b@example.com"],
        file_path=build_pack_result().output_path,
        subject="[JM] 测试本子",
        body="标题: 测试本子",
    )


@pytest.mark.asyncio
async def test_send_file_to_email_reports_failure_from_smtp():
    """底层发送失败时应返回错误信息"""
    plugin = build_plugin()
    plugin.email_sender.send_file = AsyncMock(
        return_value=SimpleNamespace(success=False, error_message="SMTP 连接失败")
    )

    success, message = await plugin._send_file_to_email(
        build_download_result(),
        build_pack_result(),
        ["a@example.com", "b@example.com"],
    )

    assert success is False
    assert message == "SMTP 连接失败"
    plugin.email_sender.send_file.assert_awaited_once()
