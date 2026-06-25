from app.schemas import SourceRegistryItem


TODO_VERIFY_SOURCE_URL = "TODO_VERIFY_SOURCE_URL"

CRAI_CIBELE_URL = "https://crai.it/negozi-e-volantini/6257-crai-cibele"
EUROSPIN_CASTALDI_URL = "http://eurospin.it/punti-vendita/catania-via-castaldi/"


DEFAULT_SOURCE_REGISTRY: list[SourceRegistryItem] = [
    SourceRegistryItem(
        source_key="coop-catania",
        store="Coop",
        source_url=TODO_VERIFY_SOURCE_URL,
        source_type="webpage",
        city_filter="Catania",
        province_filter="CT",
        active=False,
        priority=50,
        parser_strategy="generic_flyer_page",
        notes="Fonte Coop non ancora verificata. Lasciata inattiva finche' non viene impostato un URL reale.",
    ),
    SourceRegistryItem(
        source_key="conad-catania",
        store="Conad",
        source_url=TODO_VERIFY_SOURCE_URL,
        source_type="webpage",
        city_filter="Catania",
        province_filter="CT",
        active=False,
        priority=50,
        parser_strategy="generic_flyer_page",
        notes="Fonte Conad non ancora verificata. Lasciata inattiva finche' non viene impostato un URL reale.",
    ),
    SourceRegistryItem(
        source_key="deco-catania",
        store="Decò",
        source_url=TODO_VERIFY_SOURCE_URL,
        source_type="webpage",
        city_filter="Catania",
        province_filter="CT",
        active=False,
        priority=50,
        parser_strategy="generic_flyer_page",
        notes="Fonte Deco non ancora verificata. Lasciata inattiva finche' non viene impostato un URL reale.",
    ),
    SourceRegistryItem(
        source_key="famila-catania",
        store="Famila",
        source_url=TODO_VERIFY_SOURCE_URL,
        source_type="webpage",
        city_filter="Catania",
        province_filter="CT",
        active=False,
        priority=50,
        parser_strategy="generic_flyer_page",
        notes="Fonte Famila non ancora verificata. Lasciata inattiva finche' non viene impostato un URL reale.",
    ),
    SourceRegistryItem(
        source_key="md-catania",
        store="MD",
        source_url=TODO_VERIFY_SOURCE_URL,
        source_type="webpage",
        city_filter="Catania",
        province_filter="CT",
        active=False,
        priority=50,
        parser_strategy="generic_flyer_page",
        notes="Fonte MD non ancora verificata. Lasciata inattiva finche' non viene impostato un URL reale.",
    ),
    SourceRegistryItem(
        source_key="eurospin-catania",
        store="Eurospin",
        source_url=EUROSPIN_CASTALDI_URL,
        source_type="webpage",
        city_filter="Catania",
        province_filter="CT",
        active=True,
        priority=1,
        parser_strategy="eurospin_store_page",
        notes="Fonte reale del punto vendita Eurospin di Via Castaldi a Catania.",
        selectors={"flyer_link": "a[href*='volantino-store-eurospin']"},
        store_location="Eurospin Catania Via Castaldi",
    ),
    SourceRegistryItem(
        source_key="lidl-catania",
        store="Lidl",
        source_url=TODO_VERIFY_SOURCE_URL,
        source_type="webpage",
        city_filter="Catania",
        province_filter="CT",
        active=False,
        priority=50,
        parser_strategy="generic_flyer_page",
        notes="Fonte Lidl non ancora verificata. Lasciata inattiva finche' non viene impostato un URL reale.",
    ),
    SourceRegistryItem(
        source_key="spaccio-alimentare-catania",
        store="Spaccio Alimentare",
        source_url=TODO_VERIFY_SOURCE_URL,
        source_type="webpage",
        city_filter="Catania",
        province_filter="CT",
        active=False,
        priority=50,
        parser_strategy="generic_flyer_page",
        notes="Fonte Spaccio Alimentare non ancora verificata. Lasciata inattiva finche' non viene impostato un URL reale.",
    ),
    SourceRegistryItem(
        source_key="crai-catania",
        store="Crai",
        source_url=CRAI_CIBELE_URL,
        source_type="webpage",
        city_filter="Catania",
        province_filter="CT",
        active=True,
        priority=1,
        parser_strategy="crai_store_flyer_page",
        notes="Fonte reale del punto vendita CRAI Cibele di Catania.",
        selectors={"flyer_link": "a[href$='.pdf']"},
        store_location="CRAI Cibele Catania",
    ),
]


def get_source_registry(
    *,
    active_only: bool = False,
    store: str | None = None,
) -> list[SourceRegistryItem]:
    sources = DEFAULT_SOURCE_REGISTRY
    if active_only:
        sources = [source for source in sources if source.active]
    if store:
        sources = [source for source in sources if source.store.casefold() == store.casefold()]
    return list(sources)
