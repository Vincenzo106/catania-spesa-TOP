from app.services.source_registry import TODO_VERIFY_SOURCE_URL, get_source_registry

PLACEHOLDER_SOURCE_BASE = TODO_VERIFY_SOURCE_URL


def get_flyer_sources():
    return get_source_registry()


def get_active_flyer_sources():
    return get_source_registry(active_only=True)
