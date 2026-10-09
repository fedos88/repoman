from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, StringConstraints

from repoman.auth.policy import API_TOKEN_DEFAULT_LIFETIME_DAYS, API_TOKEN_MAX_LIFETIME_DAYS
from repoman.auth.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from repoman.db.models import ROLE_ADMIN, ApiToken, User
from repoman.users.names import LOCAL_USERNAME_PATTERN

Password = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, max_length=256)]
LocalUsername = Annotated[
    str,
    BeforeValidator(lambda value: value.strip().lower() if isinstance(value, str) else value),
    StringConstraints(pattern=LOCAL_USERNAME_PATTERN),
]


class UserOut(BaseModel):
    id: int
    username: str
    auth_source: Literal["local", "ldap"]
    first_name: str | None
    last_name: str | None
    display_name: str | None
    email: str | None
    is_active: bool
    blocked_by: Literal["admin", "ldap_sync"] | None
    must_change_password: bool
    roles: list[str]
    last_login_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            username=user.username,
            auth_source=user.auth_source,  # type: ignore[arg-type]
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user.display_name,
            email=user.email,
            is_active=user.is_active,
            blocked_by=user.blocked_by,  # type: ignore[arg-type]
            must_change_password=user.must_change_password,
            roles=user.role_names,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )


class MeOut(UserOut):
    is_admin: bool

    @classmethod
    def of_user(cls, user: User) -> "MeOut":
        return cls(**UserOut.of(user).model_dump(), is_admin=ROLE_ADMIN in user.role_names)


class UserPage(BaseModel):
    items: list[UserOut]
    total: int


class LoginIn(BaseModel):
    username: Annotated[str, Field(min_length=1, max_length=256)]
    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]


class ChangeOwnPasswordIn(BaseModel):
    current_password: Annotated[str, Field(max_length=PASSWORD_MAX_LENGTH)]
    new_password: Password


class ProfileFields(BaseModel):
    first_name: Name | None = None
    last_name: Name | None = None
    display_name: Name | None = None
    email: EmailStr | None = None


class UserCreateIn(ProfileFields):
    username: LocalUsername
    password: Password
    roles: list[str] = []
    must_change_password: bool = True


class UserUpdateIn(ProfileFields):
    """Fields that are omitted are left unchanged; explicit null clears a field."""

    model_config = ConfigDict(extra="forbid")


class ResetPasswordIn(BaseModel):
    password: Password
    must_change_password: bool = True


class RolesIn(BaseModel):
    roles: list[str]


class RoleOut(BaseModel):
    id: int
    name: str
    builtin: bool
    description: str | None
    assignable: bool


class TokenOut(BaseModel):
    id: int
    name: str
    prefix: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, token: ApiToken) -> "TokenOut":
        return cls(
            id=token.id,
            name=token.name,
            prefix=token.prefix,
            expires_at=token.expires_at,
            last_used_at=token.last_used_at,
            created_at=token.created_at,
        )


class TokenCreateIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    # Omitted: default lifetime; explicit null: the token never expires.
    expires_in_days: Annotated[int, Field(ge=1, le=API_TOKEN_MAX_LIFETIME_DAYS)] | None = (
        API_TOKEN_DEFAULT_LIFETIME_DAYS
    )


class TokenCreatedOut(TokenOut):
    token: str = Field(description="Shown only once")
