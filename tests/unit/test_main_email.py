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
    return plugin


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
async def test_send_file_to_email_handles_invalid_template_format():
    """非法邮件模板应返回明确错误"""
    plugin = build_plugin()
    plugin.config_manager.email_subject_template = "[JM] {title"
    plugin.email_sender.send_file = AsyncMock()

    success, message = await plugin._send_file_to_email(
        build_download_result(),
        build_pack_result(),
        "user@example.com",
    )

    assert success is False
    assert "邮件模板格式无效" in message
    assert plugin.email_sender.send_file.await_count == 0
