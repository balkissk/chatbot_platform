from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from services.auth import validate_password_policy


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "end_user"

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_policy(value)


class AdminUserCreate(BaseModel):
    name: str
    email: str
    role: str = "end_user"


class UserLogin(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_policy(value)


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    status: str
    email_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None
    project_count: int | None = None
    chatbot_count: int | None = None

    class Config:
        from_attributes = True


class UserStatsResponse(BaseModel):
    total_users: int
    active_users: int
    disabled_users: int
    managers: int


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    stats: UserStatsResponse


class TokenResponse(BaseModel):
    user: UserResponse


class RegistrationResponse(BaseModel):
    message: str
    user: UserResponse


class UserStatusUpdate(BaseModel):
    status: str


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        if len(value) > 120:
            raise ValueError("Name must be 120 characters or fewer")
        return value


class UserPasswordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_policy(value)
