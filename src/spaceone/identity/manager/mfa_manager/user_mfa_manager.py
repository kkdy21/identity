import logging
from typing import Tuple

from spaceone.core.error import *
from spaceone.core.manager import BaseManager
from spaceone.identity.error.error_mfa import *
from spaceone.identity.manager.mfa_manager.base import MFAManager
from spaceone.identity.manager.secret_manager import SecretManager
from spaceone.identity.model.user.database import User

_LOGGER = logging.getLogger(__name__)


class UserMFAManager(BaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def set_enforcement(
        self, user_vo: User, mfa_type: str, domain_id: str
    ) -> Tuple[dict, list]:
        if user_vo.auth_type == "EXTERNAL":
            raise ERROR_NOT_ALLOWED_ACTIONS(action="MFA")

        user_mfa = self._get_user_mfa_as_dict(user_vo)
        required_actions = list(set(user_vo.required_actions))

        if user_mfa.get("mfa_type") != mfa_type:
            if user_mfa.get("mfa_type") == "OTP":
                self._delete_otp_secret(user_vo, domain_id)
            user_mfa["mfa_type"] = mfa_type
            user_mfa["state"] = "DISABLED"
            user_mfa.get("options", {}).clear()

        user_mfa["options"] = {"enforce": True}
        if "ENFORCE_MFA" not in required_actions:
            required_actions.append("ENFORCE_MFA")

        return user_mfa, required_actions

    def unset_enforcement(self, user_vo: User) -> Tuple[dict, list]:
        user_mfa = self._get_user_mfa_as_dict(user_vo)
        required_actions = list(set(user_vo.required_actions))

        if user_mfa.get("state", "DISABLED") == "DISABLED":
            user_mfa.pop("mfa_type", None)

        user_mfa.get("options", {}).pop("enforce", None)
        if "ENFORCE_MFA" in required_actions:
            required_actions.remove("ENFORCE_MFA")

        return user_mfa, required_actions

    def reset_user_mfa(self, user_vo: User, domain_id: str) -> Tuple[dict, list]:
        if user_vo.mfa.get("state", "DISABLED") == "DISABLED" or not user_vo.mfa.get(
            "mfa_type"
        ):
            raise ERROR_MFA_ALREADY_DISABLED(user_id=user_vo.user_id)

        user_mfa = self._get_user_mfa_as_dict(user_vo)
        required_actions = list(set(user_vo.required_actions))

        if user_mfa.get("mfa_type") == "OTP" and user_mfa.get("state") == "ENABLED":
            self._delete_otp_secret(user_vo, domain_id)

        user_mfa["state"] = "DISABLED"

        if user_mfa.get("options", {}).get("enforce"):
            if "ENFORCE_MFA" not in required_actions:
                required_actions.append("ENFORCE_MFA")
        else:
            user_mfa.pop("mfa_type", None)

        return user_mfa, required_actions

    def prepare_to_enable(
        self,
        user_vo: User,
        mfa_type: str,
        options: dict,
    ) -> User:
        if user_vo.auth_type == "EXTERNAL":
            raise ERROR_NOT_ALLOWED_ACTIONS(action="MFA")

        user_mfa = self._get_user_mfa_as_dict(user_vo)
        self._check_mfa_is_enforced(user_mfa, mfa_type)

        if user_mfa.get("state", "DISABLED") == "ENABLED":
            raise ERROR_MFA_ALREADY_ENABLED(user_id=user_vo.user_id)

        self._check_mfa_options(options, mfa_type)

        mfa_manager = MFAManager.get_manager_by_mfa_type(mfa_type)

        user_mfa["mfa_type"] = mfa_type
        user_mfa["state"] = user_mfa.get("state", "DISABLED")
        user_mfa["options"] = {**user_mfa.get("options", {}), **options}

        if mfa_type in ["EMAIL", "OTP"]:
            user_vo.mfa = mfa_manager.enable_mfa(
                user_vo.user_id, user_vo.domain_id, user_mfa, user_vo
            )
        else:
            raise ERROR_NOT_SUPPORTED_MFA_TYPE(support_mfa_types=["EMAIL", "OTP"])

        return user_vo

    def confirm_and_enable(self, user_vo: User, verify_code: str) -> Tuple[dict, list]:
        credentials = {"user_id": user_vo.user_id, "domain_id": user_vo.domain_id}
        user_mfa = self._get_user_mfa_for_confirmation(user_vo, credentials)
        mfa_type = user_mfa["mfa_type"]
        mfa_manager = MFAManager.get_manager_by_mfa_type(mfa_type)
        required_actions = list(set(user_vo.required_actions))

        if mfa_manager.confirm_mfa(credentials, verify_code):
            user_mfa = mfa_manager.set_mfa_options(user_mfa, credentials)
            user_mfa["state"] = "ENABLED"
            if "ENFORCE_MFA" in required_actions:
                required_actions.remove("ENFORCE_MFA")
        else:
            raise ERROR_INVALID_VERIFY_CODE(verify_code=verify_code)

        return user_mfa, required_actions

    def confirm_and_disable(self, user_vo: User, verify_code: str) -> Tuple[dict, list]:
        credentials = {"user_id": user_vo.user_id, "domain_id": user_vo.domain_id}
        user_mfa = self._get_user_mfa_for_confirmation(user_vo, credentials)
        mfa_type = user_mfa["mfa_type"]
        mfa_manager = MFAManager.get_manager_by_mfa_type(mfa_type)
        required_actions = list(set(user_vo.required_actions))
        is_enforced = user_mfa.get("options", {}).get("enforce", False)

        if mfa_manager.confirm_mfa(credentials, verify_code):
            user_mfa["state"] = "DISABLED"
            if is_enforced:
                if "ENFORCE_MFA" not in required_actions:
                    required_actions.append("ENFORCE_MFA")
            else:
                user_mfa.pop("mfa_type", None)
        else:
            raise ERROR_INVALID_VERIFY_CODE(verify_code=verify_code)

        return user_mfa, required_actions

    @staticmethod
    def _check_mfa_is_enforced(user_mfa: dict, mfa_type: str) -> None:
        if (
            user_mfa.get("options", {}).get("enforce")
            and user_mfa.get("mfa_type")
            and mfa_type != user_mfa.get("mfa_type")
        ):
            raise ERROR_INVALID_PARAMETER(
                key="mfa.mfa_type",
                reason="Only requests using the MFA type enforced by admin are allowed.",
            )

    @staticmethod
    def _check_mfa_options(options: dict, mfa_type: str) -> None:
        if mfa_type == "EMAIL" and "email" not in options:
            raise ERROR_REQUIRED_PARAMETER(key="options.email")

    def _delete_otp_secret(self, user_vo: User, domain_id: str) -> None:
        user_mfa = self._get_user_mfa_as_dict(user_vo)
        user_secret_id = user_mfa.get("options", {}).get("user_secret_id")

        if user_secret_id:
            secret_manager: SecretManager = self.locator.get_manager(SecretManager)
            secret_manager.delete_user_secret_with_system_token(
                domain_id, user_secret_id
            )
