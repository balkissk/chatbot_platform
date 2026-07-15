import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PlatformSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_name: str
    support_email: str
    default_page_size: int

    @field_validator("platform_name")
    @classmethod
    def validate_platform_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Platform name is required")
        if len(trimmed) > 80:
            raise ValueError("Platform name must be 80 characters or fewer")
        return trimmed

    @field_validator("support_email")
    @classmethod
    def validate_support_email(cls, value: str) -> str:
        trimmed = value.strip().lower()
        if not trimmed:
            raise ValueError("Support email is required")
        if len(trimmed) > 255 or not EMAIL_PATTERN.match(trimmed):
            raise ValueError("Support email must be a valid email address")
        return trimmed

    @field_validator("default_page_size")
    @classmethod
    def validate_default_page_size(cls, value: int) -> int:
        if value < 10 or value > 100:
            raise ValueError("Default page size must be between 10 and 100")
        return value


class PlatformSettingsResponse(BaseModel):
    platform_name: str
    support_email: str
    default_page_size: int
    updated_at: datetime | None = None
    updated_by: int | None = None
    updated_by_name: str | None = None
    updated_by_email: str | None = None
