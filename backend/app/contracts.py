import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailInput(Input):
    email: str = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Invalid email")
        value = value.strip().lower()
        local, separator, domain = value.partition("@")
        if (
            not separator
            or len(local) > 64
            or not re.fullmatch(r"[a-z0-9!#$%&'*+/=?^_`{|}~.-]+", local)
            or local.startswith(".")
            or local.endswith(".")
            or ".." in local
            or "." not in domain
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in domain.split(".")
            )
        ):
            raise ValueError("Invalid email")
        return value


class Login(EmailInput):
    # Existing hashes remain usable, including passwords created under the old policy.
    password: str = Field(min_length=1, max_length=128)


class Register(Login):
    code: str = Field(pattern=r"^[0-9]{6}$")
    password: str = Field(min_length=6, max_length=128)


class PasswordReset(EmailInput):
    code: str = Field(pattern=r"^[0-9]{6}$")
    new_password: str = Field(min_length=6, max_length=128)


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class Version(Input):
    expected_version: int = Field(gt=0, strict=True)


class Display(Input):
    font_size: Literal["normal", "large"] = "normal"
    reduced_motion: bool = True
    hide_titles: bool = False


class PreferenceChange(Version):
    age_band: Literal["adult", "minor", "unknown"]
    mode: Literal["listen", "explore"] = "listen"
    display_preferences: Display = Field(default_factory=Display)


class ConsentCreate(Input):
    purpose: Literal["service_context", "optional_profile", "saved_memory", "research"]
    decision: Literal["granted", "declined"]
    notice_version: Literal["synthetic-notice/1"]
    scope: list[Literal["current_run"]] = Field(default_factory=list, max_length=1)


class SessionCreate(Input):
    title: str = Field(default="新的对话", min_length=1, max_length=120)


class SessionChange(Version):
    title: str = Field(min_length=1, max_length=120)


class DraftCreate(Input):
    context_type: Literal["conversation"]
    session_id: str = Field(max_length=36)
    expected_session_version: int = Field(gt=0, strict=True)
    kind: Literal["message"] = "message"


class GrantCreate(Input):
    run_id: str = Field(max_length=36)
    source_type: Literal["conversation"]
    source_id: str = Field(max_length=36)
    source_version: int = Field(gt=0, strict=True)
    purpose: Literal["current_run"]
