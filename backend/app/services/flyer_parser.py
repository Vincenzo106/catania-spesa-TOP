import base64
from datetime import date
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from app.services.flyer_fetcher import FetchResult, FlyerFetcher
from app.services.source_discovery import DiscoveryResult
from app.services.vision import VisionExtractionError, VisionExtractor
from app.schemas import ExtractedOffer, ExtractedOfferBatch


class FlyerParserError(RuntimeError):
    """Raised when a flyer cannot be parsed into reliable offers."""


class FlyerParser:
    def __init__(self, vision_extractor: VisionExtractor, fetcher: FlyerFetcher):
        self.vision_extractor = vision_extractor
        self.fetcher = fetcher

    def parse(
        self,
        *,
        store: str,
        discovery: DiscoveryResult,
        fetched: FetchResult,
    ) -> ExtractedOfferBatch:
        if discovery.content_kind in {"pdf", "image"}:
            if not fetched.local_path:
                raise FlyerParserError("Nessun file locale disponibile per il parsing del volantino.")
            try:
                return self.vision_extractor.extract(file_path=fetched.local_path, store=store)
            except VisionExtractionError as exc:
                raise FlyerParserError(str(exc)) from exc

        if discovery.content_kind == "eurospin-viewer":
            return self._parse_eurospin_viewer(discovery=discovery, fetched=fetched)

        if discovery.content_kind == "html":
            return self._parse_html_offers(
                html=fetched.text or "",
                flyer_title=discovery.flyer_title,
            )

        raise FlyerParserError(f"Formato non supportato dal parser: {discovery.content_kind}")

    def _parse_html_offers(self, *, html: str, flyer_title: str | None) -> ExtractedOfferBatch:
        soup = BeautifulSoup(html, "html.parser")
        valid_until = _extract_valid_until(soup.get_text(" ", strip=True))
        offers: list[ExtractedOffer] = []

        for line in _iter_candidate_lines(soup):
            parsed_offer = _parse_offer_line(line, valid_until=valid_until, flyer_title=flyer_title)
            if parsed_offer is not None:
                offers.append(parsed_offer)

        return ExtractedOfferBatch(offers=_deduplicate_html_offers(offers))

    def _parse_eurospin_viewer(
        self,
        *,
        discovery: DiscoveryResult,
        fetched: FetchResult,
    ) -> ExtractedOfferBatch:
        viewer_url = discovery.content_metadata.get("viewer_url") or discovery.content_url or fetched.final_url
        promotion_code = discovery.content_metadata.get("promotion_code")
        store_code = discovery.content_metadata.get("store_code")

        if not promotion_code or not store_code:
            query = parse_qs(urlparse(viewer_url).query)
            promotion_code = promotion_code or (query.get("promo_code") or query.get("code") or [""])[0]
            store_code = store_code or (query.get("codice_pv") or query.get("store") or [""])[0]

        if not promotion_code or not store_code:
            raise FlyerParserError("Parametro store_code o promotion_code mancante nella sorgente Eurospin.")

        api_config = self._extract_eurospin_api_config(fetched.text or "", viewer_url)
        token = self._fetch_eurospin_token(api_config)
        api_headers = {"Authorization": f"Bearer {token}"}
        api_base = f"{api_config['api_server'].rstrip('/')}/{api_config['api_path'].strip('/')}"

        store_payload = self.fetcher.fetch_json(
            f"{api_base}/stores",
            headers=api_headers,
            params={"code": store_code},
        ).json_data
        if not isinstance(store_payload, list) or not store_payload:
            raise FlyerParserError(f"Nessun punto vendita Eurospin trovato per il codice {store_code}.")
        store_info = store_payload[0]
        store_alias = str(store_info.get("alias") or "").strip()
        if not store_alias:
            raise FlyerParserError("Alias punto vendita Eurospin non disponibile.")

        promotions_payload = self.fetcher.fetch_json(
            f"{api_base}/stores/{store_alias}/promotions",
            headers=api_headers,
        ).json_data
        if not isinstance(promotions_payload, list) or not promotions_payload:
            raise FlyerParserError("Nessuna promozione Eurospin disponibile per il punto vendita.")

        promotion = _select_eurospin_promotion(promotions_payload, promotion_code)
        promotion_alias = str(promotion.get("alias") or "").strip()
        if not promotion_alias:
            raise FlyerParserError("Alias promozione Eurospin non disponibile.")

        total_pages = 1
        page = 0
        offers: list[ExtractedOffer] = []
        while page < total_pages:
            products_payload = self.fetcher.fetch_json(
                f"{api_base}/promotions/{promotion_alias}/stores/{store_alias}/products",
                headers=api_headers,
                params={"page": page, "size": 200},
            ).json_data
            elements = products_payload.get("elements", []) if isinstance(products_payload, dict) else []
            total_pages = int(products_payload.get("totalPages") or 1) if isinstance(products_payload, dict) else 1
            for product in elements:
                parsed_offer = _parse_eurospin_product(product, promotion)
                if parsed_offer is not None:
                    offers.append(parsed_offer)
            page += 1

        if not offers:
            raise FlyerParserError("Nessuna offerta Eurospin valida estratta dall'API del viewer.")

        return ExtractedOfferBatch(offers=_deduplicate_html_offers(offers))

    def _extract_eurospin_api_config(self, viewer_html: str, viewer_url: str) -> dict[str, str]:
        soup = BeautifulSoup(viewer_html, "html.parser")
        iframe = soup.find("iframe")
        if iframe and iframe.get("src"):
            nested_viewer_url = self.fetcher.resolve_url(viewer_url, iframe.get("src"))
            nested_viewer = self.fetcher.fetch_text(nested_viewer_url)
            viewer_url = nested_viewer.final_url
            viewer_html = nested_viewer.text or ""
            soup = BeautifulSoup(viewer_html, "html.parser")

        script_src = None
        for node in soup.find_all("script"):
            src = node.get("src")
            if src and "/smt-digitalflyer/assets/index-" in src and src.endswith(".js"):
                script_src = src
                break
        if not script_src:
            raise FlyerParserError("Asset JavaScript del viewer Eurospin non trovato.")

        asset_url = self.fetcher.resolve_url(viewer_url, script_src)
        asset_text = self.fetcher.fetch_text(asset_url).text or ""
        api_server = _extract_js_config_value(asset_text, "apiServer")
        api_authorization_code = _extract_js_config_value(asset_text, "apiAuthorizationCode")
        api_path = _extract_js_config_value(asset_text, "apiPath")
        if not api_server or not api_authorization_code or not api_path:
            raise FlyerParserError("Configurazione API Eurospin non trovata nell'asset del viewer.")

        return {
            "api_server": api_server,
            "api_authorization_code": api_authorization_code,
            "api_path": api_path,
        }

    def _fetch_eurospin_token(self, api_config: dict[str, str]) -> str:
        auth_header = base64.b64encode(api_config["api_authorization_code"].encode("utf-8")).decode("utf-8")
        token_payload = self.fetcher.fetch_json(
            f"{api_config['api_server'].rstrip('/')}/oauth/token",
            method="POST",
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        ).json_data
        token = token_payload.get("access_token") if isinstance(token_payload, dict) else None
        if not token:
            raise FlyerParserError("Token OAuth Eurospin non disponibile.")
        return str(token)


