import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from spaceone.identity.connector.smtp_connector.base import SMTPConnector
from spaceone.identity.error.error_smtp import ERROR_SMTP_CONNECTION_FAILED

_LOGGER = logging.getLogger(__name__)

__all__ = ["GmailSMTPConnector"]


class GmailSMTPConnector(SMTPConnector):
    """Gmail SMTP Connector with OAuth2.0

    Gmail OAuth2.0 SMTP connection

    Note:
        - user = OAuth2.0 client_id
        - secret = OAuth2.0 client_secret
        - credential = OAuth2.0 refresh_token
    """

    provider_type = "gmail"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Gmail Default values
        self.host = self.config.get("host", "smtp.gmail.com")
        self.port = self.config.get("port", 587)

        # OAuth2.0 settings
        self.client_id = self.config.get("user")  # user = client_id
        self.client_secret = self.config.get("secret")  # secret = client_secret
        self.refresh_token = self.config.get("credential")  # credential = refresh_token

        # Validation
        if not self.client_id or not self.client_secret:
            raise ERROR_SMTP_CONNECTION_FAILED(
                error="Gmail: user (client_id) and secret (client_secret) are required"
            )
        if not self.refresh_token:
            raise ERROR_SMTP_CONNECTION_FAILED(
                error="Gmail: credential (refresh_token) is required"
            )

    def _authenticate(self):
        """Gmail OAuth2.0 authentication: XOAUTH2 mechanism

        Google OAuth2.0 Credentials are used to issue an access token,
        and authenticate with the XOAUTH2 mechanism.

        Raises:
            Exception: Authentication failed
        """
        # OAuth2.0 Credentials creation and refresh
        creds = self._get_credentials()

        # OAuth2.0 authentication
        auth_string = self.generate_oauth2_string(self.from_email, creds.token)
        self.smtp.docmd("AUTH", "XOAUTH2 " + auth_string)

        _LOGGER.debug(f"[Gmail] Authenticated with OAuth2.0 for {self.from_email}")

    def _get_credentials(self) -> Credentials:
        """Create and refresh Gmail OAuth2.0 Credentials

        Use Refresh Token to issue a new Access Token.

        Returns:
            google.oauth2.credentials.Credentials: Refreshed OAuth2.0 Credentials

        Raises:
            Exception: Credentials creation or refresh failed
        """
        token_uri = "https://oauth2.googleapis.com/token"
        scopes = ["https://mail.google.com/"]

        creds = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri=token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=scopes,
        )

        # Access Token refresh
        if not creds.valid:
            creds.refresh(Request())
            _LOGGER.debug("[Gmail] Access token refreshed successfully")

        return creds
