from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import Settings


class FlyerFetchError(RuntimeError):
    """Raised when a remote flyer source cannot be fetched safely."""


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    content_type: str
    content_hash: str
    text: str | None = None
    local_path: Path | None = None
    json_data: Any | None = None


class FlyerFetcher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._robots_cache: dict[str, RobotFileParser] = {}

    def fetch_text(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResult:
        response = self.request("GET", url, headers=headers)
        content = response.text
        return FetchResult(
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            content_hash=sha256(content.encode("utf-8", errors="ignore")).hexdigest(),
            text=content,
        )

    def fetch_json(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> FetchResult:
        response = self.request(
            method,
            url,
            headers=headers,
            params=params,
            data=data,
            json_body=json_body,
        )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise FlyerFetchError(f"Risposta JSON non valida da {url}: {exc}") from exc
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return FetchResult(
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            content_hash=sha256(canonical.encode("utf-8")).hexdigest(),
            text=canonical,
            json_data=payload,
        )

    def download_binary(
        self,
        url: str,
        download_dir: Path,
        *,
        headers: dict[str, str] | None = None,
    ) -> FetchResult:
        response = self.request("GET", url, headers=headers)
        suffix = _infer_suffix(
            url=str(response.url),
            content_type=response.headers.get("content-type", ""),
        )
        download_dir.mkdir(parents=True, exist_ok=True)
        destination = download_dir / (
            f"remote-{sha256(str(response.url).encode('utf-8')).hexdigest()[:12]}{suffix}"
        )
        destination.write_bytes(response.content)
        return FetchResult(
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            content_hash=sha256(response.content).hexdigest(),
            local_path=destination,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> httpx.Response:
        self._ensure_allowed(url)
        last_error: Exception | None = None
        merged_headers = {"User-Agent": self.settings.update_user_agent}
        if headers:
            merged_headers.update(headers)

        for _attempt in range(2):
            try:
                with httpx.Client(
                    timeout=self.settings.update_timeout_seconds,
                    follow_redirects=True,
                    headers=merged_headers,
                ) as client:
                    response = client.request(
                        method=method.upper(),
                        url=url,
                        params=params,
                        data=data,
                        json=json_body,
                    )
                    response.raise_for_status()
                    return response
            except Exception as exc:  # pragma: no cover - network boundary
                last_error = exc
        raise FlyerFetchError(f"Download fallito per {url}: {last_error}")

    def resolve_url(self, base_url: str, candidate_url: str) -> str:
        return urljoin(base_url, candidate_url)

    def _ensure_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise FlyerFetchError(f"Schema URL non supportato: {url}")

        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = self._robots_cache.get(robots_url)
        if parser is None:
            parser = RobotFileParser()
            try:
                parser.set_url(robots_url)
                parser.read()
            except Exception:
                parser = RobotFileParser()
                parser.parse([])
            self._robots_cache[robots_url] = parser

        if not parser.can_fetch(self.settings.update_user_agent, url):
            raise FlyerFetchError(f"Accesso bloccato da robots.txt per {url}")


def _infer_suffix(*, url: str, content_type: str) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.casefold()
    if suffix in {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".html"}:
        return suffix
    lowered_content_type = content_type.casefold()
    if "pdf" in lowered_content_type:
        return ".pdf"
    if "png" in lowered_content_type:
        return ".png"
    if "jpeg" in lowered_content_type or "jpg" in lowered_content_type:
        return ".jpg"
    if "html" in lowered_content_type or "javascript" in lowered_content_type:
        return ".html"
    if "json" in lowered_content_type:
        return ".json"
    return ".bin"
