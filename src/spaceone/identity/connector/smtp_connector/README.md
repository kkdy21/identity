# SMTP Connector 리팩토링

token_manager 패턴을 따라 리팩토링된 SMTP Connector 모듈입니다.

## 📁 폴더 구조

```
smtp_connector/
├── __init__.py                 # 모듈 export
├── base.py                     # BaseSMTPConnector (추상 클래스)
├── gmail_connector.py          # GmailSMTPConnector (OAuth2.0)
├── microsoft_connector.py      # MicrosoftSMTPConnector (OAuth2.0)
├── basic_connector.py          # BasicSMTPConnector (username/password)
└── README.md                   # 이 파일
```

## 🎯 주요 개선 사항

### 1. **✨ 완전 공통 키 (5개 키만 사용)**
**모든 제공자가 정확히 같은 5개 키**를 사용합니다!

```python
# ✨ 완전 공통 키 (5개)
config = {
    "provider": "gmail",  # 또는 "microsoft", "basic"
    "from_email": "sender@company.com",
    "user": "...",        # 모든 제공자에서 사용
    "secret": "...",      # 모든 제공자에서 사용
    "credential": "...",  # Gmail/Microsoft에서만 사용, Basic은 무시
    "host": "...",        # Optional
    "port": 587,          # Optional
}
```

### 2. **키 매핑 (제공자별 의미)**

| 공통 키 | Basic | Gmail | Microsoft |
|---------|-------|-------|-----------|
| `user` | SMTP 사용자명 | OAuth2 client_id | OAuth2 client_id |
| `secret` | SMTP 비밀번호 | OAuth2 client_secret | OAuth2 client_secret |
| `credential` | *무시됨* | OAuth2 refresh_token | Azure tenant_id |

### 3. **token_manager 패턴 적용**
`get_connector_by_provider()` 메소드로 자동 선택됩니다.

```python
# __subclasses__()를 사용한 자동 탐색
provider = config.get("provider", "basic")
connector_class = BaseSMTPConnector.get_connector_by_provider(provider)
connector = connector_class(config)
```

## 📝 Config 설정 (완전 공통 키)

### ✨ 공통 키 목록 (5개)
| 키 | 필수 | 설명 |
|---|------|------|
| `provider` | ✅ | 제공자 타입 (gmail, microsoft, basic) |
| `from_email` | ✅ | 발신자 이메일 |
| `user` | ✅ | 사용자 식별자 (username / client_id) |
| `secret` | ✅ | 비밀 키 (password / client_secret) |
| `credential` | ⭕ | 추가 인증 정보 (refresh_token / tenant_id) |
| `host` | ⭕ | SMTP 서버 호스트 (제공자별 기본값) |
| `port` | ⭕ | SMTP 포트 (기본값: 587) |

### Gmail (OAuth2.0)
```python
CONNECTORS = {
    "SMTPConnector": {
        "provider": "gmail",
        "from_email": "sender@gmail.com",
        "user": "your-client-id.apps.googleusercontent.com",  # client_id
        "secret": "your-client-secret",                       # client_secret
        "credential": "your-refresh-token",                   # refresh_token
        # host, port 생략 가능 (기본값: smtp.gmail.com:587)
    }
}
```

#### Gmail Refresh Token 발급 방법:
1. GCP Console에서 OAuth2.0 Client 생성
2. Scope: `https://mail.google.com/` 추가
3. OAuth2.0 Playground 또는 코드로 Authorization Code 발급
4. Authorization Code로 Refresh Token 교환

### Microsoft Office 365 (OAuth2.0)
```python
CONNECTORS = {
    "SMTPConnector": {
        "provider": "microsoft",
        "from_email": "sender@company.com",
        "user": "your-client-id",        # client_id
        "secret": "your-client-secret",  # client_secret
        "credential": "your-tenant-id",  # tenant_id
        # host, port 생략 가능 (기본값: smtp.office365.com:587)
    }
}
```

#### Microsoft Azure AD 설정 방법:
1. Azure Portal → App registrations → New registration
2. API permissions → Add permission → Office 365 Exchange Online
3. SMTP.Send (Application) 권한 추가
4. Admin consent 부여
5. Certificates & secrets → New client secret 생성

### Basic (일반 SMTP)
```python
CONNECTORS = {
    "SMTPConnector": {
        "provider": "basic",
        "from_email": "sender@company.com",
        "user": "smtp-username",      # SMTP 사용자명
        "secret": "smtp-password",    # SMTP 비밀번호
        "host": "smtp.yourserver.com",
        "port": 587,
        # credential은 무시됨
    }
}
```