def _iter_candidate_lines(soup: BeautifulSoup) -> list[str]:
    raw_lines = [text.strip() for text in soup.stripped_strings]
    candidate_lines: list[str] = []
    for line in raw_lines:
        normalized = " ".join(line.split())
        if len(normalized) < 8:
            continue
        if not re.search(r"\d+[,.]\d{2}", normalized):
            continue
        candidate_lines.append(normalized)
    return candidate_lines


def _parse_offer_line(
    line: str,
    *,
    valid_until: date | None,
    flyer_title: str | None,
) -> ExtractedOffer | None:
    price_strings = re.findall(r"\d+[,.]\d{2}", line)
    if not price_strings:
        return None

    price_values = [_to_float(item) for item in price_strings]
    discounted_price = min(price_values)
    original_price = max(price_values) if len(price_values) > 1 else None

    product = re.sub(r"\d+[,.]\d{2}", " ", line)
    product = re.sub(r"€|euro|offerta|promo|sconto|volantino", " ", product, flags=re.IGNORECASE)
    product = re.sub(r"[-:;,.]+", " ", product)
    product = " ".join(product.split())

    if len(product) < 4 or not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", product):
        return None

    return ExtractedOffer(
        product_name=product,
        original_price=original_price if original_price != discounted_price else None,
        discounted_price=discounted_price,
        flyer_valid_until=valid_until,
        flyer_title=flyer_title,
        confidence_score=0.45 if original_price is None else 0.58,
    )


