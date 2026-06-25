from dataclasses import dataclass, field
import json
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from app.schemas import SourceRegistryItem, SourceStateRecord
from app.services.flyer_fetcher import FetchResult, FlyerFetchError, FlyerFetcher
from app.services.source_registry import TODO_VERIFY_SOURCE_URL


@dataclass
class DiscoveryResult:
    status: str
    source_key: str
    store: str
    source_url: str
    source_type: str
    content_url: str | None = None
    content_kind: str | None = None
    flyer_title: str | None = None
    flyers_found: int = 0
    change_hint: bool = False
    error: str | None = None
    parser_strategy: str | None = None
    content_metadata: dict[str, str] = field(default_factory=dict)


class SourceDiscoveryService:
    def __init__(self, fetcher: FlyerFetcher, *, max_flyers_per_store: int):
        self.fetcher = fetcher
        self.max_flyers_per_store = max_flyers_per_store

    def discover(
        self,
        source: SourceRegistryItem | SourceStateRecord,
        previous_state: SourceStateRecord | None,
    ) -> DiscoveryResult:
        if not source.active:
            return DiscoveryResult(
                status="inactive",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                parser_strategy=source.parser_strategy,
            )

        if _is_placeholder_url(source.source_url):
            return DiscoveryResult(
                status="pending_configuration",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                error="Fonte non ancora configurata con un URL reale.",
                parser_strategy=source.parser_strategy,
            )

        if source.source_type == "manual":
            return DiscoveryResult(
                status="manual_only",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                parser_strategy=source.parser_strategy,
            )

        strategy = source.parser_strategy or ""
        if strategy == "crai_store_flyer_page":
            return self._discover_crai_store_page(source, previous_state)
        if strategy == "eurospin_store_page":
            return self._discover_eurospin_store_page(source, previous_state)

        if source.direct_flyer_url and not _is_placeholder_url(source.direct_flyer_url):
            return DiscoveryResult(
                status="candidate_found",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                content_url=source.direct_flyer_url,
                content_kind=_guess_content_kind(source.direct_flyer_url, source.source_type),
                flyers_found=1,
                change_hint=source.direct_flyer_url != (previous_state.last_seen_flyer_url if previous_state else None),
                parser_strategy=source.parser_strategy,
            )

        if source.source_type in {"pdf", "image"}:
            return DiscoveryResult(
                status="candidate_found",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                content_url=source.source_url,
                content_kind=source.source_type,
                flyers_found=1,
                change_hint=source.source_url != (previous_state.last_seen_flyer_url if previous_state else None),
                parser_strategy=source.parser_strategy,
            )

        if source.source_type == "api":
            return self._discover_from_api(source, previous_state)

        if source.source_type == "webpage":
            return self._discover_from_webpage(source, previous_state)

        return DiscoveryResult(
            status="unsupported_source_type",
            source_key=source.source_key,
            store=source.store,
            source_url=source.source_url,
            source_type=source.source_type,
            error=f"Tipo sorgente non supportato: {source.source_type}",
            parser_strategy=source.parser_strategy,
        )

    def _discover_crai_store_page(
        self,
        source: SourceRegistryItem | SourceStateRecord,
        previous_state: SourceStateRecord | None,
    ) -> DiscoveryResult:
        try:
            fetched = self.fetcher.fetch_text(source.source_url)
        except FlyerFetchError as exc:
            return self._error_result(source, str(exc))

        soup = BeautifulSoup(fetched.text or "", "html.parser")
        flyer_title = _extract_page_title(soup) or source.store_location or source.store
        pdf_candidates = _extract_crai_pdf_candidates(soup=soup, fetched=fetched, fetcher=self.fetcher)
        if not pdf_candidates:
            return DiscoveryResult(
                status="no_candidate",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                flyer_title=flyer_title,
                error="Nessun PDF volantino CRAI rilevato nella pagina del punto vendita.",
                parser_strategy=source.parser_strategy,
            )

        best_candidate = pdf_candidates[0]
        return DiscoveryResult(
            status="candidate_found",
            source_key=source.source_key,
            store=source.store,
            source_url=source.source_url,
            source_type=source.source_type,
            content_url=best_candidate["url"],
            content_kind="pdf",
            flyer_title=best_candidate.get("title") or flyer_title,
            flyers_found=len(pdf_candidates),
            change_hint=best_candidate["url"] != (previous_state.last_seen_flyer_url if previous_state else None),
            parser_strategy=source.parser_strategy,
            content_metadata={"flyer_url": best_candidate["url"]},
        )

    def _discover_eurospin_store_page(
        self,
        source: SourceRegistryItem | SourceStateRecord,
        previous_state: SourceStateRecord | None,
    ) -> DiscoveryResult:
        try:
            fetched = self.fetcher.fetch_text(source.source_url)
        except FlyerFetchError as exc:
            return self._error_result(source, str(exc))

        soup = BeautifulSoup(fetched.text or "", "html.parser")
        flyer_title = _extract_page_title(soup) or source.store_location or source.store
        viewer_candidates = _extract_eurospin_viewer_candidates(
            soup=soup,
            fetched=fetched,
            fetcher=self.fetcher,
        )
        if not viewer_candidates:
            return DiscoveryResult(
                status="no_candidate",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                flyer_title=flyer_title,
                error="Nessun viewer o volantino dedicato Eurospin rilevato nella pagina del punto vendita.",
                parser_strategy=source.parser_strategy,
            )

        best_candidate = viewer_candidates[0]
        query = parse_qs(urlparse(best_candidate["url"]).query)
        store_code = (query.get("codice_pv") or query.get("store") or [""])[0]
        promo_code = (query.get("promo_code") or query.get("code") or [""])[0]
        public_promo_url = (
            f"https://www.eurospin.it/volantino/promotion?code={promo_code}"
            if promo_code
            else best_candidate["url"]
        )
        return DiscoveryResult(
            status="candidate_found",
            source_key=source.source_key,
            store=source.store,
            source_url=source.source_url,
            source_type=source.source_type,
            content_url=best_candidate["url"],
            content_kind="eurospin-viewer",
            flyer_title=best_candidate.get("title") or flyer_title,
            flyers_found=len(viewer_candidates),
            change_hint=best_candidate["url"] != (previous_state.last_seen_flyer_url if previous_state else None),
            parser_strategy=source.parser_strategy,
            content_metadata={
                "viewer_url": best_candidate["url"],
                "store_code": store_code,
                "promotion_code": promo_code,
                "flyer_url": public_promo_url,
            },
        )

    def _discover_from_api(
        self,
        source: SourceRegistryItem | SourceStateRecord,
        previous_state: SourceStateRecord | None,
    ) -> DiscoveryResult:
        try:
            fetched = self.fetcher.fetch_text(source.source_url)
        except FlyerFetchError as exc:
            return self._error_result(source, str(exc))

        candidate_urls = _extract_urls_from_json_payload(
            fetched.text or "",
            base_url=fetched.final_url,
            fetcher=self.fetcher,
        )
        if candidate_urls:
            candidate_url = candidate_urls[0]
            return DiscoveryResult(
                status="candidate_found",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                content_url=candidate_url,
                content_kind=_guess_content_kind(candidate_url, "api"),
                flyers_found=len(candidate_urls),
                change_hint=candidate_url != (previous_state.last_seen_flyer_url if previous_state else None),
                parser_strategy=source.parser_strategy,
            )

        return DiscoveryResult(
            status="no_candidate",
            source_key=source.source_key,
            store=source.store,
            source_url=source.source_url,
            source_type=source.source_type,
            error="Nessun URL volantino rilevato dalla risposta API.",
            parser_strategy=source.parser_strategy,
        )

    def _discover_from_webpage(
        self,
        source: SourceRegistryItem | SourceStateRecord,
        previous_state: SourceStateRecord | None,
    ) -> DiscoveryResult:
        try:
            fetched = self.fetcher.fetch_text(source.source_url)
        except FlyerFetchError as exc:
            return self._error_result(source, str(exc))

        soup = BeautifulSoup(fetched.text or "", "html.parser")
        flyer_title = _extract_page_title(soup)
        candidate_urls = _extract_flyer_candidates(
            soup=soup,
            fetched=fetched,
            source=source,
            fetcher=self.fetcher,
            max_candidates=self.max_flyers_per_store,
        )
        if candidate_urls:
            candidate_url = candidate_urls[0]
            return DiscoveryResult(
                status="candidate_found",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                content_url=candidate_url,
                content_kind=_guess_content_kind(candidate_url, "webpage"),
                flyer_title=flyer_title,
                flyers_found=len(candidate_urls),
                change_hint=candidate_url != (previous_state.last_seen_flyer_url if previous_state else None),
                parser_strategy=source.parser_strategy,
            )

        if _page_looks_like_text_offers(fetched):
            return DiscoveryResult(
                status="html_offers_detected",
                source_key=source.source_key,
                store=source.store,
                source_url=source.source_url,
                source_type=source.source_type,
                content_url=fetched.final_url,
                content_kind="html",
                flyer_title=flyer_title,
                flyers_found=1,
                change_hint=fetched.content_hash != (previous_state.last_seen_hash if previous_state else None),
                parser_strategy=source.parser_strategy,
            )

        return DiscoveryResult(
            status="no_candidate",
            source_key=source.source_key,
            store=source.store,
            source_url=source.source_url,
            source_type=source.source_type,
            flyer_title=flyer_title,
            error="Nessun volantino PDF/immagine o elenco offerte testuale rilevato.",
            parser_strategy=source.parser_strategy,
        )

    @staticmethod
    def _error_result(
        source: SourceRegistryItem | SourceStateRecord,
        error: str,
    ) -> DiscoveryResult:
        return DiscoveryResult(
            status="fetch_failed",
            source_key=source.source_key,
            store=source.store,
            source_url=source.source_url,
            source_type=source.source_type,
            error=error,
            parser_strategy=source.parser_strategy,
        )


