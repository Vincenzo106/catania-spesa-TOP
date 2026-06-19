from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ExtractedOffer(BaseModel):
    product_name: str = Field(min_length=1)
    brand: str | None = None
    original_price: float | None = Field(default=None, ge=0)
    discounted_price: float | None = Field(default=None, ge=0)
    flyer_valid_until: date | None = None


class ExtractedOfferBatch(BaseModel):
    offers: list[ExtractedOffer] = Field(default_factory=list)


class OfferCreate(BaseModel):
    store: str = Field(min_length=1)
    category: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    brand: str | None = None
    original_price: float | None = Field(default=None, ge=0)
    discounted_price: float = Field(ge=0)
    discount_percentage: float | None = Field(default=None, ge=0, le=100)
    flyer_valid_until: date | None = None
    source_filename: str | None = None
    is_demo: bool = False


class OfferRecord(OfferCreate):
    id: int
    created_at: datetime


class OfferListResponse(BaseModel):
    items: list[OfferRecord]
    total: int
    available_stores: list[str]
    available_categories: list[str]


class BestDealsResponse(BaseModel):
    items: list[OfferRecord]


class StoreListResponse(BaseModel):
    stores: list[str]


class IngestResponse(BaseModel):
    source_filename: str
    provider: str
    offers_created: int
    records: list[OfferRecord]


class HealthResponse(BaseModel):
    status: str
    provider: str
    database_path: str
    seed_demo_data: bool


class ErrorResponse(BaseModel):
    detail: str


JsonDict = dict[str, Any]
