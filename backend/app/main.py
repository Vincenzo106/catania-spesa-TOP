from contextlib import asynccontextmanager
import os
from pathlib import Path
import re
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import Settings, get_settings
from app.database import OffersRepository
from app.schemas import (
    AdminUpdateResponse,
    BestDealsResponse,
    ErrorResponse,
    HealthResponse,
    IngestResponse,
    MetadataResponse,
    OfferListResponse,
    StoreListResponse,
)
from app.services.flyer_fetcher import FlyerFetcher
from app.services.flyer_parser import FlyerParser
from app.services.offer_normalizer import normalize_extracted_batch
from app.services.source_discovery import SourceDiscoveryService
from app.services.source_registry import get_source_registry
from app.services.update_metadata import UpdateMetadataManager
from app.services.update_runner import UpdateRunner
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

        metadata_manager = UpdateMetadataManager(repository)
        metadata_manager.sync_source_registry()
        metadata_manager.bootstrap_if_needed()

        vision_extractor = build_vision_extractor(resolved_settings)
        fetcher = FlyerFetcher(resolved_settings)
        discovery_service = SourceDiscoveryService(
            fetcher,
            max_flyers_per_store=resolved_settings.max_flyers_per_store,
        )
        flyer_parser = FlyerParser(vision_extractor, fetcher)
        update_runner = UpdateRunner(
            settings=resolved_settings,
            repository=repository,
            fetcher=fetcher,
            discovery_service=discovery_service,
            flyer_parser=flyer_parser,
            metadata_manager=metadata_manager,
        )

        app.state.settings = resolved_settings
        app.state.repository = repository
        app.state.metadata_manager = metadata_manager
        app.state.vision_extractor = vision_extractor
        app.state.update_runner = update_runner
        yield

    app = FastAPI(
        title=resolved_settings.app_name,
        version="1.1.0",
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
        stores = _merge_unique(repository.list_supported_stores(), repository.list_stores())
        return StoreListResponse(stores=stores)

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
            available_stores=_merge_unique(repository.list_supported_stores(), repository.list_stores()),
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

    @app.get("/metadata", response_model=MetadataResponse)
    @app.get("/api/metadata", response_model=MetadataResponse)
    def get_metadata(request: Request) -> MetadataResponse:
        metadata_manager: UpdateMetadataManager = request.app.state.metadata_manager
        return metadata_manager.build_public_metadata()

    @app.post("/admin/update-offers", response_model=AdminUpdateResponse)
    def update_offers(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> AdminUpdateResponse:
        _authorize_admin(request, authorization)
        update_runner: UpdateRunner = request.app.state.update_runner
        return update_runner.run_all_updates()

    @app.post("/admin/update-store/{store_name}", response_model=AdminUpdateResponse)
    def update_single_store(
        request: Request,
        store_name: str,
        authorization: str | None = Header(default=None),
    ) -> AdminUpdateResponse:
        _authorize_admin(request, authorization)
        configured_sources = get_source_registry(active_only=True, store=store_name)
        if not configured_sources:
            raise HTTPException(status_code=404, detail=f"Nessuna fonte configurata per {store_name}.")
        update_runner: UpdateRunner = request.app.state.update_runner
        return update_runner.run_store_update(store_name)

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
        metadata_manager: UpdateMetadataManager = request.app.state.metadata_manager
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

        normalized_offers = normalize_extracted_batch(
            store=store,
            source_filename=safe_filename,
            extracted_batch=extracted_batch,
            source="manual-upload",
            source_url=None,
            source_type="manual",
            flyer_url=None,
            flyer_title=file.filename,
            store_location=None,
            city="Catania",
            is_demo=False,
        )

        if not normalized_offers:
            raise HTTPException(
                status_code=422,
                detail="No valid offers were extracted from the uploaded flyer.",
            )

        if replace_existing:
            write_result = repository.refresh_store_offers(store, normalized_offers)
        else:
            write_result = repository.upsert_offers(normalized_offers)

        metadata_manager.record_manual_ingest(store)

        return IngestResponse(
            source_filename=safe_filename,
            provider=settings.vision_provider,
            offers_created=len(write_result.records),
            records=write_result.records,
        )

    return app


app = create_app()


def _authorize_admin(request: Request, authorization: str | None) -> None:
    settings: Settings = request.app.state.settings
    if not settings.admin_update_token:
        raise HTTPException(status_code=503, detail="ADMIN_UPDATE_TOKEN is not configured.")

    expected = f"Bearer {settings.admin_update_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized.")


def _safe_upload_filename(filename: str | None) -> str:
    candidate = Path(filename or "upload").name.strip()
    suffix = Path(candidate).suffix.casefold()
    stem = Path(candidate).stem
    normalized_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("._-") or "upload"
    return f"{normalized_stem}{suffix}"


def _merge_unique(*sequences: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for sequence in sequences:
        for value in sequence:
            if value in seen:
                continue
            seen.add(value)
            merged.append(value)
    return merged


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", settings.port)),
        reload=False,
    )
