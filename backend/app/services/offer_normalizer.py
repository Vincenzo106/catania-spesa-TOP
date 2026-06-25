from datetime import date, datetime
import unicodedata
from uuid import uuid4

from app.schemas import ExtractedOffer, ExtractedOfferBatch, OfferCreate
from app.services.catalog import infer_category, normalize_store_name

STANDARD_CATEGORIES = {
    "Produce",
    "Dairy",
    "Meat & Fish",
    "Pantry",
    "Frozen",
    "Drinks",
    "Household",
    "Groceries",
}


def normalize_extracted_batch(
    *,
    store: str,
    source_filename: str,
    extracted_batch: ExtractedOfferBatch,
    source: str,
    source_url: str | None,
    source_type: str | None,
    flyer_url: str | None,
    flyer_title: str | None = None,
    store_location: str | None = None,
    city: str = "Catania",
    is_demo: bool = False,
    extraction_batch_id: str | None = None,
) -> list[OfferCreate]:
    normalized_offers: list[OfferCreate] = []
    updated_at = datetime.utcnow().replace(microsecond=0)
    batch_id = extraction_batch_id or uuid4().hex

    for extracted_offer in extracted_batch.offers:
        normalized = normalize_offer(
            store=store,
            source_filename=source_filename,
            extracted_offer=extracted_offer,
            flyer_url=flyer_url,
            flyer_title=flyer_title or extracted_offer.flyer_title,
            source=source,
            source_url=source_url,
            source_type=source_type,
            store_location=store_location,
            city=city,
            updated_at=updated_at,
            extraction_batch_id=batch_id,
            is_demo=is_demo,
        )
        if normalized is not None:
            normalized_offers.append(normalized)

    return _deduplicate_normalized_offers(normalized_offers)


def normalize_offer(
    *,
    store: str,
    source_filename: str,
    extracted_offer: ExtractedOffer,
    flyer_url: str | None = None,
    flyer_title: str | None = None,
    source: str | None = None,
    source_url: str | None = None,
    source_type: str | None = None,
    valid_from: date | None = None,
    store_location: str | None = None,
    city: str = "Catania",
    updated_at: datetime | None = None,
    extraction_batch_id: str | None = None,
    is_demo: bool = False,
) -> OfferCreate | None:
    product_name = " ".join(extracted_offer.product_name.strip().split())
    if len(product_name) < 2:
        return None

    brand = " ".join(extracted_offer.brand.strip().split()) if extracted_offer.brand else None
    original_price = _round_price(extracted_offer.original_price)
    discounted_price = _round_price(extracted_offer.discounted_price)

    if discounted_price is None and original_price is None:
        return None
    if discounted_price is None:
        discounted_price = original_price
    if discounted_price is None or discounted_price <= 0 or discounted_price > 9999:
        return None
    if original_price is not None and original_price < discounted_price:
        original_price = None

    normalized_store = normalize_store_name(store)
    normalized_product_name = _normalize_product_name(product_name)
    category = extracted_offer.category if extracted_offer.category in STANDARD_CATEGORIES else infer_category(product_name, brand)
    confidence_score = _compute_confidence_score(
        extracted_offer=extracted_offer,
        original_price=original_price,
        discounted_price=discounted_price,
    )
    dedupe_key = build_offer_dedupe_key(
        store=normalized_store,
        normalized_product_name=normalized_product_name,
        discounted_price=discounted_price,
        flyer_valid_until=extracted_offer.flyer_valid_until,
        flyer_url=flyer_url,
        source_url=source_url,
        source_filename=source_filename,
    )

    return OfferCreate(
        store=normalized_store,
        category=category,
        product_name=product_name,
        normalized_product_name=normalized_product_name,
        brand=brand,
        original_price=original_price,
        discounted_price=discounted_price,
        discount_percentage=_compute_discount(original_price, discounted_price),
        unit=extracted_offer.unit,
        quantity=extracted_offer.quantity,
        valid_from=_normalize_date(valid_from or extracted_offer.valid_from),
        flyer_valid_until=_normalize_date(extracted_offer.flyer_valid_until),
        flyer_url=flyer_url,
        flyer_title=flyer_title,
        source_url=source_url,
        source_type=source_type,
        source=source,
        source_filename=source_filename,
        store_location=store_location,
        city=city,
        confidence_score=confidence_score,
        is_demo=is_demo,
        is_active=True,
        extraction_batch_id=extraction_batch_id,
        dedupe_key=dedupe_key,
        updated_at=updated_at,
    )


def build_offer_dedupe_key(
    *,
    store: str,
    normalized_product_name: str,
    discounted_price: float,
    flyer_valid_until: date | None,
    flyer_url: str | None,
    source_url: str | None,
    source_filename: str | None,
) -> str:
    valid_until = flyer_valid_until.isoformat() if flyer_valid_until else ""
    source_hint = flyer_url or source_url or source_filename or "no-source"
    return (
        f"{store.casefold()}|{normalized_product_name}|{discounted_price:.2f}"
        f"|{valid_until}|{source_hint.strip().casefold()}"
    )


def _deduplicate_normalized_offers(offers: list[OfferCreate]) -> list[OfferCreate]:
    unique_by_key: dict[str, OfferCreate] = {}
    for offer in offers:
        unique_by_key[offer.dedupe_key] = offer
    return list(unique_by_key.values())


def _round_price(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _compute_discount(original_price: float | None, discounted_price: float | None) -> float | None:
    if not original_price or not discounted_price:
        return None
    if original_price <= 0 or discounted_price > original_price:
        return None
    return round((1 - (discounted_price / original_price)) * 100, 2)


def _compute_confidence_score(
    *,
    extracted_offer: ExtractedOffer,
    original_price: float | None,
    discounted_price: float | None,
) -> float:
    if extracted_offer.confidence_score is not None:
        return round(float(extracted_offer.confidence_score), 3)

    score = 0.45
    if original_price is not None:
        score += 0.15
    if discounted_price is not None:
        score += 0.2
    if extracted_offer.flyer_valid_until is not None:
        score += 0.1
    if extracted_offer.brand:
        score += 0.05
    if extracted_offer.quantity or extracted_offer.unit:
        score += 0.05
    return round(min(score, 0.99), 3)


def _normalize_date(value: date | None) -> date | None:
    return value


def _normalize_product_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(without_marks.split())
