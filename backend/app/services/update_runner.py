from datetime import datetime

from app.config import Settings
from app.database import OffersRepository
from app.schemas import AdminUpdateResponse, SourceCheckResult
from app.services.flyer_fetcher import FetchResult, FlyerFetchError, FlyerFetcher
from app.services.flyer_parser import FlyerParser, FlyerParserError
from app.services.offer_normalizer import normalize_extracted_batch
from app.services.source_discovery import DiscoveryResult, SourceDiscoveryService
from app.services.source_registry import get_source_registry
from app.services.update_metadata import UpdateMetadataManager


class UpdateRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: OffersRepository,
        fetcher: FlyerFetcher,
        discovery_service: SourceDiscoveryService,
        flyer_parser: FlyerParser,
        metadata_manager: UpdateMetadataManager,
    ):
        self.settings = settings
        self.repository = repository
        self.fetcher = fetcher
        self.discovery_service = discovery_service
        self.flyer_parser = flyer_parser
        self.metadata_manager = metadata_manager

    def run_all_updates(self) -> AdminUpdateResponse:
        return self._run(get_source_registry(active_only=True))

    def run_store_update(self, store: str) -> AdminUpdateResponse:
        return self._run(get_source_registry(active_only=True, store=store))

    def _run(self, sources) -> AdminUpdateResponse:
        started_at = datetime.utcnow().replace(microsecond=0)
        source_results: list[SourceCheckResult] = []
        stores_checked: list[str] = []
        stores_updated: list[str] = []
        errors: list[str] = []
        flyers_found = 0
        flyers_changed = 0
        offers_extracted = 0
        offers_added = 0
        offers_updated = 0
        offers_skipped = 0

        for source in sources:
            previous_state = self.metadata_manager.get_source_state(source.source_key)
            checked_at = datetime.utcnow().replace(microsecond=0)
            stores_checked.append(source.store)

            discovery = self.discovery_service.discover(source, previous_state)
            if discovery.flyers_found:
                flyers_found += discovery.flyers_found

            if discovery.status in {"inactive", "manual_only", "pending_configuration"}:
                source_results.append(
                    self._build_source_result(
                        discovery=discovery,
                        checked_at=checked_at,
                        finished_at=datetime.utcnow().replace(microsecond=0),
                    )
                )
                self.metadata_manager.mark_source_checked(
                    source,
                    flyer_url=previous_state.last_seen_flyer_url if previous_state else None,
                    flyer_hash=previous_state.last_seen_hash if previous_state else None,
                    flyer_title=previous_state.last_flyer_title if previous_state else None,
                    checked_at=checked_at,
                    success_at=previous_state.last_success_at if previous_state else None,
                    change_detected=False,
                    error=discovery.error,
                )
                continue

            if discovery.status not in {"candidate_found", "html_offers_detected"}:
                if discovery.error:
                    errors.append(f"{source.store}: {discovery.error}")
                source_results.append(
                    self._build_source_result(
                        discovery=discovery,
                        checked_at=checked_at,
                        finished_at=datetime.utcnow().replace(microsecond=0),
                    )
                )
                self.metadata_manager.mark_source_checked(
                    source,
                    flyer_url=previous_state.last_seen_flyer_url if previous_state else None,
                    flyer_hash=previous_state.last_seen_hash if previous_state else None,
                    flyer_title=discovery.flyer_title or (previous_state.last_flyer_title if previous_state else None),
                    checked_at=checked_at,
                    success_at=previous_state.last_success_at if previous_state else None,
                    change_detected=False,
                    error=discovery.error,
                )
                continue

            try:
                fetched = self._fetch_discovered_content(discovery)
                changed = self._has_source_changed(discovery, fetched, previous_state)
                if not changed:
                    finished_at = datetime.utcnow().replace(microsecond=0)
                    source_results.append(
                        SourceCheckResult(
                            source_key=source.source_key,
                            store=source.store,
                            source_url=source.source_url,
                            source_type=source.source_type,
                            status="no_change",
                            change_detected=False,
                            flyers_found=discovery.flyers_found,
                            flyer_url=discovery.content_url,
                            flyer_title=discovery.flyer_title,
                            flyer_hash=fetched.content_hash,
                            checked_at=checked_at,
                            finished_at=finished_at,
                        )
                    )
                    self.metadata_manager.mark_source_checked(
                        source,
                        flyer_url=discovery.content_url,
                        flyer_hash=fetched.content_hash,
                        flyer_title=discovery.flyer_title,
                        checked_at=checked_at,
                        success_at=previous_state.last_success_at if previous_state else checked_at,
                        change_detected=False,
                        error=None,
                    )
                    continue

                flyers_changed += 1
                parsed_batch = self.flyer_parser.parse(
                    store=source.store,
                    discovery=discovery,
                    fetched=fetched,
                )
                normalized_offers = normalize_extracted_batch(
                    store=source.store,
                    source_filename=fetched.local_path.name if fetched.local_path else f"{source.source_key}.html",
                    extracted_batch=parsed_batch,
                    source=f"source-registry:{source.source_key}",
                    source_url=source.source_url,
                    source_type=source.source_type,
                    flyer_url=discovery.content_metadata.get("flyer_url") or discovery.content_url,
                    flyer_title=discovery.content_metadata.get("flyer_title") or discovery.flyer_title,
                    store_location=source.store_location,
                    city=source.city_filter or "Catania",
                    is_demo=False,
                )
                offers_extracted += len(normalized_offers)
                if not normalized_offers:
                    raise FlyerParserError("Nessuna offerta valida estratta dal volantino trovato.")

                write_result = self.repository.refresh_store_offers(source.store, normalized_offers)
                offers_added += write_result.added
                offers_updated += write_result.updated
                offers_skipped += write_result.skipped
                stores_updated.append(source.store)
                finished_at = datetime.utcnow().replace(microsecond=0)

                source_results.append(
                    SourceCheckResult(
                        source_key=source.source_key,
                        store=source.store,
                        source_url=source.source_url,
                        source_type=source.source_type,
                        status="updated",
                        change_detected=True,
                        flyers_found=discovery.flyers_found,
                        flyer_url=discovery.content_url,
                        flyer_title=discovery.flyer_title,
                        flyer_hash=fetched.content_hash,
                        offers_extracted=len(normalized_offers),
                        offers_added=write_result.added,
                        offers_updated=write_result.updated,
                        offers_skipped=write_result.skipped,
                        checked_at=checked_at,
                        finished_at=finished_at,
                    )
                )
                self.metadata_manager.mark_source_checked(
                    source,
                    flyer_url=discovery.content_url,
                    flyer_hash=fetched.content_hash,
                    flyer_title=discovery.flyer_title,
                    checked_at=checked_at,
                    success_at=finished_at,
                    change_detected=True,
                    error=None,
                )
            except (FlyerFetchError, FlyerParserError) as exc:
                finished_at = datetime.utcnow().replace(microsecond=0)
                errors.append(f"{source.store}: {exc}")
                source_results.append(
                    SourceCheckResult(
                        source_key=source.source_key,
                        store=source.store,
                        source_url=source.source_url,
                        source_type=source.source_type,
                        status="error",
                        change_detected=False,
                        flyers_found=discovery.flyers_found,
                        flyer_url=discovery.content_url,
                        flyer_title=discovery.flyer_title,
                        error=str(exc),
                        checked_at=checked_at,
                        finished_at=finished_at,
                    )
                )
                self.metadata_manager.mark_source_checked(
                    source,
                    flyer_url=discovery.content_url or (previous_state.last_seen_flyer_url if previous_state else None),
                    flyer_hash=previous_state.last_seen_hash if previous_state else None,
                    flyer_title=discovery.flyer_title or (previous_state.last_flyer_title if previous_state else None),
                    checked_at=checked_at,
                    success_at=previous_state.last_success_at if previous_state else None,
                    change_detected=False,
                    error=str(exc),
                )
            except Exception as exc:  # pragma: no cover - defensive boundary
                finished_at = datetime.utcnow().replace(microsecond=0)
                errors.append(f"{source.store}: {exc}")
                source_results.append(
                    SourceCheckResult(
                        source_key=source.source_key,
                        store=source.store,
                        source_url=source.source_url,
                        source_type=source.source_type,
                        status="error",
                        change_detected=False,
                        flyers_found=discovery.flyers_found,
                        flyer_url=discovery.content_url,
                        flyer_title=discovery.flyer_title,
                        error=str(exc),
                        checked_at=checked_at,
                        finished_at=finished_at,
                    )
                )
                self.metadata_manager.mark_source_checked(
                    source,
                    flyer_url=discovery.content_url or (previous_state.last_seen_flyer_url if previous_state else None),
                    flyer_hash=previous_state.last_seen_hash if previous_state else None,
                    flyer_title=discovery.flyer_title or (previous_state.last_flyer_title if previous_state else None),
                    checked_at=checked_at,
                    success_at=previous_state.last_success_at if previous_state else None,
                    change_detected=False,
                    error=str(exc),
                )

        finished_at = datetime.utcnow().replace(microsecond=0)
        stores_checked = _unique(stores_checked)
        stores_updated = _unique(stores_updated)
        status = _compute_run_status(source_results, errors)
        report = AdminUpdateResponse(
            status=status,
            stores_checked=stores_checked,
            stores_updated=stores_updated,
            sources_checked=len(source_results),
            flyers_found=flyers_found,
            flyers_changed=flyers_changed,
            offers_extracted=offers_extracted,
            offers_added=offers_added,
            offers_updated=offers_updated,
            offers_skipped=offers_skipped,
            errors=errors,
            started_at=started_at,
            finished_at=finished_at,
            source_results=source_results,
        )
        self.metadata_manager.record_update_result(report)
        return report

    def _fetch_discovered_content(self, discovery: DiscoveryResult) -> FetchResult:
        if not discovery.content_url:
            raise FlyerFetchError("La discovery non ha restituito un contenuto scaricabile.")
        if discovery.content_kind in {"html", "eurospin-viewer"}:
            return self.fetcher.fetch_text(discovery.content_url)
        return self.fetcher.download_binary(discovery.content_url, self.settings.upload_dir)

    @staticmethod
    def _has_source_changed(discovery, fetched, previous_state) -> bool:
        if previous_state is None:
            return True
        if discovery.content_url and discovery.content_url != previous_state.last_seen_flyer_url:
            return True
        if fetched.content_hash and fetched.content_hash != previous_state.last_seen_hash:
            return True
        if discovery.flyer_title and discovery.flyer_title != previous_state.last_flyer_title:
            return True
        return bool(discovery.change_hint)

    @staticmethod
    def _build_source_result(
        *,
        discovery: DiscoveryResult,
        checked_at: datetime,
        finished_at: datetime,
    ) -> SourceCheckResult:
        return SourceCheckResult(
            source_key=discovery.source_key,
            store=discovery.store,
            source_url=discovery.source_url,
            source_type=discovery.source_type,
            status=discovery.status,
            change_detected=False,
            flyers_found=discovery.flyers_found,
            flyer_url=discovery.content_url,
            flyer_title=discovery.flyer_title,
            error=discovery.error,
            checked_at=checked_at,
            finished_at=finished_at,
        )


def _compute_run_status(source_results: list[SourceCheckResult], errors: list[str]) -> str:
    updated_sources = [result for result in source_results if result.status == "updated"]
    checked_sources = [result for result in source_results if result.status not in {"pending_configuration", "manual_only", "inactive"}]
    if errors and updated_sources:
        return "partial"
    if errors and not updated_sources and checked_sources:
        return "error"
    if updated_sources:
        return "ok"
    return "idle"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