### SendGrid
```python
CONNECTORS = {
    "SMTPConnector": {
        "provider": "basic",
        "from_email": "sender@company.com",
        "user": "apikey",                    # SendGrid 고정값
        "secret": "your-sendgrid-api-key",
        "host": "smtp.sendgrid.net",
        "port": 587
    }
}
```

### Amazon SES
```python
CONNECTORS = {
    "SMTPConnector": {
        "provider": "basic",
        "from_email": "sender@company.com",
        "user": "your-smtp-username",
        "secret": "your-smtp-password",
        "host": "email-smtp.us-east-1.amazonaws.com",
        "port": 587
    }
}
```

### 💡 완전 공통 키 방식: Config 하나로 모든 제공자 사용!

**같은 5개 키로 모든 제공자를 사용할 수 있습니다!**

```python
# 하나의 config에 모든 인증 정보를 넣고
unified_config = {
    "from_email": "sender@company.com",
    "user": "your-user-or-client-id",
    "secret": "your-password-or-client-secret",
    "credential": "refresh-token-or-tenant-id",  # Gmail/Microsoft만 사용
    "host": "smtp.example.com",
}

# Provider만 바꿔서 사용!
gmail_config = {**unified_config, "provider": "gmail"}
# → user=client_id, secret=client_secret, credential=refresh_token

ms_config = {**unified_config, "provider": "microsoft"}
# → user=client_id, secret=client_secret, credential=tenant_id

basic_config = {**unified_config, "provider": "basic"}
# → user=username, secret=password, credential은 무시
```

## 🚀 사용 방법

### 방법 1: Config에서 자동 선택 (권장)
```python
from spaceone.identity.connector.smtp_connector.base import BaseSMTPConnector

# Config에서 provider로 자동 선택
provider = config.get("provider", "basic")
connector_class = BaseSMTPConnector.get_connector_by_provider(provider)
smtp_connector = connector_class(config)

# 이메일 전송 (첫 호출 시 자동으로 연결됨)
smtp_connector.send_email(
    to_emails="user@example.com",
    subject="Test Email",
    contents="<h1>Hello!</h1>"
)

# 연결 종료
smtp_connector.quit_smtp()
```

### 방법 2: Context Manager 사용
```python
from spaceone.identity.connector.smtp_connector.base import BaseSMTPConnector

provider = config.get("provider", "basic")
connector_class = BaseSMTPConnector.get_connector_by_provider(provider)

with connector_class(config) as smtp:
    smtp.send_email(
        to_emails="user1@example.com,user2@example.com",  # 여러 명
        subject="Test Email",
        contents="<h1>Hello!</h1>"
    )
# 자동으로 연결 종료됨
```

### 방법 3: 직접 import
```python
from spaceone.identity.connector.smtp_connector.gmail_connector import GmailSMTPConnector

connector = GmailSMTPConnector(config)
connector.send_email(...)
connector.quit_smtp()
```

## 🔧 지원 Provider

| Provider | provider_type | 호스트 | 포트 | 인증 방식 |
|----------|---------------|--------|------|-----------|
| **Gmail** | `gmail` | smtp.gmail.com | 587 | OAuth2.0 |
| **Microsoft** | `microsoft` | smtp.office365.com | 587 | OAuth2.0 (MSAL) |
| **SendGrid** | `basic` | smtp.sendgrid.net | 587 | User/Secret |
| **Amazon SES** | `basic` | email-smtp.{region}.amazonaws.com | 587 | User/Secret |
| **기타** | `basic` | 사용자 지정 | 사용자 지정 | User/Secret |

## 📦 클래스 구조

```
BaseConnector (spaceone.core)
    └── BaseSMTPConnector (추상 클래스)
            ├── GmailSMTPConnector (OAuth2.0)
            ├── MicrosoftSMTPConnector (OAuth2.0)
            └── BasicSMTPConnector (User/Secret)
```

## 🎨 디자인 패턴

### Strategy + Template Method 하이브리드 ⭐

**공통 로직은 base에서 처리하고, 인증만 각 connector에서 구현합니다.**

```python
# Base: 공통 연결 로직
class BaseSMTPConnector:
    def connect(self):
        """Template Method: 공통 로직 정의"""
        # 1. SMTP 서버 연결 (공통)
        self.smtp = smtplib.SMTP(self.host, self.port)

        # 2. TLS 설정 (공통)
        self.smtp.ehlo()
        if self.use_tls:
            self.smtp.starttls()
            self.smtp.ehlo()

        # 3. 인증 (Strategy: 각 구현체에서 정의)
        self._authenticate()

    @abstractmethod
    def _authenticate(self):
        """각 제공자별 인증 전략"""
        pass

# 각 Connector: 인증만 구현
class BasicSMTPConnector(BaseSMTPConnector):
    def _authenticate(self):
        self.smtp.login(self.user, self.secret)

class GmailSMTPConnector(BaseSMTPConnector):
    def _authenticate(self):
        auth_string = self.generate_oauth2_string(...)
        self.smtp.docmd("AUTH", "XOAUTH2 " + auth_string)
```

