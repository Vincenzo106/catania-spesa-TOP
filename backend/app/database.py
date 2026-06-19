import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from app.schemas import OfferCreate, OfferRecord


CREATE_OFFERS_TABLE = """
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store TEXT NOT NULL,
    category TEXT NOT NULL,
    product_name TEXT NOT NULL,
    brand TEXT,
    original_price REAL,
    discounted_price REAL NOT NULL,
    discount_percentage REAL,
    flyer_valid_until TEXT,
    source_filename TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


class OffersRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(CREATE_OFFERS_TABLE)
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _to_record(row: sqlite3.Row) -> OfferRecord:
        valid_until = row["flyer_valid_until"]
        created_at = row["created_at"]
        return OfferRecord(
            id=row["id"],
            store=row["store"],
            category=row["category"],
            product_name=row["product_name"],
            brand=row["brand"],
            original_price=row["original_price"],
            discounted_price=row["discounted_price"],
            discount_percentage=row["discount_percentage"],
            flyer_valid_until=date.fromisoformat(valid_until) if valid_until else None,
            source_filename=row["source_filename"],
            is_demo=bool(row["is_demo"]),
            created_at=datetime.fromisoformat(created_at),
        )

    def has_offers(self) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM offers").fetchone()
        return bool(row["count"])

    def seed_demo_offers(self, demo_file: Path) -> int:
        if self.has_offers():
            return 0

        payload = json.loads(demo_file.read_text(encoding="utf-8"))
        demo_offers = [OfferCreate(**item, is_demo=True) for item in payload]
        self.insert_offers(demo_offers)
        return len(demo_offers)

    def insert_offers(self, offers: Iterable[OfferCreate]) -> list[OfferRecord]:
        created_at = datetime.utcnow().replace(microsecond=0).isoformat()
        records: list[OfferRecord] = []
        with self._connect() as connection:
            for offer in offers:
                cursor = connection.execute(
                    """
                    INSERT INTO offers (
                        store,
                        category,
                        product_name,
                        brand,
                        original_price,
                        discounted_price,
                        discount_percentage,
                        flyer_valid_until,
                        source_filename,
                        is_demo,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        offer.store,
                        offer.category,
                        offer.product_name,
                        offer.brand,
                        offer.original_price,
                        offer.discounted_price,
                        offer.discount_percentage,
                        offer.flyer_valid_until.isoformat() if offer.flyer_valid_until else None,
                        offer.source_filename,
                        int(offer.is_demo),
                        created_at,
                    ),
                )
                records.append(
                    OfferRecord(
                        id=cursor.lastrowid,
                        created_at=datetime.fromisoformat(created_at),
                        **offer.model_dump(),
                    )
                )
            connection.commit()
        return records

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
                "SELECT DISTINCT store FROM offers ORDER BY store COLLATE NOCASE ASC"
            ).fetchall()
        return [row["store"] for row in rows]

    def list_categories(self, store: str | None = None) -> list[str]:
        query = "SELECT DISTINCT category FROM offers"
        parameters: list[str] = []
        if store:
            query += " WHERE store = ?"
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
        where_clauses: list[str] = []
        parameters: list[str | int] = []

        if store:
            where_clauses.append("store = ?")
            parameters.append(store)
        if category:
            where_clauses.append("category = ?")
            parameters.append(category)
        if search:
            where_clauses.append("(product_name LIKE ? OR COALESCE(brand, '') LIKE ?)")
            parameters.extend([f"%{search}%", f"%{search}%"])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
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
        where_clauses = ["discount_percentage IS NOT NULL"]
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
