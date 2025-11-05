import base64
import logging
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from spaceone.core.connector import BaseConnector
from spaceone.identity.error.error_smtp import *

_LOGGER = logging.getLogger(__name__)

__all__ = ["SMTPConnector"]


class SMTPConnector(BaseConnector, ABC):
    name = "SMTPConnector"
    provider_type = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.smtp = None
        self.from_email = self.config.get("from_email")
        self.host = self.config.get("host")
        self.port = self.config.get("port", 587)

        print(self.config)

        if not self.from_email:
            raise ERROR_SMTP_CONNECTION_FAILED(error="from_email is required")

    def __enter__(self):
        """Context manager: enter"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: automatically close SMTP connection on exit"""
        self.quit_smtp()
        return False

    @classmethod
    def get_connector_by_provider(cls, provider_type: str):
        provider_type = provider_type.lower()

        for subclass in cls.__subclasses__():
            if subclass.provider_type == provider_type:
                return subclass()

        _LOGGER.error(f"Unknown SMTP provider: {provider_type}")
        raise ERROR_SMTP_CONNECTION_FAILED(
            error=f"Unknown SMTP provider: {provider_type}. "
            f"Supported providers: gmail, microsoft, basic"
        )

    def connect(self):
        try:
            _LOGGER.info(
                f"[{self.provider_type}] Connecting to {self.host}:{self.port}"
            )

            # SMTP 서버 연결
            self.smtp = smtplib.SMTP(self.host, self.port)

            # TLS 설정
            self.smtp.ehlo()
            use_tls = getattr(self, "use_tls", True)
            if use_tls:
                self.smtp.starttls()
                self.smtp.ehlo()

            self._authenticate()

            _LOGGER.info(
                f"[{self.provider_type}] Successfully connected "
                f"({self.host}:{self.port}, from: {self.from_email})"
            )

        except Exception as e:
            _LOGGER.error(f"[{self.provider_type}] Connection failed: {e}")
            raise ERROR_SMTP_CONNECTION_FAILED(
                error=f"{self.provider_type} SMTP connection failed: {e}"
            )

    @abstractmethod
    def _authenticate(self):
        pass

    def send_email(self, to_emails: str, subject: str, contents: str):
        # Lazy Connection
        self.connect()

        try:
            recipient_list = [email.strip() for email in to_emails.split(",")]

            multipart_msg = MIMEMultipart("alternative")
            multipart_msg["Subject"] = subject
            multipart_msg["From"] = self.from_email
            multipart_msg["To"] = ", ".join(recipient_list)
            multipart_msg.attach(MIMEText(contents, "html"))

            response = self.smtp.sendmail(
                self.from_email, recipient_list, multipart_msg.as_string()
            )

            if response:
                _LOGGER.debug(f"[send_email] response: {response}")

        except smtplib.SMTPException as e:
            _LOGGER.error(f"[send_email] Failed to send email: {e}")
            raise ERROR_SMTP_SEND_EMAIL_FAILED(message=f"Failed to send email: {e}")

    def quit_smtp(self):
        if self.smtp:
            try:
                self.smtp.quit()
                _LOGGER.debug(f"[{self.provider_type}] SMTP connection closed")
                self.smtp = None
            except Exception as e:
                _LOGGER.warning(f"[{self.provider_type}] Error closing connection: {e}")

    @staticmethod
    def generate_oauth2_string(user: str, access_token: str) -> str:
        """Generate OAuth2.0 authentication string

        Args:
            user: user email
            access_token: OAuth2.0 access token

        Returns:
            Base64 encoded OAuth2.0 authentication string
        """
        auth_string = f"user={user}\1auth=Bearer {access_token}\1\1"
        return base64.b64encode(auth_string.encode()).decode()
