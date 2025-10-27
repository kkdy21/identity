from spaceone.core.error import *


class ERROR_SMTP_CONNECTION_FAILED(ERROR_UNKNOWN):
    _message = "SMTP server connection failed: {error}"


class ERROR_SMTP_SEND_EMAIL_FAILED(ERROR_UNKNOWN):
    _message = "Failed to send email: {error}"
