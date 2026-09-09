"""Load a register's linguistic bits into a local ChromaDB.

Each bit — one lexicon term, one phrasing, one relation edge — becomes one
document in a "bits" collection persisted under corpora/<name>/<vN>/chroma/.
Ingestion is opt-in (`uv run python -m tools.lingua chroma`) rather than part
of the default build: chromadb's default embedding function downloads a small
ONNX model on first use, and the web viewer's smart navigator does not query
the store yet (ingestion now, retrieval later).

Documents carry the prose an embedding should see; metadata carries the
viewer route (`href`) and provenance so a retrieval hit can be resolved back
to a page without re-reading the YAML.
"""

from .dimensions.base import LinguaDataError
from .status import RegisterBundle

COLLECTION = "bits"


def build_bits(
    bundle: RegisterBundle,
) -> tuple[list[str], list[str], list[dict]]:
    """(ids, documents, metadatas) for every bit of the register."""
    corpus = bundle.corpus
    base = f"/{corpus.name}/{corpus.register}"
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []

    def chapters_of(anchors: list[dict]) -> str:
        return ", ".join(sorted({a["chapter"] for a in anchors}))

    if "lexicon" in bundle.tracked_modes:
        for slug, entry in sorted(bundle.data["lexicon"].items()):
            doc = f"{entry['term']} ({entry['kind']}): {entry['definition']}"
            if entry.get("aliases"):
                doc += f" Also known as: {', '.join(entry['aliases'])}."
            ids.append(f"term:{slug}")
            docs.append(doc)
            metas.append({
                "kind": "term",
                "slug": slug,
                "href": f"{base}/lexicon/{slug}",
                "defined_in": entry["defined_in"],
                "chapters": chapters_of(entry["anchors"]),
            })

    if "phrasebook" in bundle.tracked_modes:
        for slug, entry in sorted(bundle.data["phrasebook"].items()):
            doc = f"{entry['phrase']} — {entry['intent']}"
            if entry.get("template"):
                doc += f"\nTemplate: {entry['template']}"
            ids.append(f"phrase:{slug}")
            docs.append(doc)
            metas.append({
                "kind": "phrase",
                "slug": slug,
                "href": f"{base}/phrasebook/{slug}",
                "terms": ", ".join(entry["terms"]),
                "chapters": chapters_of(entry["anchors"]),
            })

    if "concept-relations" in bundle.tracked_modes:
        seen: dict[str, int] = {}
        for edge in bundle.data["concept-relations"]["edges"]:
            eid = f"relation:{edge['from']}--{edge['type']}--{edge['to']}"
            # Parallel edges are legal data; ids must still be unique.
            if eid in seen:
                seen[eid] += 1
                eid = f"{eid}--{seen[eid]}"
            else:
                seen[eid] = 0
            ids.append(eid)
            docs.append(
                f"{edge['from']} {edge['type']} {edge['to']}: {edge['gloss']}"
            )
            metas.append({
                "kind": "relation",
                "slug": f"{edge['from']}--{edge['type']}--{edge['to']}",
                "href": f"{base}/relations/{edge['type']}",
                "type": edge["type"],
                "from": edge["from"],
                "to": edge["to"],
                "chapters": chapters_of(edge["anchors"]),
            })

    return ids, docs, metas


def ingest(bundle: RegisterBundle) -> int:
    """Rebuild the register's chroma store from its data files; returns the
    number of bits written. The collection is dropped and re-added so the
    store always mirrors data/*.yaml exactly."""
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:
        raise LinguaDataError(
            "chromadb is not installed — run `uv sync` (it is a project "
            "dependency) or `uv add chromadb`"
        ) from exc

    ids, docs, metas = build_bits(bundle)
    chroma_dir = bundle.data_dir.parent / "chroma"
    client = chromadb.PersistentClient(
        path=str(chroma_dir), settings=Settings(anonymized_telemetry=False)
    )
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass  # first run — nothing to drop
    collection = client.create_collection(
        COLLECTION,
        metadata={"corpus": bundle.corpus.name,
                  "register": bundle.corpus.register},
    )
    if ids:
        collection.add(ids=ids, documents=docs, metadatas=metas)
    return len(ids)
