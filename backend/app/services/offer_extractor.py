import json
from pathlib import Path

from app.schemas import OfferCreate
from app.services.offer_normalizer import normalize_extracted_batch
from app.services.source_registry import TODO_VERIFY_SOURCE_URL


def load_demo_offers_for_source(
    *,
    demo_data_path: Path,
    store: str,
) -> list[OfferCreate]:
    payload = json.loads(demo_data_path.read_text(encoding="utf-8"))
    normalized_store = store.casefold()
    demo_items: list[OfferCreate] = []

    for item in payload:
        if str(item.get("store", "")).strip().casefold() != normalized_store:
            continue
        product_name = str(item.get("product_name") or "").strip()
        normalized_product_name = " ".join(product_name.casefold().split()) or product_name
        discounted_price = float(item.get("discounted_price") or 0)
        flyer_valid_until = item.get("flyer_valid_until")
        flyer_url = item.get("flyer_url") or TODO_VERIFY_SOURCE_URL
        source_filename = item.get("source_filename") or "demo-seed.json"
        dedupe_key = (
            f"{store.casefold()}|{normalized_product_name}|{discounted_price:.2f}|"
            f"{flyer_valid_until or ''}|{str(flyer_url).strip().casefold()}"
        )
        demo_items.append(
            OfferCreate.model_validate(
                {
                    **item,
                    "store": store,
                    "normalized_product_name": normalized_product_name,
                    "flyer_url": flyer_url,
                    "source_url": flyer_url,
                    "source_type": "demo",
                    "source": f"demo:{normalized_store}",
                    "source_filename": source_filename,
                    "city": item.get("city") or "Catania",
                    "confidence_score": item.get("confidence_score") or 0.5,
                    "dedupe_key": item.get("dedupe_key") or dedupe_key,
                    "is_demo": True,
                    "is_active": True,
                }
            )
        )

    return demo_items


__all__ = ["load_demo_offers_for_source", "normalize_extracted_batch"]
