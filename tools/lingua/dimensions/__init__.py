"""Registry of shipped linguistic dimensions.

A dimension is a module exposing a uniform surface (SLUG, LABEL,
DATA_FILENAME, METHODOLOGY, load, validate_payload, apply, dump,
chapter_state, entries_for_chapter, accept_drift, count, warnings). Adding a
dimension later = one new module here + one methodology/<slug>.md + a
registry line below; a translation.yaml mode with no registry entry stays a
"recorded" mode until its machinery ships.
"""

from . import lexicon, phrasebook, relations

# Ordered: lexicon first — phrasebook and concept-relations payloads reference
# lexicon slugs, so authoring and display follow this order.
REGISTRY = {
    module.SLUG: module
    for module in (lexicon, phrasebook, relations)
}

_REQUIRED = (
    "SLUG", "LABEL", "DATA_FILENAME", "METHODOLOGY", "NOUN",
    "load", "validate_payload", "apply", "dump", "chapter_state",
    "entries_for_chapter", "accept_drift", "count", "warnings",
)
for _module in REGISTRY.values():
    _missing = [name for name in _REQUIRED if not hasattr(_module, name)]
    assert not _missing, f"dimension {_module.__name__} missing {_missing}"
