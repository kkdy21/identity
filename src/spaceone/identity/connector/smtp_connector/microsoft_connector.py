import logging

import msal

from spaceone.identity.connector.smtp_connector.base import SMTPConnector
from spaceone.identity.error.error_smtp import ERROR_SMTP_CONNECTION_FAILED

_LOGGER = logging.getLogger(__name__)

__all__ = ["MicrosoftSMTPConnector"]


class MicrosoftSMTPConnector(SMTPConnector):
    """Microsoft Office 365 SMTP Connector with OAuth2.0

    Microsoft OAuth2.0 (Client Credentials Flow) SMTP connection

    Note:
        - Azure AD에서 App Registration is required

    Note:
        - user = OAuth2.0 client_id
        - secret = OAuth2.0 client_secret
        - credential = Azure AD tenant_id

    """

    provider_type = "microsoft"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Microsoft Default values
        self.host = self.config.get("host", "smtp.office365.com")
        self.port = self.config.get("port", 587)

        # OAuth2.0 settings
        self.client_id = self.config.get("user")  # user = client_id
        self.client_secret = self.config.get("secret")  # secret = client_secret
        self.tenant_id = self.config.get("credential")  # credential = tenant_id

        # Validation
        if not self.client_id or not self.client_secret:
            raise ERROR_SMTP_CONNECTION_FAILED(
                error="Microsoft: user (client_id) and secret (client_secret) are required"
            )
        if not self.tenant_id:
            raise ERROR_SMTP_CONNECTION_FAILED(
                error="Microsoft: credential (tenant_id) is required"
            )

    def _authenticate(self):
        """Microsoft OAuth2.0 authentication: XOAUTH2 mechanism

        MSAL(Microsoft Authentication Library) is used to issue an access token,
        and authenticate with the XOAUTH2 mechanism.

        Raises:
            Exception: Authentication failed
        """
        # OAuth2.0 Access Token issuance
        access_token = self._get_access_token()

        # OAuth2.0 authentication
        auth_string = self.generate_oauth2_string(self.from_email, access_token)
        self.smtp.docmd("AUTH", "XOAUTH2 " + auth_string)

        _LOGGER.debug(f"[Microsoft] Authenticated with OAuth2.0 for {self.from_email}")

    def _get_access_token(self) -> str:
        """Issue Microsoft OAuth2.0 Access Token

        Client Credentials Flow is used to issue an application-level Access Token.
        Access Token is issued.

        Returns:
            str: OAuth2.0 Access Token

        Raises:
            Exception: Token issuance failed
        """
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        scopes = ["https://outlook.office365.com/.default"]

        # MSAL Confidential Client creation
        app = msal.ConfidentialClientApplication(
            self.client_id, authority=authority, client_credential=self.client_secret
        )

        # Access Token issuance
        result = app.acquire_token_for_client(scopes=scopes)

        if "access_token" not in result:
            error = result.get("error", "Unknown error")
            error_description = result.get("error_description", "")
            raise Exception(f"{error} - {error_description}")

        _LOGGER.debug("[Microsoft] Access token acquired successfully")
        return result["access_token"]
