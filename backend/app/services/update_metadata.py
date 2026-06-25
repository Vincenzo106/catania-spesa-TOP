from datetime import datetime

from app.database import OffersRepository
from app.schemas import AdminUpdateResponse, SourceRegistryItem, SourceStateRecord
from app.services.source_registry import get_source_registry


class UpdateMetadataManager:
    def __init__(self, repository: OffersRepository):
        self.repository = repository

    def sync_source_registry(self) -> None:
        self.repository.sync_source_registry(get_source_registry())

    def bootstrap_if_needed(self) -> None:
        metadata = self.repository.get_update_metadata()
        if (
            self.repository.has_offers()
            and metadata.offers_count == 0
            and metadata.last_successful_update is None
            and metadata.last_attempted_update is None
        ):
            self.repository.refresh_update_metadata(
                status="ready",
                errors=[],
                last_successful_update=None,
                last_attempted_update=None,
                stores_updated=[],
                sources_checked=0,
            )

    def build_public_metadata(self):
        return self.repository.get_update_metadata()

    def get_source_state(self, source_key: str) -> SourceStateRecord | None:
        return self.repository.get_source_state(source_key)

    def mark_source_checked(
        self,
        source: SourceRegistryItem | SourceStateRecord,
        *,
        flyer_url: str | None,
        flyer_hash: str | None,
        flyer_title: str | None,
        checked_at: datetime,
        success_at: datetime | None,
        change_detected: bool,
        error: str | None,
    ) -> None:
        current = self.repository.get_source_state(source.source_key)
        updated_state = SourceStateRecord(
            source_key=source.source_key,
            store=source.store,
            source_url=source.source_url,
            source_type=source.source_type,
            city_filter=source.city_filter,
            province_filter=source.province_filter,
            active=source.active,
            priority=source.priority,
            parser_strategy=source.parser_strategy,
            notes=source.notes,
            selectors=dict(source.selectors),
            direct_flyer_url=source.direct_flyer_url,
            store_location=source.store_location,
            last_seen_flyer_url=flyer_url or (current.last_seen_flyer_url if current else None),
            last_seen_hash=flyer_hash or (current.last_seen_hash if current else None),
            last_checked_at=checked_at,
            last_success_at=success_at or (current.last_success_at if current else None),
            last_error=error,
            last_flyer_title=flyer_title or (current.last_flyer_title if current else None),
            last_change_detected_at=checked_at if change_detected else (current.last_change_detected_at if current else None),
            updated_at=checked_at,
        )
        self.repository.save_source_state(updated_state)

    def record_update_result(self, report: AdminUpdateResponse) -> None:
        self.repository.refresh_update_metadata(
            status=report.status,
            errors=report.errors,
            last_successful_update=report.finished_at if report.stores_updated else self.repository.get_update_metadata().last_successful_update,
            last_attempted_update=report.finished_at,
            stores_updated=report.stores_updated,
            sources_checked=report.sources_checked,
        )

    def record_manual_ingest(self, store: str) -> None:
        previous = self.repository.get_update_metadata()
        now = datetime.utcnow().replace(microsecond=0)
        stores_updated = sorted(
            {item for item in [*previous.stores_updated, store] if item},
            key=str.casefold,
        )
        self.repository.refresh_update_metadata(
            status="ok",
            errors=[],
            last_successful_update=now,
            last_attempted_update=now,
            stores_updated=stores_updated,
            sources_checked=max(previous.sources_checked, 1),
        )