def _parse_eurospin_product(product: dict, promotion: dict) -> ExtractedOffer | None:
    properties = _properties_to_map(product.get("properties", []))

    product_name = _first_property_value(properties, "TITLE") or str(product.get("description") or "").strip()
    if not product_name:
        return None

    discounted_price = _to_float_from_property(properties, "END-PRICE")
    if discounted_price is None:
        return None

    original_price = _to_float_from_property(properties, "INITIAL-PRICE")
    valid_from = _parse_compact_date(_first_property_value(properties, "START-DATE-VALIDITY")) or _parse_compact_date(
        str(promotion.get("startDate") or "")
    )
    valid_until = _parse_compact_date(_first_property_value(properties, "END-DATE-VALIDITY")) or _parse_compact_date(
        str(promotion.get("endDate") or "")
    )
    category = _first_property_value(properties, "CATEGORY")
    quantity = _first_property_value(properties, "DESCRIPTION")
    unit = _first_property_value(properties, "MEASURE-UNIT") or _first_property_value(properties, "SELL-UNIT")
    brand = _first_property_value(properties, "BRAND") or _first_property_value(properties, "MARK")
    discount_rate = _to_float_from_property(properties, "DISCOUNT-RATE")

    return ExtractedOffer(
        product_name=" ".join(product_name.split()),
        brand=" ".join(brand.split()) if brand else None,
        original_price=original_price,
        discounted_price=discounted_price,
        flyer_valid_until=valid_until,
        category=category,
        unit=unit,
        quantity=quantity,
        valid_from=valid_from,
        flyer_title=str(promotion.get("description") or "").strip() or None,
        confidence_score=0.98 if discount_rate is not None else 0.92,
    )


def _properties_to_map(properties: list[dict]) -> dict[str, list]:
    mapped: dict[str, list] = {}
    for item in properties:
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        mapped[code] = item.get("values", [])
    return mapped


def _first_property_value(properties: dict[str, list], code: str) -> str | None:
    values = properties.get(code) or []
    if not values:
        return None
    value = values[0]
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return text or None
    return None


def _to_float_from_property(properties: dict[str, list], code: str) -> float | None:
    raw = _first_property_value(properties, code)
    if raw is None:
        return None
    try:
        return round(float(str(raw).replace(",", ".")), 2)
    except ValueError:
        return None


def _select_eurospin_promotion(promotions: list[dict], promotion_code: str) -> dict:
    normalized_target = promotion_code.strip().casefold()
    for promotion in promotions:
        code = str(promotion.get("code") or "").strip().casefold()
        alias = str(promotion.get("alias") or "").strip().casefold()
        if normalized_target and normalized_target in {code, alias}:
            return promotion
    return promotions[0]


def _extract_js_config_value(asset_text: str, key: str) -> str | None:
    match = re.search(rf'{re.escape(key)}:"([^"]+)"', asset_text)
    if match:
        return match.group(1)
    return None


def _deduplicate_html_offers(offers: list[ExtractedOffer]) -> list[ExtractedOffer]:
    unique: dict[tuple[str, float | None, date | None], ExtractedOffer] = {}
    for offer in offers:
        key = (
            " ".join(offer.product_name.casefold().split()),
            offer.discounted_price,
            offer.flyer_valid_until,
        )
        unique[key] = offer
    return list(unique.values())


def _extract_valid_until(text: str) -> date | None:
    patterns = [
        r"fino al (\d{2}/\d{2}/\d{4})",
        r"valido fino al (\d{2}/\d{2}/\d{4})",
        r"valido dal \d{2}/\d{2}/\d{4} al (\d{2}/\d{2}/\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return date.fromisoformat(_italian_date_to_iso(match.group(1)))
            except ValueError:
                continue
    return None


def _parse_compact_date(value: str | None) -> date | None:
    if not value:
        return None
    match = re.match(r"^(\d{4})(\d{2})(\d{2})", value)
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _italian_date_to_iso(value: str) -> str:
    day, month, year = value.split("/")
    return f"{year}-{month}-{day}"


def _to_float(value: str) -> float:
    return round(float(value.replace(".", "").replace(",", ".")), 2)
