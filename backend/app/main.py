from contextlib import asynccontextmanager
import os
from pathlib import Path
import re
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import Settings, get_settings
from app.database import OffersRepository
from app.schemas import (
    BestDealsResponse,
    ErrorResponse,
    HealthResponse,
    IngestResponse,
    OfferListResponse,
    StoreListResponse,
)
from app.services.offers import normalize_offer
from app.services.vision import VisionExtractionError, build_vision_extractor


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf"}


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_settings.upload_dir.mkdir(parents=True, exist_ok=True)

        repository = OffersRepository(resolved_settings.database_path)
        if resolved_settings.seed_demo_data:
            repository.seed_demo_offers(resolved_settings.demo_data_path)

        app.state.settings = resolved_settings
        app.state.repository = repository
        app.state.vision_extractor = build_vision_extractor(resolved_settings)
        yield

    app = FastAPI(
        title=resolved_settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        responses={500: {"model": ErrorResponse}},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_model=HealthResponse)
    def root(request: Request) -> HealthResponse:
        current_settings: Settings = request.app.state.settings
        return HealthResponse(
            status="ok",
            provider=current_settings.vision_provider,
            database_path=str(current_settings.database_path),
            seed_demo_data=current_settings.seed_demo_data,
        )

    @app.get("/health", response_model=HealthResponse)
    @app.get("/api/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        return root(request)

    @app.get("/stores", response_model=StoreListResponse)
    @app.get("/api/stores", response_model=StoreListResponse)
    def list_stores(request: Request) -> StoreListResponse:
        repository: OffersRepository = request.app.state.repository
        return StoreListResponse(stores=repository.list_stores())

    @app.get("/offers", response_model=OfferListResponse)
    @app.get("/api/offers", response_model=OfferListResponse)
    def list_offers(
        request: Request,
        store: str | None = Query(default=None),
        category: str | None = Query(default=None),
        search: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> OfferListResponse:
        repository: OffersRepository = request.app.state.repository
        items, total = repository.list_offers(
            store=store or None,
            category=category or None,
            search=search or None,
            limit=limit,
            offset=offset,
        )
        return OfferListResponse(
            items=items,
            total=total,
            available_stores=repository.list_stores(),
            available_categories=repository.list_categories(store=store or None),
        )

    @app.get("/offers/best", response_model=BestDealsResponse)
    @app.get("/api/offers/best", response_model=BestDealsResponse)
    def best_offers(
        request: Request,
        store: str | None = Query(default=None),
        category: str | None = Query(default=None),
        limit: int = Query(default=12, ge=1, le=50),
    ) -> BestDealsResponse:
        repository: OffersRepository = request.app.state.repository
        items = repository.list_best_offers(
            store=store or None,
            category=category or None,
            limit=limit,
        )
        return BestDealsResponse(items=items)

    @app.post("/offers/ingest", response_model=IngestResponse)
    async def ingest_flyer(
        request: Request,
        store: str = Form(...),
        replace_existing: bool = Form(default=False),
        file: UploadFile = File(...),
    ) -> IngestResponse:
        safe_filename = _safe_upload_filename(file.filename)
        suffix = Path(safe_filename).suffix.casefold()
        if suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Upload JPEG, PNG, or PDF flyers.",
            )

        settings: Settings = request.app.state.settings
        repository: OffersRepository = request.app.state.repository
        extractor = request.app.state.vision_extractor

        uploaded_bytes = await file.read()
        if not uploaded_bytes:
            raise HTTPException(status_code=400, detail="Uploaded flyer is empty.")

        destination = settings.upload_dir / f"{uuid4().hex}{suffix}"
        destination.write_bytes(uploaded_bytes)

        try:
            extracted_batch = extractor.extract(file_path=destination, store=store)
        except VisionExtractionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        normalized_offers = [
            normalized
            for normalized in (
                normalize_offer(
                    store=store,
                    source_filename=safe_filename,
                    extracted_offer=offer,
                )
                for offer in extracted_batch.offers
            )
            if normalized is not None
        ]

        if not normalized_offers:
            raise HTTPException(
                status_code=422,
                detail="No valid offers were extracted from the uploaded flyer.",
            )

        if replace_existing:
            repository.delete_offers_by_source(store=store, source_filename=safe_filename)

        records = repository.insert_offers(normalized_offers)
        return IngestResponse(
            source_filename=safe_filename,
            provider=settings.vision_provider,
            offers_created=len(records),
            records=records,
        )

    return app


app = create_app()


def _safe_upload_filename(filename: str | None) -> str:
    candidate = Path(filename or "upload").name.strip()
    suffix = Path(candidate).suffix.casefold()
    stem = Path(candidate).stem
    normalized_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("._-") or "upload"
    return f"{normalized_stem}{suffix}"


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", settings.port)),
        reload=False,
    )
