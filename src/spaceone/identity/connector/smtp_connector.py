import base64
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import msal
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from spaceone.core.connector import BaseConnector
from spaceone.identity.error.error_smtp import *

__all__ = ["SMTPConnector"]

_LOGGER = logging.getLogger(__name__)


class SMTPConnector(BaseConnector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.smtp = None
        self.from_email = None

        # Prepare a list of connection methods (the actual connection will be made later)
        self._connection_methods = []
        if "gmail" in self.config:
            self._connection_methods.append(("gmail", self.config["gmail"]))
        if "microsoft" in self.config:
            self._connection_methods.append(("microsoft", self.config["microsoft"]))
        if "basic" in self.config:
            self._connection_methods.append(("basic", self.config["basic"]))

        if not self._connection_methods:
            raise ERROR_SMTP_CONNECTION_FAILED(
                message="No SMTP configuration found. Please provide at least one of: gmail, microsoft, or basic."
            )

    def _connect(self):
        """
        Fallback mechanism: Try in the order of Gmail -> Microsoft -> Basic.
        """
        if self.smtp is not None:
            return  # Already connected

        errors = []

        # Fallback mechanism: try in order
        for method_name, method_config in self._connection_methods:
            if method_name == "gmail":
                if self._try_gmail(method_config, errors):
                    return
            elif method_name == "microsoft":
                if self._try_microsoft(method_config, errors):
                    return
            elif method_name == "basic":
                if self._try_basic(method_config, errors):
                    return

        # All methods failed
        error_messages = "\n".join(
            [f"  - {method}: {error}" for method, error in errors]
        )
        _LOGGER.error(
            f"[_connect] All SMTP authentication methods failed:\n{error_messages}"
        )
        raise ERROR_SMTP_CONNECTION_FAILED(
            message=f"All SMTP authentication methods failed:\n{error_messages}"
        )

    def __enter__(self):
        """Context manager: enter"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: automatically close SMTP connection on exit"""
        self.quit_smtp()
        return False  # Propagate exceptions

    def _try_gmail(self, gmail_config, errors):
        """Try to connect using Gmail OAuth2.0."""
        try:
            _LOGGER.info("[_try_gmail] Trying Gmail OAuth2.0")

            from_email = gmail_config.get("from_email")
            refresh_token = gmail_config.get("refresh_token")
            client_id = gmail_config.get("client_id")
            client_secret = gmail_config.get("client_secret")
            smtp_host = gmail_config.get("host", "smtp.gmail.com")
            smtp_port = gmail_config.get("port", 587)

            if not from_email:
                raise Exception("from_email is required in gmail config")
            if not refresh_token:
                raise Exception("refresh_token is required in gmail config")
            if not client_id or not client_secret:
                raise Exception(
                    "client_id and client_secret are required in gmail config"
                )

            # Create Gmail OAuth2.0 credentials
            creds = self._get_gmail_credentials(refresh_token, client_id, client_secret)

            # Connect to Gmail SMTP server
            self.smtp = smtplib.SMTP(smtp_host, smtp_port)
            self.smtp.ehlo()
            self.smtp.starttls()
            self.smtp.ehlo()

            # OAuth2.0 authentication
            auth_string = self.generate_oauth2_string(from_email, creds.token)
            self.smtp.docmd("AUTH", "XOAUTH2 " + auth_string)

            self.from_email = from_email
            _LOGGER.info(
                f"[_try_gmail] Successfully connected with Gmail OAuth2.0 ({smtp_host}:{smtp_port}, from: {from_email})"
            )
            return True

        except Exception as e:
            error_msg = str(e)
            errors.append(("Gmail OAuth2.0", error_msg))
            return False

    def _try_microsoft(self, microsoft_config, errors):
        """Try to connect using Microsoft OAuth2.0."""
        try:
            _LOGGER.info("[_try_microsoft] Trying Microsoft OAuth2.0")

            from_email = microsoft_config.get("from_email")
            client_id = microsoft_config.get("client_id")
            client_secret = microsoft_config.get("client_secret")
            tenant_id = microsoft_config.get("tenant_id")
            smtp_host = microsoft_config.get("host", "smtp.office365.com")
            smtp_port = microsoft_config.get("port", 587)

            if not from_email:
                raise Exception("from_email is required in microsoft config")
            if not client_id or not client_secret or not tenant_id:
                raise Exception(
                    "client_id, client_secret, and tenant_id are required in microsoft config"
                )

            # Get Microsoft OAuth2.0 access token
            access_token = self._get_microsoft_token(
                client_id, client_secret, tenant_id
            )

            # Connect to Microsoft SMTP server
            self.smtp = smtplib.SMTP(smtp_host, smtp_port)
            self.smtp.ehlo()
            self.smtp.starttls()
            self.smtp.ehlo()

            # OAuth2.0 authentication
            auth_string = self.generate_oauth2_string(from_email, access_token)
            self.smtp.docmd("AUTH", "XOAUTH2 " + auth_string)

            self.from_email = from_email
            _LOGGER.info(
                f"[_try_microsoft] Successfully connected with Microsoft OAuth2.0 ({smtp_host}:{smtp_port}, from: {from_email})"
            )
            return True

        except Exception as e:
            error_msg = str(e)
            errors.append(("Microsoft OAuth2.0", error_msg))
            return False

    def _try_basic(self, basic_config, errors):
        """Try to connect using Basic ID/PW authentication."""
        try:
            _LOGGER.info("[_try_basic] Trying Basic ID/PW authentication")

            from_email = basic_config.get("from_email")
            host = basic_config.get("host")
            port = basic_config.get("port", 587)
            user = basic_config.get("user")
            password = basic_config.get("password")

            if not from_email:
                raise Exception("from_email is required in basic config")
            if not host:
                raise Exception("host is required in basic config")
            if not user or not password:
                raise Exception("user and password are required in basic config")

            # SMTP connection
            self.smtp = smtplib.SMTP(host, port)
            self.smtp.connect(host, port)
            self.smtp.ehlo()
            self.smtp.starttls()
            self.smtp.login(user, password)

            self.from_email = from_email
            _LOGGER.info(
                f"[_try_basic] Successfully connected with Basic ID/PW ({host}:{port}, from: {from_email})"
            )
            return True

        except Exception as e:
            error_msg = str(e)
            errors.append(("Basic ID/PW", error_msg))
            return False

    def _get_gmail_credentials(self, refresh_token, client_id, client_secret):
        """Create Gmail OAuth2.0 credentials."""

        token_uri = "https://oauth2.googleapis.com/token"
        scopes = ["https://mail.google.com/"]

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )

        if not creds.valid:
            creds.refresh(Request())

        return creds

    def _get_microsoft_token(self, client_id, client_secret, tenant_id):
        """Get Microsoft OAuth2.0 access token."""
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        scopes = ["https://outlook.office365.com/.default"]

        app = msal.ConfidentialClientApplication(
            client_id, authority=authority, client_credential=client_secret
        )
        result = app.acquire_token_for_client(scopes=scopes)

        if "access_token" not in result:
            error = result.get("error", "Unknown error")
            error_description = result.get("error_description", "")
            raise Exception(f"{error} - {error_description}")

        return result["access_token"]

    def generate_oauth2_string(self, user, access_token):
        """Generate OAuth2.0 authentication string."""
        auth_string = f"user={user}\1auth=Bearer {access_token}\1\1"
        return base64.b64encode(auth_string.encode()).decode()

    def send_email(self, to_emails, subject, contents):
        """
        Send an email

        Args:
            to_emails: Recipient email addresses (multiple recipients can be specified, separated by commas)
            subject: Email subject
            contents: Email content (HTML)

        Note:
            An SMTP connection is automatically attempted on the first call (Lazy Connection).
        """
        # Lazy Connection: connect when needed
        self._connect()

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
                _LOGGER.debug(f"[send_email] send email response : {response}")

        except smtplib.SMTPException as e:
            _LOGGER.error(f"[send_email] Failed to send email: {e}")
            raise ERROR_SMTP_SEND_EMAIL_FAILED(message=f"Failed to send email: {e}")

    def quit_smtp(self):
        if self.smtp:
            try:
                self.smtp.quit()
                _LOGGER.debug("[quit_smtp] SMTP connection closed")
                self.smtp = None  # Mark as closed
            except Exception as e:
                _LOGGER.warning(f"[quit_smtp] Failed to close SMTP connection: {e}")
