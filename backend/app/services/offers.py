from datetime import date

from app.schemas import ExtractedOffer, OfferCreate
from app.services.catalog import infer_category, normalize_store_name


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


def normalize_offer(
    *,
    store: str,
    source_filename: str,
    extracted_offer: ExtractedOffer,
    is_demo: bool = False,
) -> OfferCreate | None:
    product_name = extracted_offer.product_name.strip()
    brand = extracted_offer.brand.strip() if extracted_offer.brand else None
    original_price = _round_price(extracted_offer.original_price)
    discounted_price = _round_price(extracted_offer.discounted_price)

    if discounted_price is None and original_price is None:
        return None
    if discounted_price is None and original_price is not None:
        discounted_price = original_price
    if original_price is not None and discounted_price is not None and discounted_price > original_price:
        original_price = None

    category = infer_category(product_name, brand)
    normalized_store = normalize_store_name(store)
    discount_percentage = _compute_discount(original_price, discounted_price)

    return OfferCreate(
        store=normalized_store,
        category=category,
        product_name=product_name,
        brand=brand,
        original_price=original_price,
        discounted_price=discounted_price or 0,
        discount_percentage=discount_percentage,
        flyer_valid_until=_normalize_date(extracted_offer.flyer_valid_until),
        source_filename=source_filename,
        is_demo=is_demo,
    )


def _normalize_date(value: date | None) -> date | None:
    return value
