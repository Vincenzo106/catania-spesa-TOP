from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ExtractedOffer(BaseModel):
    product_name: str = Field(min_length=1)
    brand: str | None = None
    original_price: float | None = Field(default=None, ge=0)
    discounted_price: float | None = Field(default=None, ge=0)
    flyer_valid_until: date | None = None
    category: str | None = None
    unit: str | None = None
    quantity: str | None = None
    valid_from: date | None = None
    flyer_title: str | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)


class ExtractedOfferBatch(BaseModel):
    offers: list[ExtractedOffer] = Field(default_factory=list)


class OfferCreate(BaseModel):
    store: str = Field(min_length=1)
    category: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    normalized_product_name: str = Field(min_length=1)
    brand: str | None = None
    original_price: float | None = Field(default=None, ge=0)
    discounted_price: float = Field(ge=0)
    discount_percentage: float | None = Field(default=None, ge=0, le=100)
    unit: str | None = None
    quantity: str | None = None
    valid_from: date | None = None
    flyer_valid_until: date | None = None
    flyer_url: str | None = None
    flyer_title: str | None = None
    source_url: str | None = None
    source_type: str | None = None
    source: str | None = None
    source_filename: str | None = None
    store_location: str | None = None
    city: str | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    is_demo: bool = False
    is_active: bool = True
    extraction_batch_id: str | None = None
    dedupe_key: str = Field(min_length=1)
    updated_at: datetime | None = None


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


class SourceRegistryItem(BaseModel):
    source_key: str
    store: str
    source_url: str
    source_type: str
    city_filter: str | None = None
    province_filter: str | None = None
    active: bool = True
    priority: int = 100
    parser_strategy: str | None = None
    notes: str | None = None
    selectors: dict[str, str] = Field(default_factory=dict)
    direct_flyer_url: str | None = None
    store_location: str | None = None


class SourceStateRecord(BaseModel):
    source_key: str
    store: str
    source_url: str
    source_type: str
    city_filter: str | None = None
    province_filter: str | None = None
    active: bool = True
    priority: int = 100
    parser_strategy: str | None = None
    notes: str | None = None
    selectors: dict[str, str] = Field(default_factory=dict)
    direct_flyer_url: str | None = None
    store_location: str | None = None
    last_seen_flyer_url: str | None = None
    last_seen_hash: str | None = None
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_flyer_title: str | None = None
    last_change_detected_at: datetime | None = None
    updated_at: datetime | None = None


class SourceCheckResult(BaseModel):
    source_key: str
    store: str
    source_url: str
    source_type: str
    status: str
    change_detected: bool = False
    flyers_found: int = 0
    flyer_url: str | None = None
    flyer_title: str | None = None
    flyer_hash: str | None = None
    offers_extracted: int = 0
    offers_added: int = 0
    offers_updated: int = 0
    offers_skipped: int = 0
    error: str | None = None
    checked_at: datetime | None = None
    finished_at: datetime | None = None


class AdminUpdateResponse(BaseModel):
    status: str
    stores_checked: list[str] = Field(default_factory=list)
    stores_updated: list[str] = Field(default_factory=list)
    sources_checked: int = 0
    flyers_found: int = 0
    flyers_changed: int = 0
    offers_extracted: int = 0
    offers_added: int = 0
    offers_updated: int = 0
    offers_skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime
    source_results: list[SourceCheckResult] = Field(default_factory=list)


class MetadataResponse(BaseModel):
    last_successful_update: datetime | None = None
    last_attempted_update: datetime | None = None
    last_check: datetime | None = None
    offers_count: int = 0
    active_offers_count: int = 0
    stores: list[str] = Field(default_factory=list)
    stores_supported: list[str] = Field(default_factory=list)
    stores_updated: list[str] = Field(default_factory=list)
    sources_checked: int = 0
    status: str = "unknown"
    errors: list[str] = Field(default_factory=list)
    last_errors: list[str] = Field(default_factory=list)
    next_suggested_check: datetime | None = None
    data_mode: str = "unknown"
    updated_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    provider: str
    database_path: str
    seed_demo_data: bool


class ErrorResponse(BaseModel):
    detail: str


JsonDict = dict[str, Any]
