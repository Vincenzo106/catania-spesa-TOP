import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from app.schemas import MetadataResponse, OfferCreate, OfferRecord, SourceRegistryItem, SourceStateRecord


CREATE_OFFERS_TABLE = """
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store TEXT NOT NULL,
    category TEXT NOT NULL,
    product_name TEXT NOT NULL,
    normalized_product_name TEXT NOT NULL DEFAULT '',
    brand TEXT,
    original_price REAL,
    discounted_price REAL NOT NULL,
    discount_percentage REAL,
    unit TEXT,
    quantity TEXT,
    valid_from TEXT,
    flyer_valid_until TEXT,
    flyer_url TEXT,
    flyer_title TEXT,
    source_url TEXT,
    source_type TEXT,
    source TEXT,
    source_filename TEXT,
    store_location TEXT,
    city TEXT,
    confidence_score REAL,
    is_demo INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    extraction_batch_id TEXT,
    dedupe_key TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    created_at TEXT NOT NULL
);
"""

CREATE_UPDATE_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS update_metadata (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_successful_update TEXT,
    last_attempted_update TEXT,
    last_check TEXT,
    offers_count INTEGER NOT NULL DEFAULT 0,
    active_offers_count INTEGER NOT NULL DEFAULT 0,
    stores_json TEXT NOT NULL DEFAULT '[]',
    stores_supported_json TEXT NOT NULL DEFAULT '[]',
    stores_updated_json TEXT NOT NULL DEFAULT '[]',
    sources_checked INTEGER NOT NULL DEFAULT 0,
    errors_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'never_run',
    next_suggested_check TEXT,
    data_mode TEXT NOT NULL DEFAULT 'unknown',
    updated_at TEXT
);
"""

CREATE_SOURCE_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS source_state (
    source_key TEXT PRIMARY KEY,
    store TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    city_filter TEXT,
    province_filter TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 100,
    parser_strategy TEXT,
    notes TEXT,
    selectors_json TEXT NOT NULL DEFAULT '{}',
    direct_flyer_url TEXT,
    store_location TEXT,
    last_seen_flyer_url TEXT,
    last_seen_hash TEXT,
    last_checked_at TEXT,
    last_success_at TEXT,
    last_error TEXT,
    last_flyer_title TEXT,
    last_change_detected_at TEXT,
    updated_at TEXT
);
"""

REQUIRED_OFFER_COLUMNS = {
    "normalized_product_name": "ALTER TABLE offers ADD COLUMN normalized_product_name TEXT NOT NULL DEFAULT ''",
    "unit": "ALTER TABLE offers ADD COLUMN unit TEXT",
    "quantity": "ALTER TABLE offers ADD COLUMN quantity TEXT",
    "flyer_title": "ALTER TABLE offers ADD COLUMN flyer_title TEXT",
    "source_url": "ALTER TABLE offers ADD COLUMN source_url TEXT",
    "source_type": "ALTER TABLE offers ADD COLUMN source_type TEXT",
    "store_location": "ALTER TABLE offers ADD COLUMN store_location TEXT",
    "city": "ALTER TABLE offers ADD COLUMN city TEXT",
    "confidence_score": "ALTER TABLE offers ADD COLUMN confidence_score REAL",
    "is_active": "ALTER TABLE offers ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
    "extraction_batch_id": "ALTER TABLE offers ADD COLUMN extraction_batch_id TEXT",
    "dedupe_key": "ALTER TABLE offers ADD COLUMN dedupe_key TEXT NOT NULL DEFAULT ''",
}

REQUIRED_METADATA_COLUMNS = {
    "last_check": "ALTER TABLE update_metadata ADD COLUMN last_check TEXT",
    "active_offers_count": "ALTER TABLE update_metadata ADD COLUMN active_offers_count INTEGER NOT NULL DEFAULT 0",
    "stores_supported_json": "ALTER TABLE update_metadata ADD COLUMN stores_supported_json TEXT NOT NULL DEFAULT '[]'",
    "stores_updated_json": "ALTER TABLE update_metadata ADD COLUMN stores_updated_json TEXT NOT NULL DEFAULT '[]'",
    "sources_checked": "ALTER TABLE update_metadata ADD COLUMN sources_checked INTEGER NOT NULL DEFAULT 0",
    "next_suggested_check": "ALTER TABLE update_metadata ADD COLUMN next_suggested_check TEXT",
    "data_mode": "ALTER TABLE update_metadata ADD COLUMN data_mode TEXT NOT NULL DEFAULT 'unknown'",
}


