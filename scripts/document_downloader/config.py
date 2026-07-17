from __future__ import annotations

from .models import SourceConfig

SOURCES: dict[str, SourceConfig] = {
    "bdu": SourceConfig(
        key="bdu",
        name="Bahir Dar University Institutional Repository",
        kind="bdu_legacy_rest",
        base_url="http://ir.bdu.edu.et",
        endpoint="http://ir.bdu.edu.et/rest/items",
        metadata_prefix="oai_dc",
    ),
    "wku": SourceConfig(
        key="wku",
        name="Wolkite University Research Publication System",
        kind="wku_rest",
        base_url="https://rps.wku.edu.et",
        endpoint=("https://rps.wku.edu.et/server/api/discover/search/objects"),
        metadata_prefix="oai_dc",
    ),
    "aau": SourceConfig(
        key="aau",
        name="Addis Ababa University Electronic Theses and Dissertations",
        kind="aau_dspace7",
        base_url="https://etd.aau.edu.et",
        endpoint="https://etd.aau.edu.et/server/api/discover/search/objects",
    ),
}
