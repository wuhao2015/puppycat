from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    signup_code: str = Field(min_length=1)
    display_name: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return value

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    passport_countries: list[str] | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("passport_countries")
    @classmethod
    def normalize_passport_countries(
        cls, value: list[str] | None
    ) -> list[str] | None:
        if value is None:
            return None

        countries: list[str] = []
        for country in value:
            code = country.strip().upper()
            if len(code) != 2 or not code.isascii() or not code.isalpha():
                raise ValueError("Passport countries must use two-letter country codes")
            if code not in countries:
                countries.append(code)
        return countries


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str | None
    passport_countries: list[str]
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TripCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="New trip", min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Trip title cannot be empty")
        return title


class TripUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Trip title cannot be empty")
        return title


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    ts: datetime


class TripListItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    destination: str | None
    start_date: date | None
    end_date: date | None
    created_at: datetime
    updated_at: datetime


class TripResponse(TripListItemResponse):
    preferences: dict[str, Any]
    chat_messages: list[ChatMessage]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user"] = "user"
    content: str = Field(min_length=1, max_length=10_000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("Message cannot be empty")
        return content


class ChatDevelopmentResponse(BaseModel):
    message: ChatMessage
    trip_updated_at: datetime
    assistant_status: Literal["gemini_not_connected"] = "gemini_not_connected"
