import base64
import json
from abc import ABC, abstractmethod
from io import BytesIO
from os import fspath
from pathlib import Path

from openai import OpenAI
from PIL import Image
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError

from app.config import Settings
from app.schemas import ExtractedOffer, ExtractedOfferBatch


EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "offers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "brand": {"type": ["string", "null"]},
                    "original_price": {"type": ["number", "null"]},
                    "discounted_price": {"type": ["number", "null"]},
                    "flyer_valid_until": {
                        "type": ["string", "null"],
                        "description": "ISO 8601 date in YYYY-MM-DD format.",
                    },
                },
                "required": [
                    "product_name",
                    "brand",
                    "original_price",
                    "discounted_price",
                    "flyer_valid_until",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["offers"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """
You extract supermarket offers from Italian promotional flyers.
Return only valid JSON matching the provided schema.

Rules:
- Extract one object per distinct purchasable product offer.
- Use the main headline price for each product.
- Keep product_name in Italian if the flyer is in Italian.
- brand must be null when it is not clearly visible.
- Prices must be numeric values with a dot decimal separator and no currency symbol.
- flyer_valid_until must be YYYY-MM-DD when visible, otherwise null.
- Never invent products, prices, brands, or dates.
- Ignore loyalty-only microtext unless it is the only visible discounted price.
""".strip()


class VisionExtractionError(RuntimeError):
    """Raised when flyer extraction fails."""


class VisionExtractor(ABC):
    @abstractmethod
    def extract(self, *, file_path: Path, store: str) -> ExtractedOfferBatch:
        raise NotImplementedError


class MockVisionExtractor(VisionExtractor):
    def extract(self, *, file_path: Path, store: str) -> ExtractedOfferBatch:
        filename = file_path.name.casefold()
        if "validation" in filename or "sample" in filename:
            return ExtractedOfferBatch(
                offers=[
                    ExtractedOffer(
                        product_name="Pasta Rummo 500g",
                        brand="Rummo",
                        original_price=1.99,
                        discounted_price=1.09,
                        flyer_valid_until="2026-06-30",
                    ),
                    ExtractedOffer(
                        product_name="Latte UHT 1L",
                        brand="Parmalat",
                        original_price=1.59,
                        discounted_price=0.99,
                        flyer_valid_until="2026-06-30",
                    ),
                    ExtractedOffer(
                        product_name="Detersivo Casa 2L",
                        brand="Fresh Clean",
                        original_price=5.49,
                        discounted_price=3.79,
                        flyer_valid_until="2026-06-30",
                    ),
                ]
            )

        default_offers = {
            "coop": [
                ("Pasta Barilla 500g", "Barilla", 1.89, 0.99),
                ("Latte UHT 1L", "Parmalat", 1.79, 1.19),
                ("Pomodori Ciliegino 500g", None, 2.79, 1.69),
            ],
            "conad": [
                ("Banane al kg", "Chiquita", 2.29, 1.49),
                ("Carta Igienica 12 rotoli", "Conad", 6.99, 4.99),
                ("Succo ACE 1L", "Yoga", 2.49, 1.59),
            ],
            "famila": [
                ("Passata di Pomodoro 700g", "Valfrutta", 2.19, 1.19),
                ("Caffè Macinato 250g", "Splendid", 4.99, 3.49),
                ("Mozzarella 125g", "Santa Lucia", 1.49, 0.99),
            ],
        }
        library = default_offers.get(store.casefold(), default_offers["coop"])
        return ExtractedOfferBatch(
            offers=[
                ExtractedOffer(
                    product_name=product_name,
                    brand=brand,
                    original_price=original_price,
                    discounted_price=discounted_price,
                    flyer_valid_until="2026-06-30",
                )
                for product_name, brand, original_price, discounted_price in library
            ]
        )


class OpenAIVisionExtractor(VisionExtractor):
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise VisionExtractionError(
                "OPENAI_API_KEY is required when VISION_PROVIDER=openai."
            )
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.request_timeout_seconds,
        )

    def extract(self, *, file_path: Path, store: str) -> ExtractedOfferBatch:
        suffix = file_path.suffix.casefold()
        if suffix == ".pdf":
            return self._extract_from_pdf(file_path=file_path, store=store)
        return self._extract_from_visual_inputs(
            store=store,
            visual_inputs=[self._build_image_input(file_path)],
            page_context=file_path.name,
        )

    def _extract_from_pdf(self, *, file_path: Path, store: str) -> ExtractedOfferBatch:
        page_inputs = self._build_pdf_page_inputs(file_path)
        all_offers: list[ExtractedOffer] = []

        for start in range(0, len(page_inputs), self.settings.openai_pdf_pages_per_request):
            batch = page_inputs[start : start + self.settings.openai_pdf_pages_per_request]
            page_label = f"{file_path.name} pages {start + 1}-{start + len(batch)}"
            batch_result = self._extract_from_visual_inputs(
                store=store,
                visual_inputs=batch,
                page_context=page_label,
            )
            all_offers.extend(batch_result.offers)

        return ExtractedOfferBatch(offers=_deduplicate_offers(all_offers))

    def _extract_from_visual_inputs(
        self,
        *,
        store: str,
        visual_inputs: list[dict[str, str]],
        page_context: str,
    ) -> ExtractedOfferBatch:
        user_prompt = (
            f"This flyer belongs to the supermarket '{store}'. "
            f"The attached pages are from {page_context}. "
            "Extract every distinct product offer visible in these pages and avoid duplicates."
        )
        content = [{"type": "input_text", "text": user_prompt}, *visual_inputs]
        try:
            response = self.client.responses.create(
                model=self.settings.openai_model,
                instructions=SYSTEM_PROMPT,
                input=[{"role": "user", "content": content}],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "flyer_offer_batch",
                        "strict": True,
                        "schema": EXTRACTION_JSON_SCHEMA,
                    }
                },
            )
            payload = json.loads(response.output_text)
            return ExtractedOfferBatch.model_validate(payload)
        except Exception as exc:  # pragma: no cover - defensive boundary for API failures
            raise VisionExtractionError(f"Vision extraction failed: {exc}") from exc

    def _build_image_input(self, file_path: Path) -> dict[str, str]:
        data_url = _image_file_to_data_url(
            file_path,
            max_dimension=self.settings.openai_image_max_px,
        )
        return {
            "type": "input_image",
            "image_url": data_url,
            "detail": "high",
        }

    def _build_pdf_page_inputs(self, file_path: Path) -> list[dict[str, str]]:
        try:
            pages = convert_from_path(
                pdf_path=fspath(file_path),
                dpi=self.settings.pdf_render_dpi,
                fmt="jpeg",
                thread_count=1,
                poppler_path=fspath(self.settings.poppler_path)
                if self.settings.poppler_path
                else None,
            )
        except PDFInfoNotInstalledError as exc:
            raise VisionExtractionError(
                "PDF conversion requires Poppler. Install Poppler on Windows and set POPPLER_PATH "
                "to the Poppler bin directory if it is not already on PATH."
            ) from exc
        except (PDFPageCountError, PDFSyntaxError, OSError) as exc:
            raise VisionExtractionError(f"PDF conversion failed for {file_path.name}: {exc}") from exc

        if not pages:
            raise VisionExtractionError(f"No pages were rendered from {file_path.name}.")

        return [
            {
                "type": "input_image",
                "image_url": _pil_image_to_data_url(page, max_dimension=self.settings.openai_image_max_px),
                "detail": "high",
            }
            for page in pages
        ]