ACTIVE_OFFERS_SQL = """
is_active = 1
AND (flyer_valid_until IS NULL OR DATE(flyer_valid_until) >= DATE('now'))
"""


@dataclass
class OfferWriteResult:
    records: list[OfferRecord]
    added: int = 0
    updated: int = 0
    skipped: int = 0


class OffersRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(CREATE_OFFERS_TABLE)
            connection.execute(CREATE_UPDATE_METADATA_TABLE)
            connection.execute(CREATE_SOURCE_STATE_TABLE)
            self._ensure_offer_columns(connection)
            self._ensure_metadata_columns(connection)
            self._ensure_metadata_row(connection)
            self._backfill_offer_derived_fields(connection)
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_offer_columns(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(offers)").fetchall()
        }
        for column_name, alter_sql in REQUIRED_OFFER_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(alter_sql)

    def _ensure_metadata_columns(self, connection: sqlite3.Connection) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(update_metadata)").fetchall()
        }
        for column_name, alter_sql in REQUIRED_METADATA_COLUMNS.items():
            if column_name not in existing_columns:
                connection.execute(alter_sql)

    def _ensure_metadata_row(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("SELECT id FROM update_metadata WHERE id = 1").fetchone()
        if row:
            return

        connection.execute(
            """
            INSERT INTO update_metadata (
                id,
                last_successful_update,
                last_attempted_update,
                last_check,
                offers_count,
                active_offers_count,
                stores_json,
                stores_supported_json,
                stores_updated_json,
                sources_checked,
                errors_json,
                status,
                next_suggested_check,
                data_mode,
                updated_at
            ) VALUES (1, NULL, NULL, NULL, 0, 0, '[]', '[]', '[]', 0, '[]', 'never_run', NULL, 'unknown', NULL)
            """
        )

    def _backfill_offer_derived_fields(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT id, store, product_name, discounted_price, flyer_valid_until, flyer_url, source_url,
                   source_filename, normalized_product_name, dedupe_key
            FROM offers
            """
        ).fetchall()
        for row in rows:
            normalized_name = row["normalized_product_name"] or _normalize_product_name(
                row["product_name"]
            )
            dedupe_key = row["dedupe_key"] or _build_dedupe_key(
                store=row["store"],
                normalized_product_name=normalized_name,
                discounted_price=row["discounted_price"],
                flyer_valid_until=row["flyer_valid_until"],
                flyer_url=row["flyer_url"],
                source_url=row["source_url"],
                source_filename=row["source_filename"],
            )
            connection.execute(
                """
                UPDATE offers
                SET normalized_product_name = ?, dedupe_key = ?
                WHERE id = ?
                """,
                (normalized_name, dedupe_key, row["id"]),
            )

    @staticmethod
    def _to_record(row: sqlite3.Row) -> OfferRecord:
        return OfferRecord(
            id=row["id"],
            store=row["store"],
            category=row["category"],
            product_name=row["product_name"],
            normalized_product_name=row["normalized_product_name"],
            brand=row["brand"],
            original_price=row["original_price"],
            discounted_price=row["discounted_price"],
            discount_percentage=row["discount_percentage"],
            unit=row["unit"] if "unit" in row.keys() else None,
            quantity=row["quantity"] if "quantity" in row.keys() else None,
            valid_from=_parse_date(row["valid_from"]),
            flyer_valid_until=_parse_date(row["flyer_valid_until"]),
            flyer_url=row["flyer_url"],
            flyer_title=row["flyer_title"] if "flyer_title" in row.keys() else None,
            source_url=row["source_url"] if "source_url" in row.keys() else None,
            source_type=row["source_type"] if "source_type" in row.keys() else None,
            source=row["source"],
            source_filename=row["source_filename"],
            store_location=row["store_location"] if "store_location" in row.keys() else None,
            city=row["city"] if "city" in row.keys() else None,
            confidence_score=row["confidence_score"] if "confidence_score" in row.keys() else None,
            is_demo=bool(row["is_demo"]),
            is_active=bool(row["is_active"]) if "is_active" in row.keys() else True,
            extraction_batch_id=row["extraction_batch_id"]
            if "extraction_batch_id" in row.keys()
            else None,
            dedupe_key=row["dedupe_key"] or "",
            updated_at=_parse_datetime(row["updated_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def has_offers(self) -> bool:
        return self.count_offers() > 0

    def count_offers(self, *, active_only: bool = False) -> int:
        query = "SELECT COUNT(*) AS count FROM offers"
        if active_only:
            query += f" WHERE {ACTIVE_OFFERS_SQL}"
        with self._connect() as connection:
            row = connection.execute(query).fetchone()
        return int(row["count"])

    def count_offers_for_store(self, store: str, *, active_only: bool = False) -> int:
        query = "SELECT COUNT(*) AS count FROM offers WHERE store = ?"
        if active_only:
            query += f" AND {ACTIVE_OFFERS_SQL}"
        with self._connect() as connection:
            row = connection.execute(query, (store,)).fetchone()
        return int(row["count"])

    def get_offer_debug_summary(self, *, store: str | None = None, sample_limit: int = 5) -> dict:
        scoped_where = ""
        scoped_params: list[str | int] = []
        if store:
            scoped_where = "WHERE store = ?"
            scoped_params.append(store)

        active_where = f"{scoped_where} {'AND' if scoped_where else 'WHERE'} {ACTIVE_OFFERS_SQL}"
        inactive_where = f"{scoped_where} {'AND' if scoped_where else 'WHERE'} is_active = 0"
        demo_where = f"{scoped_where} {'AND' if scoped_where else 'WHERE'} is_demo = 1"
        live_where = f"{scoped_where} {'AND' if scoped_where else 'WHERE'} is_demo = 0"
        expired_where = (
            f"{scoped_where} {'AND' if scoped_where else 'WHERE'} "
            "is_active = 1 AND flyer_valid_until IS NOT NULL AND DATE(flyer_valid_until) < DATE('now')"
        )
        null_validity_where = (
            f"{scoped_where} {'AND' if scoped_where else 'WHERE'} "
            "is_active = 1 AND flyer_valid_until IS NULL"
        )

        with self._connect() as connection:
            database_list = [
                {"seq": row["seq"], "name": row["name"], "file": row["file"]}
                for row in connection.execute("PRAGMA database_list").fetchall()
            ]
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM offers {scoped_where}",
                    scoped_params,
                ).fetchone()["count"]
            )
            active_total = int(
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM offers {active_where}",
                    scoped_params,
                ).fetchone()["count"]
            )
            inactive_total = int(
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM offers {inactive_where}",
                    scoped_params,
                ).fetchone()["count"]
            )
            demo_total = int(
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM offers {demo_where}",
                    scoped_params,
                ).fetchone()["count"]
            )
            live_total = int(
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM offers {live_where}",
                    scoped_params,
                ).fetchone()["count"]
            )
            expired_active_total = int(
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM offers {expired_where}",
                    scoped_params,
                ).fetchone()["count"]
            )
            active_null_validity_total = int(
                connection.execute(
                    f"SELECT COUNT(*) AS count FROM offers {null_validity_where}",
                    scoped_params,
                ).fetchone()["count"]
            )
            bounds_row = connection.execute(
                f"""
                SELECT
                    MIN(valid_from) AS min_valid_from,
                    MAX(valid_from) AS max_valid_from,
                    MIN(flyer_valid_until) AS min_flyer_valid_until,
                    MAX(flyer_valid_until) AS max_flyer_valid_until,
                    MIN(updated_at) AS min_updated_at,
                    MAX(updated_at) AS max_updated_at
                FROM offers
                {scoped_where}
                """,
                scoped_params,
            ).fetchone()
            sample_rows = [
                dict(row)
                for row in connection.execute(
                    f"""
                    SELECT
                        id,
                        store,
                        product_name,
                        discounted_price,
                        valid_from,
                        flyer_valid_until,
                        is_active,
                        is_demo,
                        updated_at,
                        flyer_url
                    FROM offers
                    {scoped_where}
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ?
                    """,
                    [*scoped_params, sample_limit],
                ).fetchall()
            ]

        db_path = self.db_path.resolve(strict=False)
        return {
            "database_path": str(db_path),
            "database_exists": db_path.exists(),
            "database_size_bytes": db_path.stat().st_size if db_path.exists() else 0,
            "sqlite_database_list": database_list,
            "store_scope": store,
            "counts": {
                "total": total,
                "active_public_filter": active_total,
                "inactive": inactive_total,
                "demo": demo_total,
                "live": live_total,
                "expired_active": expired_active_total,
                "active_null_validity": active_null_validity_total,
            },
            "date_bounds": {
                "min_valid_from": bounds_row["min_valid_from"] if bounds_row else None,
                "max_valid_from": bounds_row["max_valid_from"] if bounds_row else None,
                "min_flyer_valid_until": bounds_row["min_flyer_valid_until"] if bounds_row else None,
                "max_flyer_valid_until": bounds_row["max_flyer_valid_until"] if bounds_row else None,
                "min_updated_at": bounds_row["min_updated_at"] if bounds_row else None,
                "max_updated_at": bounds_row["max_updated_at"] if bounds_row else None,
            },
            "sample_rows": sample_rows,
            "active_filter_sql": "is_active = 1 AND (flyer_valid_until IS NULL OR DATE(flyer_valid_until) >= DATE('now'))",
        }

    def seed_demo_offers(self, demo_file: Path) -> int:
        if self.has_offers():
            return 0

        payload = json.loads(demo_file.read_text(encoding="utf-8"))
        demo_offers: list[OfferCreate] = []
        for item in payload:
            product_name = str(item.get("product_name") or "").strip()
            normalized_product_name = item.get("normalized_product_name") or _normalize_product_name(
                product_name
            )
            discounted_price = round(float(item.get("discounted_price") or 0), 2)
            dedupe_key = item.get("dedupe_key") or _build_dedupe_key(
                store=str(item.get("store") or ""),
                normalized_product_name=normalized_product_name,
                discounted_price=discounted_price,
                flyer_valid_until=item.get("flyer_valid_until"),
                flyer_url=item.get("flyer_url"),
                source_url=item.get("source_url"),
                source_filename=item.get("source_filename"),
            )
            demo_offers.append(
                OfferCreate.model_validate(
                    {
                        **item,
                        "normalized_product_name": normalized_product_name,
                        "discounted_price": discounted_price,
                        "flyer_url": item.get("flyer_url") or item.get("source_filename") or "demo-seed.json",
                        "source_url": item.get("source_url") or "demo://seed",
                        "source_type": item.get("source_type") or "demo",
                        "source": item.get("source") or f"demo:{str(item.get('store') or '').casefold()}",
                        "city": item.get("city") or "Catania",
                        "confidence_score": item.get("confidence_score") or 0.5,
                        "dedupe_key": dedupe_key,
                        "is_demo": True,
                        "is_active": True,
                    }
                )
            )
        self.upsert_offers(demo_offers)
        self.refresh_update_metadata(
            status="seeded",
            errors=[],
            last_successful_update=None,
            last_attempted_update=None,
            stores_updated=[],
            sources_checked=0,
            data_mode="demo",
        )
        return len(demo_offers)

    def insert_offers(self, offers: Iterable[OfferCreate]) -> list[OfferRecord]:
        return self.upsert_offers(offers).records

    def upsert_offers(self, offers: Iterable[OfferCreate]) -> OfferWriteResult:
        with self._connect() as connection:
            result = self._upsert_offers(connection, list(offers), replace_store=False)
            connection.commit()
        return result

    def refresh_store_offers(self, store: str, offers: Iterable[OfferCreate]) -> OfferWriteResult:
        prepared_offers = list(offers)
        normalized_store = prepared_offers[0].store if prepared_offers else store
        with self._connect() as connection:
            result = self._upsert_offers(
                connection,
                prepared_offers,
                replace_store=True,
                store_to_replace=normalized_store,
            )
            connection.commit()
        return result

    def replace_offers_for_store(self, store: str, offers: Iterable[OfferCreate]) -> list[OfferRecord]:
        return self.refresh_store_offers(store, offers).records

    def _upsert_offers(
        self,
        connection: sqlite3.Connection,
        offers: list[OfferCreate],
        *,
        replace_store: bool,
        store_to_replace: str | None = None,
    ) -> OfferWriteResult:
        created_now = datetime.utcnow().replace(microsecond=0)
        unique_offers = _deduplicate_offers(offers)
        result = OfferWriteResult(records=[])

        if replace_store and store_to_replace:
            connection.execute(
                "UPDATE offers SET is_active = 0, updated_at = ? WHERE store = ? AND is_active = 1",
                (created_now.isoformat(), store_to_replace),
            )

        for offer in unique_offers:
            existing = connection.execute(
                "SELECT * FROM offers WHERE dedupe_key = ? ORDER BY id DESC LIMIT 1",
                (offer.dedupe_key,),
            ).fetchone()
            if existing and bool(existing["is_active"]) and not replace_store:
                result.skipped += 1
                result.records.append(self._to_record(existing))
                continue

            if existing:
                updated_at = offer.updated_at or created_now
                connection.execute(
                    """
                    UPDATE offers
                    SET store = ?, category = ?, product_name = ?, normalized_product_name = ?, brand = ?,
                        original_price = ?, discounted_price = ?, discount_percentage = ?, unit = ?, quantity = ?,
                        valid_from = ?, flyer_valid_until = ?, flyer_url = ?, flyer_title = ?, source_url = ?,
                        source_type = ?, source = ?, source_filename = ?, store_location = ?, city = ?,
                        confidence_score = ?, is_demo = ?, is_active = ?, extraction_batch_id = ?, dedupe_key = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        offer.store,
                        offer.category,
                        offer.product_name,
                        offer.normalized_product_name,
                        offer.brand,
                        offer.original_price,
                        offer.discounted_price,
                        offer.discount_percentage,
                        offer.unit,
                        offer.quantity,
                        _serialize_date(offer.valid_from),
                        _serialize_date(offer.flyer_valid_until),
                        offer.flyer_url,
                        offer.flyer_title,
                        offer.source_url,
                        offer.source_type,
                        offer.source,
                        offer.source_filename,
                        offer.store_location,
                        offer.city,
                        offer.confidence_score,
                        int(offer.is_demo),
                        int(offer.is_active),
                        offer.extraction_batch_id,
                        offer.dedupe_key,
                        updated_at.isoformat(),
                        existing["id"],
                    ),
                )
                refreshed = connection.execute(
                    "SELECT * FROM offers WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
                result.updated += 1
                result.records.append(self._to_record(refreshed))
                continue

            cursor = connection.execute(
                """
                INSERT INTO offers (
                    store,
                    category,
                    product_name,
                    normalized_product_name,
                    brand,
                    original_price,
                    discounted_price,
                    discount_percentage,
                    unit,
                    quantity,
                    valid_from,
                    flyer_valid_until,
                    flyer_url,
                    flyer_title,
                    source_url,
                    source_type,
                    source,
                    source_filename,
                    store_location,
                    city,
                    confidence_score,
                    is_demo,
                    is_active,
                    extraction_batch_id,
                    dedupe_key,
                    updated_at,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    offer.store,
                    offer.category,
                    offer.product_name,
                    offer.normalized_product_name,
                    offer.brand,
                    offer.original_price,
                    offer.discounted_price,
                    offer.discount_percentage,
                    offer.unit,
                    offer.quantity,
                    _serialize_date(offer.valid_from),
                    _serialize_date(offer.flyer_valid_until),
                    offer.flyer_url,
                    offer.flyer_title,
                    offer.source_url,
                    offer.source_type,
                    offer.source,
                    offer.source_filename,
                    offer.store_location,
                    offer.city,
                    offer.confidence_score,
                    int(offer.is_demo),
                    int(offer.is_active),
                    offer.extraction_batch_id,
                    offer.dedupe_key,
                    (offer.updated_at or created_now).isoformat(),
                    created_now.isoformat(),
                ),
            )
            created_row = connection.execute(
                "SELECT * FROM offers WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
            result.added += 1
            result.records.append(self._to_record(created_row))

        return result

    def delete_offers_by_source(self, store: str, source_filename: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM offers WHERE store = ? AND source_filename = ?",
                (store, source_filename),
            )
            connection.commit()
        return cursor.rowcount

    def list_stores(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT store
                FROM offers
                WHERE {ACTIVE_OFFERS_SQL}
                ORDER BY store COLLATE NOCASE ASC
                """
            ).fetchall()
        return [row["store"] for row in rows]

    def list_supported_stores(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT store
                FROM source_state
                WHERE active = 1
                ORDER BY priority ASC, store COLLATE NOCASE ASC
                """
            ).fetchall()
        return [row["store"] for row in rows]

    def list_categories(self, store: str | None = None) -> list[str]:
        query = f"SELECT DISTINCT category FROM offers WHERE {ACTIVE_OFFERS_SQL}"
        parameters: list[str] = []
        if store:
            query += " AND store = ?"
            parameters.append(store)
        query += " ORDER BY category COLLATE NOCASE ASC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [row["category"] for row in rows]

    def list_offers(
        self,
        *,
        store: str | None = None,
        category: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[OfferRecord], int]:
        where_clauses = [ACTIVE_OFFERS_SQL]
        parameters: list[str | int] = []

        if store:
            where_clauses.append("store = ?")
            parameters.append(store)
        if category:
            where_clauses.append("category = ?")
            parameters.append(category)
        if search:
            where_clauses.append(
                "(product_name LIKE ? OR COALESCE(brand, '') LIKE ? OR COALESCE(store_location, '') LIKE ?)"
            )
            like_value = f"%{search}%"
            parameters.extend([like_value, like_value, like_value])

        where_sql = f"WHERE {' AND '.join(where_clauses)}"
        count_query = f"SELECT COUNT(*) AS count FROM offers {where_sql}"
        select_query = f"""
            SELECT *
            FROM offers
            {where_sql}
            ORDER BY COALESCE(discount_percentage, 0) DESC, discounted_price ASC, product_name ASC
            LIMIT ? OFFSET ?
        """

        with self._connect() as connection:
            total_row = connection.execute(count_query, parameters).fetchone()
            rows = connection.execute(select_query, [*parameters, limit, offset]).fetchall()

        return [self._to_record(row) for row in rows], int(total_row["count"])

    def list_best_offers(
        self,
        *,
        store: str | None = None,
        category: str | None = None,
        limit: int = 12,
    ) -> list[OfferRecord]:
        where_clauses = [ACTIVE_OFFERS_SQL, "discount_percentage IS NOT NULL"]
        parameters: list[str | int] = []

        if store:
            where_clauses.append("store = ?")
            parameters.append(store)
        if category:
            where_clauses.append("category = ?")
            parameters.append(category)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"
        query = f"""
            SELECT *
            FROM offers
            {where_sql}
            ORDER BY discount_percentage DESC, discounted_price ASC, product_name ASC
            LIMIT ?
        """

        with self._connect() as connection:
            rows = connection.execute(query, [*parameters, limit]).fetchall()
        return [self._to_record(row) for row in rows]

    def sync_source_registry(self, sources: Iterable[SourceRegistryItem]) -> None:
        now = datetime.utcnow().replace(microsecond=0).isoformat()
        with self._connect() as connection:
            for source in sources:
                connection.execute(
                    """
                    INSERT INTO source_state (
                        source_key,
                        store,
                        source_url,
                        source_type,
                        city_filter,
                        province_filter,
                        active,
                        priority,
                        parser_strategy,
                        notes,
                        selectors_json,
                        direct_flyer_url,
                        store_location,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_key) DO UPDATE SET
                        store = excluded.store,
                        source_url = excluded.source_url,
                        source_type = excluded.source_type,
                        city_filter = excluded.city_filter,
                        province_filter = excluded.province_filter,
                        active = excluded.active,
                        priority = excluded.priority,
                        parser_strategy = excluded.parser_strategy,
                        notes = excluded.notes,
                        selectors_json = excluded.selectors_json,
                        direct_flyer_url = excluded.direct_flyer_url,
                        store_location = excluded.store_location,
                        updated_at = excluded.updated_at
                    """,
                    (
                        source.source_key,
                        source.store,
                        source.source_url,
                        source.source_type,
                        source.city_filter,
                        source.province_filter,
                        int(source.active),
                        source.priority,
                        source.parser_strategy,
                        source.notes,
                        json.dumps(source.selectors, ensure_ascii=False),
                        source.direct_flyer_url,
                        source.store_location,
                        now,
                    ),
                )
            connection.commit()

    def get_source_state(self, source_key: str) -> SourceStateRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM source_state WHERE source_key = ?",
                (source_key,),
            ).fetchone()
        return self._to_source_state(row) if row else None

    def list_source_states(
        self,
        *,
        active_only: bool = False,
        store: str | None = None,
    ) -> list[SourceStateRecord]:
        query = "SELECT * FROM source_state"
        clauses: list[str] = []
        params: list[str | int] = []
        if active_only:
            clauses.append("active = 1")
        if store:
            clauses.append("store = ?")
            params.append(store)
        if clauses:
            query += f" WHERE {' AND '.join(clauses)}"
        query += " ORDER BY priority ASC, store COLLATE NOCASE ASC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._to_source_state(row) for row in rows]

    def save_source_state(self, source_state: SourceStateRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_state (
                    source_key,
                    store,
                    source_url,
                    source_type,
                    city_filter,
                    province_filter,
                    active,
                    priority,
                    parser_strategy,
                    notes,
                    selectors_json,
                    direct_flyer_url,
                    store_location,
                    last_seen_flyer_url,
                    last_seen_hash,
                    last_checked_at,
                    last_success_at,
                    last_error,
                    last_flyer_title,
                    last_change_detected_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    store = excluded.store,
                    source_url = excluded.source_url,
                    source_type = excluded.source_type,
                    city_filter = excluded.city_filter,
                    province_filter = excluded.province_filter,
                    active = excluded.active,
                    priority = excluded.priority,
                    parser_strategy = excluded.parser_strategy,
                    notes = excluded.notes,
                    selectors_json = excluded.selectors_json,
                    direct_flyer_url = excluded.direct_flyer_url,
                    store_location = excluded.store_location,
                    last_seen_flyer_url = excluded.last_seen_flyer_url,
                    last_seen_hash = excluded.last_seen_hash,
                    last_checked_at = excluded.last_checked_at,
                    last_success_at = excluded.last_success_at,
                    last_error = excluded.last_error,
                    last_flyer_title = excluded.last_flyer_title,
                    last_change_detected_at = excluded.last_change_detected_at,
                    updated_at = excluded.updated_at
                """,
                (
                    source_state.source_key,
                    source_state.store,
                    source_state.source_url,
                    source_state.source_type,
                    source_state.city_filter,
                    source_state.province_filter,
                    int(source_state.active),
                    source_state.priority,
                    source_state.parser_strategy,
                    source_state.notes,
                    json.dumps(source_state.selectors, ensure_ascii=False),
                    source_state.direct_flyer_url,
                    source_state.store_location,
                    source_state.last_seen_flyer_url,
                    source_state.last_seen_hash,
                    _serialize_datetime(source_state.last_checked_at),
                    _serialize_datetime(source_state.last_success_at),
                    source_state.last_error,
                    source_state.last_flyer_title,
                    _serialize_datetime(source_state.last_change_detected_at),
                    _serialize_datetime(source_state.updated_at),
                ),
            )
            connection.commit()

    def get_update_metadata(self) -> MetadataResponse:
        live_offers_count = self.count_offers()
        live_active_offers_count = self.count_offers(active_only=True)
        live_stores = self.list_stores()
        live_supported_stores = self.list_supported_stores()
        live_data_mode = self.get_data_mode()

        with self._connect() as connection:
            row = connection.execute("SELECT * FROM update_metadata WHERE id = 1").fetchone()

        if not row:
            return MetadataResponse(
                offers_count=live_offers_count,
                active_offers_count=live_active_offers_count,
                stores=live_stores,
                stores_supported=live_supported_stores,
                status="unknown",
                data_mode=live_data_mode,
            )

        errors = _parse_json_list(row["errors_json"])
        return MetadataResponse(
            last_successful_update=_parse_datetime(row["last_successful_update"]),
            last_attempted_update=_parse_datetime(row["last_attempted_update"]),
            last_check=_parse_datetime(row["last_check"]),
            offers_count=live_offers_count,
            active_offers_count=live_active_offers_count,
            stores=live_stores,
            stores_supported=live_supported_stores,
            stores_updated=_parse_json_list(row["stores_updated_json"]),
            sources_checked=int(row["sources_checked"] or 0),
            status=row["status"] or "unknown",
            errors=errors,
            last_errors=errors,
            next_suggested_check=_parse_datetime(row["next_suggested_check"]),
            data_mode=row["data_mode"] or live_data_mode,
            updated_at=_parse_datetime(row["updated_at"]),
        )

    def refresh_update_metadata(
        self,
        *,
        status: str,
        errors: list[str] | None,
        last_successful_update: datetime | None,
        last_attempted_update: datetime | None,
        stores_updated: list[str] | None,
        sources_checked: int,
        data_mode: str | None = None,
        next_suggested_check: datetime | None = None,
        last_check: datetime | None = None,
    ) -> MetadataResponse:
        updated_at = datetime.utcnow().replace(microsecond=0)
        metadata = MetadataResponse(
            last_successful_update=last_successful_update,
            last_attempted_update=last_attempted_update,
            last_check=last_check or last_attempted_update or updated_at,
            offers_count=self.count_offers(),
            active_offers_count=self.count_offers(active_only=True),
            stores=self.list_stores(),
            stores_supported=self.list_supported_stores(),
            stores_updated=stores_updated or [],
            sources_checked=sources_checked,
            status=status,
            errors=errors or [],
            last_errors=errors or [],
            next_suggested_check=next_suggested_check
            or _default_next_check(last_attempted_update or updated_at),
            data_mode=data_mode or self.get_data_mode(),
            updated_at=updated_at,
        )
        self.save_update_metadata(metadata)
        return metadata

    def save_update_metadata(self, metadata: MetadataResponse) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO update_metadata (
                    id,
                    last_successful_update,
                    last_attempted_update,
                    last_check,
                    offers_count,
                    active_offers_count,
                    stores_json,
                    stores_supported_json,
                    stores_updated_json,
                    sources_checked,
                    errors_json,
                    status,
                    next_suggested_check,
                    data_mode,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_successful_update = excluded.last_successful_update,
                    last_attempted_update = excluded.last_attempted_update,
                    last_check = excluded.last_check,
                    offers_count = excluded.offers_count,
                    active_offers_count = excluded.active_offers_count,
                    stores_json = excluded.stores_json,
                    stores_supported_json = excluded.stores_supported_json,
                    stores_updated_json = excluded.stores_updated_json,
                    sources_checked = excluded.sources_checked,
                    errors_json = excluded.errors_json,
                    status = excluded.status,
                    next_suggested_check = excluded.next_suggested_check,
                    data_mode = excluded.data_mode,
                    updated_at = excluded.updated_at
                """,
                (
                    1,
                    _serialize_datetime(metadata.last_successful_update),
                    _serialize_datetime(metadata.last_attempted_update),
                    _serialize_datetime(metadata.last_check),
                    metadata.offers_count,
                    metadata.active_offers_count,
                    json.dumps(metadata.stores, ensure_ascii=False),
                    json.dumps(metadata.stores_supported, ensure_ascii=False),
                    json.dumps(metadata.stores_updated, ensure_ascii=False),
                    metadata.sources_checked,
                    json.dumps(metadata.last_errors, ensure_ascii=False),
                    metadata.status,
                    _serialize_datetime(metadata.next_suggested_check),
                    metadata.data_mode,
                    _serialize_datetime(metadata.updated_at),
                ),
            )
            connection.commit()

    def get_data_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN is_demo = 1 THEN 1 ELSE 0 END) AS demo_count
                FROM offers
                """
            ).fetchone()

        total_count = int(row["total_count"] or 0)
        demo_count = int(row["demo_count"] or 0)
        if total_count == 0:
            return "empty"
        if demo_count == total_count:
            return "demo"
        if demo_count == 0:
            return "live"
        return "mixed"

    @staticmethod
    def _to_source_state(row: sqlite3.Row) -> SourceStateRecord:
        return SourceStateRecord(
            source_key=row["source_key"],
            store=row["store"],
            source_url=row["source_url"],
            source_type=row["source_type"],
            city_filter=row["city_filter"],
            province_filter=row["province_filter"],
            active=bool(row["active"]),
            priority=int(row["priority"]),
            parser_strategy=row["parser_strategy"],
            notes=row["notes"],
            selectors=_parse_json_dict(row["selectors_json"]),
            direct_flyer_url=row["direct_flyer_url"],
            store_location=row["store_location"],
            last_seen_flyer_url=row["last_seen_flyer_url"],
            last_seen_hash=row["last_seen_hash"],
            last_checked_at=_parse_datetime(row["last_checked_at"]),
            last_success_at=_parse_datetime(row["last_success_at"]),
            last_error=row["last_error"],
            last_flyer_title=row["last_flyer_title"],
            last_change_detected_at=_parse_datetime(row["last_change_detected_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )


def _deduplicate_offers(offers: Iterable[OfferCreate]) -> list[OfferCreate]:
    unique_by_key: dict[str, OfferCreate] = {}
    for offer in offers:
        unique_by_key[offer.dedupe_key] = offer
    return list(unique_by_key.values())


def _normalize_product_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _build_dedupe_key(
    *,
    store: str,
    normalized_product_name: str,
    discounted_price: float | None,
    flyer_valid_until: date | str | None,
    flyer_url: str | None,
    source_url: str | None,
    source_filename: str | None,
) -> str:
    valid_until = (
        flyer_valid_until.isoformat()
        if isinstance(flyer_valid_until, date)
        else (flyer_valid_until or "")
    )
    source_hint = flyer_url or source_url or source_filename or "no-source"
    return (
        f"{store.casefold()}|{normalized_product_name}|{round(float(discounted_price or 0), 2):.2f}"
        f"|{valid_until}|{source_hint.strip().casefold()}"
    )


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _parse_json_dict(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(item) for key, item in parsed.items()}


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _serialize_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _default_next_check(reference: datetime) -> datetime:
    return reference + timedelta(hours=12)
