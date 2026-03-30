"""
邮件发送器测试
"""

from pathlib import Path
from unittest.mock import MagicMock, patch


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
                "user@example.com",
                file_path,
                "subject",
                "body",
            )

        assert result.success is True
        assert result.recipient == "user@example.com"
        smtp_instance.login.assert_called_once()
        smtp_instance.send_message.assert_called_once()

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
                "user@example.com",
                file_path,
                "subject",
                "body",
            )

        assert result.success is False
        assert "smtp failed" in result.error_message