def build_vision_extractor(settings: Settings) -> VisionExtractor:
    if settings.vision_provider == "openai":
        return OpenAIVisionExtractor(settings)
    return MockVisionExtractor()


def _image_file_to_data_url(file_path: Path, *, max_dimension: int) -> str:
    with Image.open(file_path) as image:
        return _pil_image_to_data_url(image, max_dimension=max_dimension)


def _pil_image_to_data_url(image: Image.Image, *, max_dimension: int) -> str:
    prepared_image = image.convert("RGB")
    prepared_image.thumbnail((max_dimension, max_dimension))
    buffer = BytesIO()
    prepared_image.save(buffer, format="JPEG", quality=90, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def _deduplicate_offers(offers: list[ExtractedOffer]) -> list[ExtractedOffer]:
    unique_offers: list[ExtractedOffer] = []
    seen: set[tuple[str, str, float | None, float | None, str | None]] = set()

    for offer in offers:
        key = (
            " ".join(offer.product_name.casefold().split()),
            " ".join((offer.brand or "").casefold().split()),
            offer.original_price,
            offer.discounted_price,
            offer.flyer_valid_until.isoformat() if offer.flyer_valid_until else None,
        )
        if key in seen:
            continue
        seen.add(key)
        unique_offers.append(offer)

    return unique_offers
