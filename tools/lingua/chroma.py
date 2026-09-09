"""Load a register's linguistic bits into a local ChromaDB.

Each bit — one lexicon term, one phrasing, one relation edge — becomes one
document in a "bits" collection persisted under corpora/<name>/<vN>/chroma/.
Creating a store is opt-in (`uv run python -m tools.lingua chroma`) because
chromadb's default embedding function downloads a small ONNX model on first
use. Once a store exists, the default build keeps it fresh: a fingerprint of
the built bits is kept beside the store, and a build whose bits no longer
match re-ingests automatically — so /translate runs (which end in a build)
never leave a stale store behind. `check` warns (and `check --strict` fails)
on a stale store instead of touching it.

Documents carry the prose an embedding should see; metadata carries the
viewer route (`href`) and provenance so a retrieval hit can be resolved back
to a page without re-reading the YAML.

The module is also runnable as a query bridge for the web viewer's smart
navigator (which cannot read an embedded chroma store from Node):

    echo "the selection" | python -m tools.lingua.chroma query <chroma-dir> <n>

prints a JSON list of {id, document, metadata, distance}, or exits 3 when
the directory holds no store (the viewer then falls back to its candidate
index).
"""

import hashlib
import json
import sys
from pathlib import Path

from .dimensions.base import LinguaDataError
from .status import RegisterBundle

COLLECTION = "bits"

# Written beside the store at ingest time; a mismatch against the current
# data files marks the store stale. A sidecar (not collection metadata) so
# staleness checks never have to import chromadb.
FINGERPRINT_FILE = ".bits-fingerprint"


def store_dir(bundle: RegisterBundle) -> Path:
    return bundle.data_dir.parent / "chroma"


def bits_fingerprint(
    ids: list[str], docs: list[str], metas: list[dict]
) -> str:
    payload = json.dumps([ids, docs, metas], sort_keys=True,
                         ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def staleness(bundle: RegisterBundle) -> str:
    """"absent" (never opted in), "fresh", or "stale". Pure file reads plus
    bit building — safe for `check`, which writes nothing."""
    chroma_dir = store_dir(bundle)
    if not (chroma_dir / "chroma.sqlite3").exists():
        return "absent"
    try:
        stored = (chroma_dir / FINGERPRINT_FILE).read_text().strip()
    except OSError:
        return "stale"  # store without a fingerprint — rebuild to be sure
    return "fresh" if stored == bits_fingerprint(*build_bits(bundle)) else "stale"


def refresh_if_stale(bundle: RegisterBundle) -> int | None:
    """Re-ingest an existing store whose bits drifted from data/*.yaml.
    Returns the bit count when a rebuild happened, else None. Never creates
    a store — opting in stays explicit via the chroma subcommand."""
    if staleness(bundle) != "stale":
        return None
    return ingest(bundle)


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
    chroma_dir = store_dir(bundle)
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
    (chroma_dir / FINGERPRINT_FILE).write_text(
        bits_fingerprint(ids, docs, metas) + "\n")
    return len(ids)


def query_bits(chroma_dir: Path, text: str, n: int) -> list[dict]:
    """Nearest bits to `text` from a register's store, best first."""
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(chroma_dir), settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_collection(COLLECTION)
    count = collection.count()
    if count == 0:
        return []
    res = collection.query(query_texts=[text], n_results=min(n, count))
    return [
        {"id": id_, "document": doc, "metadata": meta, "distance": dist}
        for id_, doc, meta, dist in zip(
            res["ids"][0],
            res["documents"][0],
            res["metadatas"][0],
            res["distances"][0],
        )
    ]


def _main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "query":
        print("usage: echo <text> | python -m tools.lingua.chroma "
              "query <chroma-dir> <n>", file=sys.stderr)
        return 2
    chroma_dir = Path(argv[1])
    if not (chroma_dir / "chroma.sqlite3").exists():
        print("no store — run `uv run python -m tools.lingua chroma` first",
              file=sys.stderr)
        return 3
    try:
        n = int(argv[2])
    except ValueError:
        print(f"n must be an integer, got {argv[2]!r}", file=sys.stderr)
        return 2
    text = sys.stdin.read().strip()
    if not text:
        print("empty query text on stdin", file=sys.stderr)
        return 2
    print(json.dumps(query_bits(chroma_dir, text, n)))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