**장점**:
- ✅ **코드 중복 제거**: SMTP 연결 로직(ehlo, starttls)이 base에만 존재
- ✅ **단일 책임**: 연결 vs 인증이 명확히 분리
- ✅ **유지보수 용이**: SMTP 공통 로직 수정 시 한 곳만 수정
- ✅ **확장성**: 새 제공자 추가 시 `_authenticate()`만 구현

### 기타 패턴

- **token_manager Pattern**: `get_connector_by_provider()`로 자동 선택
- **Lazy Initialization**: 첫 `send_email()` 호출 시 자동 연결
- **Context Manager**: `with` 문으로 자동 리소스 관리

## 🔄 마이그레이션 가이드

### 기존 코드
```python
from spaceone.identity.connector.smtp_connector import SMTPConnector

connector = SMTPConnector(config)
connector.send_email(...)
connector.quit_smtp()
```

### 리팩토링 후 (하위 호환)
```python
# 같은 코드 그대로 동작! (BasicSMTPConnector로 매핑됨)
from spaceone.identity.connector.smtp_connector import SMTPConnector

connector = SMTPConnector(config)
connector.send_email(...)
connector.quit_smtp()
```

### 권장 방식
```python
from spaceone.identity.connector.smtp_connector.base import BaseSMTPConnector

# provider로 자동 선택
provider = config.get("provider", "basic")
connector_class = BaseSMTPConnector.get_connector_by_provider(provider)
connector = connector_class(config)
connector.send_email(...)
connector.quit_smtp()
```

## 🆕 새로운 Provider 추가하기

✨ **Strategy + Template Method 패턴** 덕분에 `_authenticate()` 메서드만 구현하면 됩니다!

```python
# new_provider_connector.py
import logging
from spaceone.identity.connector.smtp_connector.base import BaseSMTPConnector

_LOGGER = logging.getLogger(__name__)

class NewProviderSMTPConnector(BaseSMTPConnector):
    provider_type = "new_provider"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 공통 키(user, secret, credential)를 사용하여 설정
        self.api_key = self.config.get("user")
        self.api_secret = self.config.get("secret")
        self.extra = self.config.get("credential")

        # 필수 값 검증
        if not self.api_key or not self.api_secret:
            raise ERROR_SMTP_CONNECTION_FAILED(
                message="NewProvider: user and secret are required"
            )

    def _authenticate(self):
        """인증 로직만 구현하면 됩니다!

        SMTP 연결(ehlo, starttls)은 이미 base.connect()에서 처리됩니다.
        """
        # 제공자별 인증 로직 구현
        # 예: 커스텀 AUTH 메커니즘
        auth_token = f"{self.api_key}:{self.api_secret}"
        self.smtp.docmd("AUTH", f"CUSTOM {auth_token}")

        _LOGGER.debug(f"[NewProvider] Authenticated successfully")
```

**이것이 전부입니다!**
- SMTP 연결, TLS 설정, 에러 처리는 모두 base가 자동 처리
- 인증 로직만 `_authenticate()`에 구현

## 📚 참고

- [Gmail SMTP 설정](https://support.google.com/mail/answer/7126229)
- [Office 365 SMTP 설정](https://learn.microsoft.com/en-us/exchange/mail-flow-best-practices/how-to-set-up-a-multifunction-device-or-application-to-send-email-using-microsoft-365-or-office-365)
- [SendGrid SMTP](https://docs.sendgrid.com/for-developers/sending-email/integrating-with-the-smtp-api)
- [Amazon SES SMTP](https://docs.aws.amazon.com/ses/latest/dg/smtp-connect.html)
- [Google OAuth2.0](https://developers.google.com/identity/protocols/oauth2)
- [Microsoft MSAL](https://learn.microsoft.com/en-us/azure/active-directory/develop/msal-overview)

## ✅ 장점 요약

1. **✨ 완전 공통 키**: 모든 제공자가 정확히 같은 5개 키 사용
2. **단순함**: 키 이름만 통일하여 극도로 단순화
3. **provider만 변경**: config 복사해서 provider만 바꾸면 됨
4. **확장 가능**: 새 제공자 추가 시 같은 키 사용
5. **하위 호환**: 기존 코드와 호환
6. **token_manager 패턴**: 일관된 코드 스타일
7. **OAuth2.0 지원**: Gmail, Microsoft OAuth2.0 기본 지원
8. **Lazy Connection**: 필요할 때만 연결
9. **Context Manager**: 안전한 리소스 관리
