import logging

from spaceone.identity.connector.smtp_connector.base import SMTPConnector
from spaceone.identity.error.error_smtp import ERROR_SMTP_CONNECTION_FAILED

_LOGGER = logging.getLogger(__name__)

__all__ = ["BasicSMTPConnector"]


class BasicSMTPConnector(SMTPConnector):
    """Basic SMTP Connector with username/password authentication

    Standard SMTP authentication (username/password)

    Note:
        - credential key is ignored in Basic
    """

    provider_type = "basic"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Default values
        self.port = self.config.get("port", 587)
        self.use_tls = self.config.get("use_tls", True)

        # Authentication information
        self.user = self.config.get("user")
        self.secret = self.config.get("secret")

        # Validation
        if not self.host:
            raise ERROR_SMTP_CONNECTION_FAILED(error="Basic: host is required")
        if not self.user or not self.secret:
            raise ERROR_SMTP_CONNECTION_FAILED(
                error="Basic: user and secret are required"
            )

    def _authenticate(self):
        """Basic SMTP authentication: username/password login

        Standard SMTP LOGIN command is used to authenticate.

        Raises:
            Exception: Authentication failed
        """
        self.smtp.login(self.user, self.secret)
        _LOGGER.debug(f"[Basic] Authenticated as {self.user}")
