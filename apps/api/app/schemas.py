from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

DISCLAIMER = (
    "Information is assembled from third-party sources and may be out of date. "
    "Confirm opening hours, closures, and visa requirements with official sources "
    "before you travel."
)


# --- Geography & places -----------------------------------------------------


class GeoPoint(BaseModel):
    lat: float
    lng: float


class BusinessStatus(str, Enum):
    OPERATIONAL = "OPERATIONAL"
    CLOSED_TEMPORARILY = "CLOSED_TEMPORARILY"
    CLOSED_PERMANENTLY = "CLOSED_PERMANENTLY"
    UNKNOWN = "UNKNOWN"


class Place(BaseModel):
    """Normalised POI returned by the Places data source."""

    place_id: str
    name: str
    address: str | None = None
    location: GeoPoint | None = None
    business_status: BusinessStatus = BusinessStatus.UNKNOWN
    rating: float | None = None
    user_rating_count: int | None = None
    website: str | None = None
    google_maps_uri: str | None = None
    types: list[str] = Field(default_factory=list)
    # Per-weekday opening text, e.g. {"Monday": "9:00 AM – 6:00 PM"}.
    opening_hours: dict[str, str] = Field(default_factory=dict)
    open_now: bool | None = None


# --- Itinerary --------------------------------------------------------------


class WarningSeverity(str, Enum):
    INFO = "info"
    CAUTION = "caution"
    BLOCKER = "blocker"


class Warning(BaseModel):
    severity: WarningSeverity = WarningSeverity.CAUTION
    message: str
    source: str | None = None
    related_item: str | None = None


class ItineraryItem(BaseModel):
    name: str
    place_id: str | None = None
    category: str | None = None
    description: str | None = None
    start_time: str | None = None  # "09:30"
    end_time: str | None = None
    location: GeoPoint | None = None
    address: str | None = None
    website: str | None = None
    reservation_url: str | None = None
    business_status: BusinessStatus = BusinessStatus.UNKNOWN
    warnings: list[Warning] = Field(default_factory=list)


class DayWeather(BaseModel):
    date: str
    summary: str | None = None
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    precipitation_mm: float | None = None


class ItineraryDay(BaseModel):
    date: str  # ISO date
    title: str | None = None
    summary: str | None = None
    items: list[ItineraryItem] = Field(default_factory=list)
    weather: DayWeather | None = None


class Itinerary(BaseModel):
    destination: str
    start_date: str
    end_date: str
    days: list[ItineraryDay] = Field(default_factory=list)
    warnings: list[Warning] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


# --- Requests ---------------------------------------------------------------


class TripPace(str, Enum):
    RELAXED = "relaxed"
    BALANCED = "balanced"
    PACKED = "packed"


class TripRequest(BaseModel):
    destination: str
    start_date: str = Field(description="ISO date, e.g. 2026-07-01")
    end_date: str = Field(description="ISO date, e.g. 2026-07-05")
    interests: list[str] = Field(default_factory=list)
    budget: str | None = None
    pace: TripPace = TripPace.BALANCED
    travelers: int = 1
    notes: str | None = None


class ItineraryResponse(BaseModel):
    trip_id: str
    itinerary_id: str
    itinerary: Itinerary


# --- Visa -------------------------------------------------------------------


class VisaRequest(BaseModel):
    passport_country: str
    destination_country: str
    purpose: str = "tourism"
    duration_days: int = 14


class VisaDocument(BaseModel):
    name: str
    detail: str | None = None
    required: bool = True


class VisaChecklist(BaseModel):
    passport_country: str
    destination_country: str
    visa_required: bool | None = None
    visa_type: str | None = None
    allowed_stay: str | None = None
    processing_time: str | None = None
    fees: str | None = None
    documents: list[VisaDocument] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    official_links: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


# --- Chat -------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


# --- Documents --------------------------------------------------------------


class CoverLetterRequest(BaseModel):
    """Proof-of-travel / cover letter often required for Schengen-style visas."""

    applicant_name: str
    passport_country: str
    passport_number: str | None = None
    destination_country: str
    purpose: str = "tourism"
    start_date: str
    end_date: str
    addressed_to: str | None = None  # e.g. "The Visa Officer, Embassy of France"
    itinerary: Itinerary | None = None
    notes: str | None = None
