from datetime import date, datetime, time, timedelta
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.external.places import Place, PlaceCoordinate
from app.external.weather import DailyWeather


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


class TripRequest(BaseModel):
    """Trip facts extracted from the conversation, before business validation."""

    model_config = ConfigDict(extra="forbid")

    destination: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    interests: list[str] = Field(default_factory=list)
    budget: str | None = None
    pace: str | None = None
    travelers: int | None = Field(default=None, ge=1)
    notes: str | None = None

    @field_validator("destination", "budget", "pace", "notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("interests")
    @classmethod
    def normalize_interests(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            interest = value.strip()
            if interest and interest not in normalized:
                normalized.append(interest)
        return normalized

    def preferences(self) -> dict[str, Any]:
        return self.model_dump(
            include={"interests", "budget", "pace", "travelers", "notes"},
            exclude_none=True,
        )


VerificationSource = Literal["google_places", "open_meteo", "tavily"]


class Warning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["caution", "blocker"]
    code: str
    message: str
    source: VerificationSource | None = None
    item_id: str | None = None
    source_url: str | None = None


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    start_time: time
    end_time: time
    title: str = Field(min_length=1)
    description: str = ""
    kind: Literal["place", "generic"]
    place_id: str | None = None
    place: Place | None = None
    warnings: list[Warning] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_reference_and_time(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("Item end_time must be after start_time")
        if self.kind == "place" and not self.place_id:
            raise ValueError("Place items require place_id")
        if self.kind == "generic" and self.place_id is not None:
            raise ValueError("Generic activities cannot include place_id")
        return self


class Day(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    title: str = Field(min_length=1)
    accommodation: str | None = None
    items: list[Item] = Field(default_factory=list)


class Itinerary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: str = Field(min_length=1)
    destination_location: PlaceCoordinate | None = None
    start_date: date
    end_date: date
    days: list[Day]
    weather: list[DailyWeather] = Field(default_factory=list)
    warnings: list[Warning] = Field(default_factory=list)
    verification_status: Literal["verified", "partial", "unavailable"] = (
        "unavailable"
    )
    verified_sources: list[VerificationSource] = Field(default_factory=list)
    unavailable_sources: list[VerificationSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("Itinerary end_date must be on or after start_date")
        expected = [
            self.start_date + timedelta(days=offset)
            for offset in range((self.end_date - self.start_date).days + 1)
        ]
        if [day.date for day in self.days] != expected:
            raise ValueError("Itinerary days must cover the trip dates in order")
        item_ids = [item.id for day in self.days for item in day.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Itinerary item IDs must be unique")
        return self


class ItineraryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    trip_id: str
    data: Itinerary
    created_at: datetime


class PlanGenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    trip_id: str
    itinerary_id: str | None
    input_message_ts: datetime
    status: Literal["queued", "running", "succeeded", "failed"]
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


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
    latest_itinerary: ItineraryResponse | None = None
    plan_generation: PlanGenerationResponse | None = None


class VisaMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: Literal["required", "optional", "conditional"]
    details: str | None = None
    source_url: str


class VisaStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    title: str
    description: str
    source_url: str


class VisaOfficialLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class VisaSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    published_date: str | None = None


class VisaChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passport_country: str
    destination_country: str
    visa_required: bool | None = None
    visa_type: str | None = None
    allowed_stay: str | None = None
    processing_time: str | None = None
    fees: str | None = None
    notes: str | None = None
    materials: list[VisaMaterial] = Field(default_factory=list)
    steps: list[VisaStep] = Field(default_factory=list)
    official_links: list[VisaOfficialLink] = Field(default_factory=list)
    sources: list[VisaSource] = Field(default_factory=list)
    status: Literal["available", "unavailable"] = "unavailable"
    disclaimer: str


class VisaChecklistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_country: str
    destination_country_code: str
    stay_days: int = Field(ge=1)
    checklists: list[VisaChecklist]


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