def _extract_page_title(soup: BeautifulSoup) -> str | None:
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        return str(og_title["content"]).strip()
    return None


def _extract_crai_pdf_candidates(
    *,
    soup: BeautifulSoup,
    fetched: FetchResult,
    fetcher: FlyerFetcher,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []

    for node in soup.find_all("a"):
        href = node.get("href")
        label = node.get_text(" ", strip=True)
        if not href:
            continue
        resolved = fetcher.resolve_url(fetched.final_url, href)
        if not resolved.casefold().endswith(".pdf"):
            continue
        score = _score_crai_pdf_candidate(resolved, label)
        if score <= 0:
            continue
        candidates.append({"url": resolved, "title": label or "Volantino CRAI", "score": str(score)})

    html_text = fetched.text or ""
    for title, url in re.findall(r'"titolo":"([^"]+)".{0,1500}?"url":"([^"]+\.pdf)"', html_text):
        resolved = fetcher.resolve_url(fetched.final_url, url.replace("\\/", "/"))
        score = _score_crai_pdf_candidate(resolved, title)
        if score <= 0:
            continue
        candidates.append({"url": resolved, "title": title, "score": str(score)})

    unique: dict[str, dict[str, str]] = {}
    for candidate in candidates:
        existing = unique.get(candidate["url"])
        if existing is None or int(candidate["score"]) > int(existing["score"]):
            unique[candidate["url"]] = candidate

    return sorted(unique.values(), key=lambda item: int(item["score"]), reverse=True)


def _score_crai_pdf_candidate(url: str, label: str) -> int:
    haystack = f"{url} {label}".casefold()
    if "company profile" in haystack or "prontuario" in haystack or "codice etico" in haystack:
        return -10
    score = 0
    if "leggi il volantino" in haystack:
        score += 10
    if "volantino" in haystack:
        score += 8
    if "promo" in haystack or "offert" in haystack:
        score += 4
    if "crai" in haystack:
        score += 2
    if "strapi.crai.it/uploads/" in haystack:
        score += 2
    return score


def _extract_eurospin_viewer_candidates(
    *,
    soup: BeautifulSoup,
    fetched: FetchResult,
    fetcher: FlyerFetcher,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for node in soup.find_all("a"):
        href = node.get("href")
        if not href:
            continue
        resolved = fetcher.resolve_url(fetched.final_url, href)
        if "volantino-store-eurospin" not in resolved:
            continue
        label = node.get_text(" ", strip=True)
        score = 10
        if "volantino" in label.casefold():
            score += 4
        candidates.append({"url": resolved, "title": label or "Volantino Eurospin", "score": str(score)})

    html_text = fetched.text or ""
    for url in re.findall(r"https://www\.eurospin\.it/volantino-store-eurospin/\?[^\"'<>\\s]+", html_text):
        candidates.append({"url": url, "title": "Volantino Eurospin", "score": "8"})

    unique: dict[str, dict[str, str]] = {}
    for candidate in candidates:
        existing = unique.get(candidate["url"])
        if existing is None or int(candidate["score"]) > int(existing["score"]):
            unique[candidate["url"]] = candidate

    return sorted(unique.values(), key=lambda item: int(item["score"]), reverse=True)


def _extract_flyer_candidates(
    *,
    soup: BeautifulSoup,
    fetched: FetchResult,
    source: SourceRegistryItem | SourceStateRecord,
    fetcher: FlyerFetcher,
    max_candidates: int,
) -> list[str]:
    selector_candidates: list[str] = []
    selectors = source.selectors or {}
    if selectors.get("flyer_link"):
        for node in soup.select(selectors["flyer_link"]):
            href = node.get("href") or node.get("src")
            if href:
                selector_candidates.append(fetcher.resolve_url(fetched.final_url, href))

    generic_candidates: list[str] = []
    for node in soup.find_all(["a", "img", "source"]):
        candidate = node.get("href") or node.get("src")
        if not candidate:
            continue
        resolved = fetcher.resolve_url(fetched.final_url, candidate)
        if _looks_like_flyer_asset(
            url=resolved,
            text=node.get_text(" ", strip=True),
            city_filter=source.city_filter,
        ):
            generic_candidates.append(resolved)

    for match in re.findall(r"https?://[^\s\"'<>]+", fetched.text or ""):
        if _looks_like_flyer_asset(url=match, text="", city_filter=source.city_filter):
            generic_candidates.append(match)

    combined = selector_candidates + generic_candidates
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in combined:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique[:max_candidates]


def _extract_urls_from_json_payload(
    payload: str,
    *,
    base_url: str,
    fetcher: FlyerFetcher,
) -> list[str]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []

    urls: list[str] = []

    def visit(node):
        if isinstance(node, dict):
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
        elif isinstance(node, str):
            if _looks_like_flyer_asset(url=node, text="", city_filter=None):
                urls.append(fetcher.resolve_url(base_url, node))

    visit(parsed)
    return urls


def _looks_like_flyer_asset(*, url: str, text: str, city_filter: str | None) -> bool:
    parsed = urlparse(url)
    haystack = f"{parsed.path} {parsed.query} {text}".casefold()
    asset_like = any(
        token in haystack
        for token in ["volantino", "offerte", "promo", ".pdf", ".jpg", ".png", ".jpeg", "promotion?code="]
    )
    if not asset_like:
        return False
    if city_filter and city_filter.casefold() in haystack:
        return True
    return True


def _page_looks_like_text_offers(fetched: FetchResult) -> bool:
    haystack = (fetched.text or "").casefold()
    has_price = bool(re.search(r"\d+[,.]\d{2}", haystack))
    has_offer_terms = any(token in haystack for token in ["offerta", "promo", "sconto", "volantino"])
    return has_price and has_offer_terms


def _guess_content_kind(url: str, fallback: str) -> str:
    lower = url.casefold()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".png") or lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".webp"):
        return "image"
    return fallback


def _is_placeholder_url(value: str | None) -> bool:
    if not value:
        return True
    return value.startswith(TODO_VERIFY_SOURCE_URL)
