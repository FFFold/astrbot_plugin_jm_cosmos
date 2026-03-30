"""
邮件发送器测试
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestJMEmailSenderConfig:
    """SMTP 配置检查测试"""

    def test_validate_config_disabled(self, config_manager):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager)
        success, message = sender.validate_config()

        assert success is False
        assert "未启用" in message

    def test_validate_config_success(self, config_manager_with_admin):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        success, message = sender.validate_config()

        assert success is True
        assert message == ""

    def test_validate_config_invalid_port(self, config_manager_with_admin):
        from core.mailer import JMEmailSender

        config_manager_with_admin.plugin_config["smtp_port"] = 0
        sender = JMEmailSender(config_manager_with_admin)

        success, message = sender.validate_config()

        assert success is False
        assert "SMTP 端口必须大于 0" in message

    def test_validate_config_ssl_tls_conflict(self, config_manager_with_admin):
        from core.mailer import JMEmailSender

        config_manager_with_admin.plugin_config["smtp_use_ssl"] = True
        config_manager_with_admin.plugin_config["smtp_use_tls"] = True
        sender = JMEmailSender(config_manager_with_admin)

        success, message = sender.validate_config()

        assert success is False
        assert "SSL" in message and "STARTTLS" in message

    def test_validate_config_missing_required_fields(self, config_manager_with_admin):
        from core.mailer import JMEmailSender

        config_manager_with_admin.plugin_config["smtp_host"] = ""
        config_manager_with_admin.plugin_config["smtp_password"] = ""
        sender = JMEmailSender(config_manager_with_admin)

        success, message = sender.validate_config()

        assert success is False
        assert "缺少" in message
        assert "smtp_host" in message
        assert "smtp_password" in message


class TestJMEmailSenderAttachment:
    """附件检查测试"""

    def test_validate_attachment_missing(self, config_manager_with_admin):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        success, message = sender.validate_attachment(Path("missing.zip"))

        assert success is False
        assert "不存在" in message

    def test_validate_attachment_too_large(self, config_manager_with_admin, temp_dir):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "large.zip"
        file_path.write_bytes(b"x" * 16 * 1024 * 1024)
        sender.config.plugin_config["email_max_attachment_mb"] = 10

        success, message = sender.validate_attachment(file_path)

        assert success is False
        assert "附件过大" in message

    def test_validate_attachment_success_under_limit(
        self, config_manager_with_admin, temp_dir
    ):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "small.zip"
        file_path.write_bytes(b"x" * 1024 * 1024)
        sender.config.plugin_config["email_max_attachment_mb"] = 10

        success, message = sender.validate_attachment(file_path)

        assert success is True
        assert message == ""

    def test_validate_attachment_limit_disabled(
        self, config_manager_with_admin, temp_dir
    ):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "anysize.zip"
        file_path.write_bytes(b"x" * 16 * 1024 * 1024)
        sender.config.plugin_config["email_max_attachment_mb"] = 0

        success, message = sender.validate_attachment(file_path)

        assert success is True
        assert message == ""


class TestJMEmailSenderSend:
    """邮件发送测试"""

    def test_send_file_sync_success(self, config_manager_with_admin, temp_dir):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "demo.zip"
        file_path.write_bytes(b"demo")

        smtp_instance = MagicMock()
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp_instance
        smtp_context.__exit__.return_value = None
        smtp_instance.send_message.return_value = {}

        with patch("core.mailer.smtplib.SMTP_SSL", return_value=smtp_context):
            result = sender._send_file_sync(
                ["user@example.com", "other@example.com"],
                file_path,
                "subject",
                "body",
            )

        assert result.success is True
        assert result.recipient == "user@example.com, other@example.com"
        assert result.message_id is not None
        smtp_instance.login.assert_called_once()
        smtp_instance.send_message.assert_called_once()
        sent_message = smtp_instance.send_message.call_args.args[0]
        assert sent_message["To"] == "user@example.com, other@example.com"

    def test_send_file_sync_failure(self, config_manager_with_admin, temp_dir):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "demo.zip"
        file_path.write_bytes(b"demo")

        with patch(
            "core.mailer.smtplib.SMTP_SSL",
            side_effect=RuntimeError("smtp failed"),
        ):
            result = sender._send_file_sync(
                ["user@example.com", "other@example.com"],
                file_path,
                "subject",
                "body",
            )

        assert result.success is False
        assert "smtp failed" in result.error_message
        assert result.message_id is None or result.message_id.startswith("<")

    def test_send_file_sync_starttls_success(self, config_manager_with_admin, temp_dir):
        from core.mailer import JMEmailSender

        config_manager_with_admin.plugin_config["smtp_use_ssl"] = False
        config_manager_with_admin.plugin_config["smtp_use_tls"] = True
        config_manager_with_admin.plugin_config["smtp_port"] = 587
        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "demo.zip"
        file_path.write_bytes(b"demo")

        smtp_instance = MagicMock()
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp_instance
        smtp_context.__exit__.return_value = None
        smtp_instance.send_message.return_value = {}

        with patch("core.mailer.smtplib.SMTP", return_value=smtp_context):
            result = sender._send_file_sync(
                ["user@example.com", "other@example.com"],
                file_path,
                "subject",
                "body",
            )

        assert result.success is True
        assert result.message_id is not None
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once()
        smtp_instance.send_message.assert_called_once()

    def test_send_file_sync_partial_recipient_failure(
        self, config_manager_with_admin, temp_dir
    ):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "demo.zip"
        file_path.write_bytes(b"demo")

        smtp_instance = MagicMock()
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp_instance
        smtp_context.__exit__.return_value = None
        smtp_instance.send_message.return_value = {
            "user@example.com": (550, b"mailbox unavailable")
        }

        with patch("core.mailer.smtplib.SMTP_SSL", return_value=smtp_context):
            result = sender._send_file_sync(
                ["user@example.com", "other@example.com"],
                file_path,
                "subject",
                "body",
            )

        assert result.success is False
        assert "部分收件人发送失败" in result.error_message
        assert result.message_id is not None

    @pytest.mark.asyncio
    async def test_send_file_config_validation_fails(
        self, config_manager_with_admin, temp_dir
    ):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "demo.zip"
        file_path.write_bytes(b"demo")
        sender.validate_config = MagicMock(return_value=(False, "配置错误"))
        sender.validate_attachment = MagicMock()
        sender._run_sync = AsyncMock()

        result = await sender.send_file(
            ["user@example.com", "other@example.com"],
            file_path,
            "subject",
            "body",
        )

        assert result.success is False
        assert result.error_message == "配置错误"
        assert result.recipient == "user@example.com, other@example.com"
        sender._run_sync.assert_not_awaited()
        sender.validate_attachment.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_file_attachment_validation_fails(
        self, config_manager_with_admin, temp_dir
    ):
        from core.mailer import JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "demo.zip"
        file_path.write_bytes(b"demo")
        sender.validate_config = MagicMock(return_value=(True, ""))
        sender.validate_attachment = MagicMock(return_value=(False, "附件错误"))
        sender._run_sync = AsyncMock()

        result = await sender.send_file(
            ["user@example.com", "other@example.com"],
            file_path,
            "subject",
            "body",
        )

        assert result.success is False
        assert result.error_message == "附件错误"
        assert result.recipient == "user@example.com, other@example.com"
        sender._run_sync.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_file_success_uses_run_sync(
        self, config_manager_with_admin, temp_dir
    ):
        from core.mailer import EmailSendResult, JMEmailSender

        sender = JMEmailSender(config_manager_with_admin)
        file_path = temp_dir / "demo.zip"
        file_path.write_bytes(b"demo")
        sender.validate_config = MagicMock(return_value=(True, ""))
        sender.validate_attachment = MagicMock(return_value=(True, ""))
        expected = EmailSendResult(
            True,
            "user@example.com, other@example.com",
            message_id="<id>",
        )

        async def fake_run_sync(func, *args):
            assert func == sender._send_file_sync
            assert args == (
                ["user@example.com", "other@example.com"],
                file_path,
                "subject",
                "body",
            )
            return expected

        sender._run_sync = AsyncMock(side_effect=fake_run_sync)

        result = await sender.send_file(
            ["user@example.com", "other@example.com"],
            file_path,
            "subject",
            "body",
        )

        assert result is expected
        sender._run_sync.assert_awaited_once()
        sender.validate_config.assert_called_once()
        sender.validate_attachment.assert_called_once_with(file_path)
