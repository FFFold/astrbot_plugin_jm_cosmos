"""
JMComic 邮件发送模块

提供 SMTP 附件发送能力，用于将下载后的加密文件发送到邮箱。
"""

import mimetypes
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from astrbot.api import logger

from .base import JMClientMixin, JMConfigManager


@dataclass
class EmailSendResult:
    """邮件发送结果"""

    success: bool
    recipient: str
    error_message: str | None = None
    message_id: str | None = None


class JMEmailSender(JMClientMixin):
    """SMTP 邮件发送器"""

    def __init__(self, config_manager: JMConfigManager):
        self.config = config_manager

    def validate_config(self) -> tuple[bool, str]:
        """检查 SMTP 配置是否完整可用"""
        if not self.config.smtp_enabled:
            return False, "未启用 SMTP 邮件发送，请先在插件配置中开启"

        required_fields = {
            "smtp_host": self.config.smtp_host,
            "smtp_username": self.config.smtp_username,
            "smtp_password": self.config.smtp_password,
            "smtp_from_email": self.config.smtp_from_email,
        }
        missing_fields = [name for name, value in required_fields.items() if not value]
        if missing_fields:
            return False, f"SMTP 配置不完整，缺少: {', '.join(missing_fields)}"

        if self.config.smtp_port <= 0:
            return False, "SMTP 端口必须大于 0"

        if self.config.smtp_use_ssl and self.config.smtp_use_tls:
            return False, "SMTP SSL 与 STARTTLS 不能同时启用"

        return True, ""

    def validate_attachment(self, file_path: Path) -> tuple[bool, str]:
        """检查附件是否可发送"""
        if not file_path.exists() or not file_path.is_file():
            return False, "附件文件不存在"

        limit_mb = self.config.email_max_attachment_mb
        if limit_mb <= 0:
            return True, ""

        file_size = file_path.stat().st_size
        limit_bytes = limit_mb * 1024 * 1024
        if file_size > limit_bytes:
            current_mb = file_size / 1024 / 1024
            return (
                False,
                f"附件过大 ({current_mb:.1f}MB)，超过邮箱限制 {limit_mb}MB",
            )

        return True, ""

    async def send_file(
        self,
        recipient: str,
        file_path: Path,
        subject: str,
        body: str,
    ) -> EmailSendResult:
        """异步发送附件邮件"""
        ok, message = self.validate_config()
        if not ok:
            return EmailSendResult(False, recipient, message)

        ok, message = self.validate_attachment(file_path)
        if not ok:
            return EmailSendResult(False, recipient, message)

        try:
            return await self._run_sync(
                self._send_file_sync,
                recipient,
                file_path,
                subject,
                body,
            )
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return EmailSendResult(False, recipient, str(e))

    def _send_file_sync(
        self,
        recipient: str,
        file_path: Path,
        subject: str,
        body: str,
    ) -> EmailSendResult:
        """同步发送附件邮件"""
        try:
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = (
                f"{self.config.smtp_from_name} <{self.config.smtp_from_email}>"
                if self.config.smtp_from_name
                else self.config.smtp_from_email
            )
            message["To"] = recipient
            message.set_content(body)

            mime_type, _ = mimetypes.guess_type(file_path.name)
            if mime_type is None:
                maintype, subtype = "application", "octet-stream"
            else:
                maintype, subtype = mime_type.split("/", 1)

            with open(file_path, "rb") as f:
                message.add_attachment(
                    f.read(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=file_path.name,
                )

            timeout = self.config.email_send_timeout
            if self.config.smtp_use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    timeout=timeout,
                    context=context,
                ) as server:
                    server.login(self.config.smtp_username, self.config.smtp_password)
                    response = server.send_message(message)
            else:
                with smtplib.SMTP(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    timeout=timeout,
                ) as server:
                    if self.config.smtp_use_tls:
                        server.starttls(context=ssl.create_default_context())
                    server.login(self.config.smtp_username, self.config.smtp_password)
                    response = server.send_message(message)

            if response:
                return EmailSendResult(
                    False, recipient, f"部分收件人发送失败: {response}"
                )

            logger.info(f"邮件发送成功: {recipient} <- {file_path.name}")
            return EmailSendResult(True, recipient)

        except Exception as e:
            logger.error(f"SMTP 发送失败 ({recipient}): {e}")
            return EmailSendResult(False, recipient, str(e))
