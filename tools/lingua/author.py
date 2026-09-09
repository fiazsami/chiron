"""API-native authoring stage: extract linguistic structure via the Claude API.

Replaces interactive-agent authoring for bulk extraction. One run targets one
register; each chapter becomes one Messages API request — Sonnet-class model,
structured outputs (the payload schema is enforced by the API), a shared
prompt-cache prefix (system charter + translation requirements + methodology
+ slug index), and the Batch API's 50% discount by default (`--sync` for a
handful of chapters).

The single-writer discipline is unchanged: results land as JSON files under
the register's work/authoring/ dir, and `author --apply` pushes them through
the same validate/apply/dump path as `set` — quote grounding, schema caps,
and slug checks all still gate every write. Cross-chapter define-conflicts
that authors could not see (they run in parallel) are resolved
deterministically: the earlier chapter in register order keeps the
definition, later payloads are demoted to mention-only (anchors preserved,
no tokens spent). Declared redefinitions are never auto-applied — they hold
the chapter for a human gate.

    uv run python -m tools.lingua author <register|group|ids...> [--sync]
    uv run python -m tools.lingua author --collect [<register>] [--wait]
    uv run python -m tools.lingua author --apply [<register>] [--check]
    uv run python -m tools.lingua author --retry <id...>
"""

import json
import re
import sys
import time
from pathlib import Path

from . import dimensions
from .dimensions.base import SetContext
from .extract import (
    content_lines, current_entry_lines, meta_lines, methodology_lines,
    requirements_lines, slug_index_lines,
)
from .model import Chapter
from .status import RegisterBundle
from .where import cmd, state_line

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_EFFORT = "medium"
MAX_TOKENS = 16_000
POLL_SECONDS = 30


class AuthorError(Exception):
    pass


def _anthropic():
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise AuthorError(
            "the 'anthropic' package is required for authoring — run `uv sync`"
        ) from exc
    return anthropic


def _auth_error(exc: BaseException) -> AuthorError:
    return AuthorError(
        "no API credentials — set ANTHROPIC_API_KEY in the environment "
        "(or log in with `ant auth login`) and re-run; the authoring stage "
        f"calls the Claude API directly ({exc})"
    )


SYSTEM = """\
You are the linguistic-extraction author for chiron. You extract one \
chapter's contribution to a corpus register's linguistic structure — the \
lexicon (what things are called here), the phrasebook (canonical phrasings \
for instructing an agent about this corpus), and the concept relations \
(typed links between terms) — as JSON payloads applied by a machine-owned \
pipeline.

Grounding rules (mechanically enforced — violations bounce the payload):
- The provided chapter material is your ONLY source of truth. If the \
chapter doesn't say it, it does not go in; the chapter wins over your own \
knowledge.
- Every anchor quote must be copied VERBATIM from the chapter material \
(whitespace is normalized; 8-240 chars; single line). The pipeline rejects \
quotes it cannot find. An anchor's "chapter" is always the target chapter's \
register-local id. For code chapters, every anchor also needs a "path" \
naming one of the chapter's files.
- Reuse slugs from the Lexicon slug index — never mint a new slug for a \
term that already exists. To anchor an existing term here, use a \
mention-only entry: ONLY slug, "define": false, and anchors.
- "define": true on a slug the index attributes to another chapter is a \
redefinition: keep it only if this chapter should own the definition, and \
declare it in "redefinitions" with a reason. Undeclared conflicts are \
demoted to mentions automatically — the anchors survive, the prose is \
dropped.
- Phrasebook "terms" and relation "from"/"to" may reference existing \
lexicon slugs or slugs your own lexicon payload defines — nothing else.
- Follow the embedded methodology section for each dimension, and honor \
the register's translation requirements.

Author only the dimensions the task line requests. Quality over coverage: \
a few load-bearing entries beat many incidental ones."""

_ANCHOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["chapter", "quote"],
    "properties": {
        "chapter": {"type": "string"},
        "path": {"type": "string"},
        "quote": {"type": "string", "minLength": 8, "maxLength": 240},
    },
}

_DIM_SCHEMAS = {
    "lexicon": {
        "type": "object",
        "additionalProperties": False,
        "required": ["terms"],
        "properties": {
            "terms": {
                "type": "array", "minItems": 1, "maxItems": 40,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["slug", "define", "anchors"],
                    "properties": {
                        "slug": {"type": "string"},
                        "define": {"type": "boolean"},
                        "term": {"type": "string", "maxLength": 80},
                        "kind": {"enum": list(dimensions.lexicon.KINDS)},
                        "definition": {"type": "string", "maxLength": 400},
                        "aliases": {
                            "type": "array", "maxItems": 6,
                            "items": {"type": "string", "maxLength": 80},
                        },
                        "anchors": {
                            "type": "array", "minItems": 1, "maxItems": 8,
                            "items": _ANCHOR_SCHEMA,
                        },
                    },
                },
            },
        },
    },
    "phrasebook": {
        "type": "object",
        "additionalProperties": False,
        "required": ["phrases"],
        "properties": {
            "phrases": {
                "type": "array", "minItems": 1, "maxItems": 15,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["slug", "phrase", "intent", "terms", "anchors"],
                    "properties": {
                        "slug": {"type": "string"},
                        "phrase": {"type": "string", "maxLength": 160},
                        "intent": {"type": "string", "maxLength": 160},
                        "template": {"type": "string", "maxLength": 300},
                        "terms": {
                            "type": "array", "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "anchors": {
                            "type": "array", "minItems": 1, "maxItems": 8,
                            "items": _ANCHOR_SCHEMA,
                        },
                    },
                },
            },
        },
    },
    "concept-relations": {
        "type": "object",
        "additionalProperties": False,
        "required": ["edges"],
        "properties": {
            "edges": {
                "type": "array", "minItems": 1, "maxItems": 30,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["from", "to", "type", "gloss", "anchors"],
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "type": {"enum": list(dimensions.relations.TYPES)},
                        "gloss": {"type": "string", "maxLength": 200},
                        "anchors": {
                            "type": "array", "minItems": 1, "maxItems": 8,
                            "items": _ANCHOR_SCHEMA,
                        },
                    },
                },
            },
        },
    },
}


# Constraint keywords the structured-outputs schema subset rejects (the API
# returns invalid_request naming them, e.g. "'maxItems' is not supported").
# Dropping them is harmless: validate_payload enforces every cap at apply
# time — the API schema only has to pin the structure.
_UNSUPPORTED_KEYS = {"maxItems", "minItems", "maxLength", "minLength",
                     "pattern", "format"}


def _sanitize(schema):
    if isinstance(schema, dict):
        return {k: _sanitize(v) for k, v in schema.items()
                if k not in _UNSUPPORTED_KEYS}
    if isinstance(schema, list):
        return [_sanitize(v) for v in schema]
    return schema


def result_schema(modes: list[str]) -> dict:
    """One schema per run mode-set: requested dimensions are required, so the
    model can never silently skip one; nothing else is representable."""
    props = {
        "redefinitions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["slug", "reason"],
                "properties": {
                    "slug": {"type": "string"},
                    "reason": {"type": "string", "maxLength": 300},
                },
            },
        },
        "notes": {"type": "string", "maxLength": 2000},
    }
    required = ["redefinitions"]
    for slug in modes:
        props[slug] = _DIM_SCHEMAS[slug]
        required.append(slug)
    return _sanitize({
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": props,
    })


# --- prompt assembly ---------------------------------------------------------

def shared_context(bundle: RegisterBundle) -> str:
    """The run-stable block: identical for every chapter of a run, so it
    rides one prompt-cache prefix (system charter + this block)."""
    return "\n".join(
        requirements_lines(bundle.corpus)
        + methodology_lines(list(bundle.tracked_modes))
        + slug_index_lines(bundle)
    )


def chapter_message(chapter: Chapter, bundle: RegisterBundle,
                    modes: list[str], feedback: str | None = None) -> str:
    out = (
        meta_lines(chapter, bundle)
        + content_lines(chapter, bundle.corpus)
        + current_entry_lines(chapter, bundle, modes)
    )
    out.append(f"Task: author these dimensions for chapter "
               f"{chapter.local_id}: {', '.join(modes)}.")
    if feedback:
        out += ["", "Your previous payload was rejected. Fix every item:",
                feedback]
    return "\n".join(out)


def build_params(bundle: RegisterBundle, chapter: Chapter, modes: list[str],
                 model: str, effort: str, shared: str,
                 feedback: str | None = None) -> dict:
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": [
            {"type": "text", "text": SYSTEM},
            {"type": "text", "text": shared,
             "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [{
            "role": "user",
            "content": chapter_message(chapter, bundle, modes, feedback),
        }],
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": result_schema(modes)},
        },
    }


# --- work dir ----------------------------------------------------------------

def work_dir(bundle: RegisterBundle) -> Path:
    return bundle.data_dir.parent / "work" / "authoring"


def _key(chapter: Chapter) -> str:
    return chapter.local_id.replace("/", "--")


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def modes_needed(bundle: RegisterBundle, chapter: Chapter,
                 mode: str | None) -> list[str]:
    if mode:
        return [mode]
    states = bundle.chapter_states(chapter)
    needed = [m for m in bundle.tracked_modes if states[m] != "ok"]
    return needed or list(bundle.tracked_modes)


# --- submit ------------------------------------------------------------------

def _parse_result_text(message) -> dict:
    if message.stop_reason == "refusal":
        raise AuthorError("the model refused this chapter")
    if message.stop_reason == "max_tokens":
        raise AuthorError("payload truncated at max_tokens — retry")
    text = next((b.text for b in message.content if b.type == "text"), "")
    return json.loads(text)


def submit(bundle: RegisterBundle, chapters: list[Chapter], mode: str | None,
           model: str, effort: str, sync: bool) -> int:
    anthropic = _anthropic()
    client = anthropic.Anthropic()
    shared = shared_context(bundle)
    wd = work_dir(bundle)
    (wd / "results").mkdir(parents=True, exist_ok=True)
    plan = {
        _key(c): {"id": c.id, "modes": modes_needed(bundle, c, mode),
                  "attempts": 0, "parked": None}
        for c in chapters
    }
    # A new run owns the slate. Without this a chapter whose collect fails
    # silently re-applies a stale result from an earlier run.
    for key in plan:
        (wd / "results" / f"{key}.json").unlink(missing_ok=True)
    (wd / "failures.json").unlink(missing_ok=True)

    if sync:
        for chapter in chapters:
            modes = plan[_key(chapter)]["modes"]
            params = build_params(bundle, chapter, modes, model, effort, shared)
            message = client.messages.create(**params)
            result = _parse_result_text(message)
            (wd / "results" / f"{_key(chapter)}.json").write_text(
                json.dumps(result, indent=2))
            print(f"{chapter.id}: authored ({', '.join(modes)}) — "
                  f"in {message.usage.input_tokens} / "
                  f"out {message.usage.output_tokens} tokens")
        (wd / "run.json").write_text(json.dumps(
            {"batch_id": None, "model": model, "effort": effort,
             "chapters": plan, "created_at": time.time()}, indent=2))
        print(f"{len(chapters)} chapter(s) authored synchronously — "
              f"next: {cmd('author --apply')}")
        return 0

    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    requests = [
        Request(
            custom_id=_key(chapter),
            params=MessageCreateParamsNonStreaming(**build_params(
                bundle, chapter, plan[_key(chapter)]["modes"],
                model, effort, shared)),
        )
        for chapter in chapters
    ]
    batch = client.messages.batches.create(requests=requests)
    (wd / "run.json").write_text(json.dumps(
        {"batch_id": batch.id, "model": model, "effort": effort,
         "chapters": plan, "created_at": time.time()}, indent=2))
    print(f"submitted batch {batch.id}: {len(chapters)} chapter(s), "
          f"model {model}, effort {effort} (Batch API — 50% token pricing)")
    print(f"next: {cmd('author --collect --wait')}")
    return 0


# --- collect -----------------------------------------------------------------

def collect(bundle: RegisterBundle, wait: bool) -> int:
    anthropic = _anthropic()
    client = anthropic.Anthropic()
    wd = work_dir(bundle)
    run = _load_json(wd / "run.json", None)
    if not run:
        raise AuthorError(f"no authoring run found under {wd}")
    if run["batch_id"] is None:
        print(f"run was synchronous — results already collected; "
              f"next: {cmd('author --apply')}")
        return 0

    while True:
        batch = client.messages.batches.retrieve(run["batch_id"])
        if batch.processing_status == "ended":
            break
        if not wait:
            print(f"batch {run['batch_id']}: {batch.processing_status} "
                  f"({batch.request_counts.processing} processing) — "
                  f"re-run with --wait to block until done")
            return 0
        time.sleep(POLL_SECONDS)

    usage_in = usage_out = cache_read = 0
    ok, failed = [], []
    for result in client.messages.batches.results(run["batch_id"]):
        key = result.custom_id
        chapter_id = run["chapters"].get(key, {}).get("id", key)
        if result.result.type != "succeeded":
            detail = result.result.type
            if result.result.type == "errored":
                err = result.result.error.model_dump()
                detail = err.get("error", {}).get("message", "errored")
            failed.append((chapter_id, detail))
            continue
        message = result.result.message
        usage_in += message.usage.input_tokens
        usage_out += message.usage.output_tokens
        cache_read += message.usage.cache_read_input_tokens or 0
        try:
            payload = _parse_result_text(message)
        except (AuthorError, json.JSONDecodeError) as exc:
            failed.append((chapter_id, str(exc)))
            continue
        (wd / "results" / f"{key}.json").write_text(json.dumps(payload, indent=2))
        redefs = payload.get("redefinitions") or []
        flag = f"  ({len(redefs)} declared redefinition(s) — human gate)" \
            if redefs else ""
        ok.append(chapter_id + flag)

    print(f"collected {len(ok)} result(s):")
    for line in ok:
        print(f"  {line}")
    for chapter_id, why in failed:
        print(f"  FAILED {chapter_id}: {why}")
    print(f"usage: {usage_in} in ({cache_read} cached) / {usage_out} out "
          f"— billed at 50% batch pricing")
    if failed:
        ids = " ".join(chapter_id for chapter_id, _ in failed)
        print(f"next: {cmd('author --apply')}, then re-submit the failures: "
              f"{cmd(f'author {ids} --sync')}")
    else:
        print(f"next: {cmd('author --apply')}")
    return 1 if failed else 0


# --- apply -------------------------------------------------------------------

def normalize_anchors(payload: dict, chapter: Chapter, corpus) -> dict:
    """Mechanical anchor normalization, content untouched. Models sometimes
    label anchors with the chapter's slug or full id instead of the
    register-local id — but the anchor's chapter IS the target by contract,
    so it is rewritten unconditionally (a quote genuinely from another
    chapter still fails the grounding check). Quotes are whitespace-collapsed
    — the exact equivalence the grounding check applies. On a code chapter,
    a `path` that is missing, unknown, or names a unit file that does NOT
    contain the quote is re-anchored to the first unit file that does
    (primary file first, then adapter order) — models often anchor to the
    file where walkthrough code ends up rather than the file quoting it."""
    from .dimensions import base as dimbase

    unit_rels = {
        p.relative_to(corpus.root).as_posix(): p for p in chapter.unit_paths
    }
    # Deterministic search order: primary first, then the adapter's order.
    ordered = list(chapter.unit_paths)
    if chapter.primary_path in ordered:
        ordered.remove(chapter.primary_path)
        ordered.insert(0, chapter.primary_path)
    texts: dict[Path, str] = {}

    def contains(p: Path, needle: str) -> bool:
        if p not in texts:
            texts[p] = dimbase.normalize(p.read_text(errors="replace"))
        return needle in texts[p]

    def fix(anchor: dict) -> dict:
        anchor = dict(anchor)
        anchor["chapter"] = chapter.local_id
        if isinstance(anchor.get("quote"), str):
            anchor["quote"] = dimbase.normalize(anchor["quote"])
        if chapter.kind == "code" and isinstance(anchor.get("quote"), str):
            needle = anchor["quote"]
            declared = unit_rels.get(anchor.get("path"))
            if needle and (declared is None or not contains(declared, needle)):
                for p in ordered:
                    if contains(p, needle):
                        anchor["path"] = p.relative_to(corpus.root).as_posix()
                        break
        return anchor

    fixed = json.loads(json.dumps(payload))  # deep copy, JSON-shaped anyway
    for entry in fixed.get("terms", []) or []:
        entry["anchors"] = [fix(a) for a in entry.get("anchors", [])]
    for entry in fixed.get("phrases", []) or []:
        entry["anchors"] = [fix(a) for a in entry.get("anchors", [])]
    for entry in fixed.get("edges", []) or []:
        entry["anchors"] = [fix(a) for a in entry.get("anchors", [])]
    return fixed


def demote_conflicts(payload: dict, chapter: Chapter, lexicon_data: dict,
                     declared: set[str]) -> tuple[dict, list[str]]:
    """Deterministic resolution of parallel-author collisions: an undeclared
    define on a slug another chapter owns becomes a mention (anchors kept,
    prose dropped). Declared redefinitions never reach here — those chapters
    are held for the human gate."""
    demoted: list[str] = []
    terms = []
    for term in payload.get("terms", []):
        slug = term.get("slug")
        owner = lexicon_data.get(slug, {}).get("defined_in")
        if (term.get("define") and owner and owner != chapter.local_id
                and slug not in declared):
            term = {"slug": slug, "define": False,
                    "anchors": term.get("anchors", [])}
            demoted.append(slug)
        terms.append(term)
    return {"terms": terms}, demoted


COLLECTION_KEY = {"lexicon": "terms", "phrasebook": "phrases",
                  "concept-relations": "edges"}


def _entry_block(entry: dict, indent: str) -> list[str]:
    """One lexicon entry, shown the way a human needs to weigh it: the term,
    its kind, its definition, and the anchor that grounds it."""
    out = [f"{indent}{entry.get('term', '?')}  ({entry.get('kind', '?')})",
           f"{indent}  {entry.get('definition', '')}"]
    anchors = entry.get("anchors") or []
    if anchors:
        quote = str(anchors[0].get("quote", "")).strip()
        out.append(f'{indent}  evidence {anchors[0].get("chapter", "?")} '
                   f'"{quote}"')
    return out


def _print_gate(bundle: RegisterBundle, wd: Path, gated: list) -> None:
    """The redefinition gate. A gate that cannot show its material is a bug,
    not a gate — so both definitions are printed with their anchors, and both
    branches are runnable commands. Nothing is hand-edited."""
    gate_dir = wd / "gated"
    gate_dir.mkdir(exist_ok=True)
    print(f"\n{len(gated)} chapter(s) HELD for the redefinition gate — their "
          f"lexicon, phrasebook and concept-relations are all unapplied until "
          f"you run the commands below.")
    for chapter, result in gated:
        proposed = {
            t.get("slug"): t
            for t in (result.get("lexicon") or {}).get("terms", [])
        }
        for redef in result["redefinitions"]:
            slug = redef["slug"]
            current = bundle.data["lexicon"].get(slug, {})
            owner = current.get("defined_in") or "nothing yet"
            print(f"\n  {chapter.id}: {slug}")
            print(f"    reason: {redef.get('reason', '')}")
            print(f"    current definition (owned by {owner}):")
            for line in _entry_block(current, "      "):
                print(line)
            print(f"    proposed definition (from {chapter.local_id}):")
            for line in _entry_block(proposed.get(slug, {}), "      "):
                print(line)
        # Both branches are payload files the CLI writes; the reject branch is
        # demote_conflicts applied mechanically, so nobody edits JSON by hand.
        lex = result.get("lexicon")
        if lex and lex.get("terms"):
            keep = gate_dir / f"{_key(chapter)}-lexicon.json"
            keep.write_text(json.dumps(lex, indent=2))
            demoted_payload, _ = demote_conflicts(
                dict(lex), chapter, bundle.data["lexicon"], set())
            drop = gate_dir / f"{_key(chapter)}-lexicon.demoted.json"
            drop.write_text(json.dumps(demoted_payload, indent=2))
            print(f"    accept:  "
                  f"{cmd(f'set lexicon {chapter.id} --from {keep} --redefine')}")
            print(f"    reject:  "
                  f"{cmd(f'set lexicon {chapter.id} --from {drop}')}")
        for dim in dimensions.REGISTRY:
            if dim == "lexicon" or not result.get(dim):
                continue
            path = gate_dir / f"{_key(chapter)}-{dim}.json"
            path.write_text(json.dumps(result[dim], indent=2))
            print(f"    then:    "
                  f"{cmd(f'set {dim} {chapter.id} --from {path}')}")


def apply_results(bundle: RegisterBundle, check: bool) -> int:
    wd = work_dir(bundle)
    run = _load_json(wd / "run.json", None)
    if not run:
        raise AuthorError(f"no authoring run found under {wd}")

    by_local = {c.local_id: c for c in bundle.corpus.chapters}
    ordered: list[tuple[Chapter, dict]] = []
    for key, info in run["chapters"].items():
        result = _load_json(wd / "results" / f"{key}.json", None)
        # local id from the stored full id — the key's separator is lossy
        # for group ids containing hyphens.
        local = info["id"].split("/", 2)[2]
        if result is not None and local in by_local:
            ordered.append((by_local[local], result))
    ordered.sort(key=lambda pair: bundle.corpus.chapters.index(pair[0]))
    if not ordered:
        raise AuthorError("no collected results to apply — run author --collect")

    gated = [(c, r) for c, r in ordered if r.get("redefinitions")]
    ready = [(c, r) for c, r in ordered if not r.get("redefinitions")]
    failures: dict[str, dict] = {}
    applied: dict[str, list[str]] = {}
    demoted_report: dict[str, list[str]] = {}
    skip: set[str] = set()

    for dim in dimensions.REGISTRY:
        module = dimensions.REGISTRY[dim]
        for chapter, result in ready:
            if chapter.local_id in skip:
                continue
            payload = result.get(dim)
            if not payload:
                continue
            # The API schema can't express minItems: an author with nothing
            # to contribute returns an empty collection — a skip, not an error.
            if not payload.get(COLLECTION_KEY[dim]):
                continue
            payload = normalize_anchors(payload, chapter, bundle.corpus)
            if dim == "lexicon":
                payload, demoted = demote_conflicts(
                    payload, chapter, bundle.data["lexicon"], set())
                if demoted:
                    demoted_report[chapter.local_id] = demoted
            ctx = SetContext(chapter=chapter, corpus=bundle.corpus,
                             data=bundle.data, redefine=False)
            problems = module.validate_payload(payload, ctx)
            if problems:
                failures.setdefault(chapter.local_id, {})[dim] = problems
                if dim == "lexicon":
                    # Later dimensions reference these slugs; don't cascade.
                    skip.add(chapter.local_id)
                continue
            new_data = module.apply(bundle.data[dim], ctx, payload)
            if not check:
                module.dump(bundle.data_dir / module.DATA_FILENAME, new_data)
            bundle.data[dim] = new_data
            applied.setdefault(chapter.local_id, []).append(dim)

    verb = "would apply" if check else "applied"
    # Voice law 2: a line addressed to a human carries the full chapter id.
    full = {c.local_id: c.id for c in bundle.corpus.chapters}
    for local, dims in applied.items():
        note = ""
        if local in demoted_report:
            note = f"  (auto-demoted: {', '.join(demoted_report[local])})"
        print(f"{verb} {full.get(local, local)}: {', '.join(dims)}{note}")
    for local, dims in failures.items():
        for dim, problems in dims.items():
            print(f"REJECTED {full.get(local, local)} {dim}:")
            for problem in problems:
                print(f"  - {problem}")
    # A lexicon rejection cancels the chapter's other dimensions. That used to
    # happen in silence, which is exactly what made triage guesswork.
    for chapter, result in ready:
        if chapter.local_id not in skip:
            continue
        cancelled = [
            d for d in dimensions.REGISTRY
            if d != "lexicon" and result.get(d)
            and result[d].get(COLLECTION_KEY[d])
        ]
        if cancelled:
            print(f"skipped {chapter.id} {', '.join(cancelled)} — lexicon "
                  f"rejected (they reference its slugs)")
    if not check:
        if failures:
            (wd / "failures.json").write_text(json.dumps(failures, indent=2))
            print(f"rejected payloads recorded — triage first: "
                  f"/ch:verify {bundle.corpus.name}/{bundle.corpus.register} "
                  f"(or {cmd('author --status')})")
        else:
            (wd / "failures.json").unlink(missing_ok=True)
    # Voice law 3: exit 0 states what is now true; silence is never success.
    if not failures and not gated:
        print(f"{verb} {len(applied)} chapter(s); nothing rejected or held")

    if gated:
        _print_gate(bundle, wd, gated)
    return 1 if failures else 0


# --- retry -------------------------------------------------------------------

def retry(bundle: RegisterBundle, chapters: list[Chapter], model: str,
          effort: str) -> int:
    anthropic = _anthropic()
    client = anthropic.Anthropic()
    wd = work_dir(bundle)
    run = _load_json(wd / "run.json", None)
    if not run:
        raise AuthorError(f"no authoring run found under {wd}")
    failures = _load_json(wd / "failures.json", {})
    shared = shared_context(bundle)

    for chapter in chapters:
        key = _key(chapter)
        info = run["chapters"].get(key)
        if info is None:
            raise AuthorError(f"{chapter.id} is not part of the current run")
        info["attempts"] = int(info.get("attempts") or 0) + 1
        prior = _load_json(wd / "results" / f"{key}.json", {})
        problems = failures.get(chapter.local_id, {})
        feedback_lines = []
        for dim, issues in problems.items():
            feedback_lines.append(f"{dim}:")
            feedback_lines += [f"  - {issue}" for issue in issues]
        feedback = "\n".join(feedback_lines) or "(no stored violations)"
        feedback += "\n\nYour previous payload:\n" + json.dumps(prior, indent=2)
        params = build_params(bundle, chapter, info["modes"], model, effort,
                              shared, feedback=feedback)
        message = client.messages.create(**params)
        result = _parse_result_text(message)
        (wd / "results" / f"{key}.json").write_text(json.dumps(result, indent=2))
        (wd / "run.json").write_text(json.dumps(run, indent=2))
        print(f"{chapter.id}: re-authored (attempt {info['attempts']}) — "
              f"next: {cmd('author --apply')}")
    return 0


# --- run status ---------------------------------------------------------------

_MENTION_BOUNCE = re.compile(r"'([^']+)' is not in the lexicon")


def _definers(wd: Path, planned: dict) -> dict[str, str]:
    """slug -> the run-local key of the chapter whose payload defines it."""
    out: dict[str, str] = {}
    for key in planned:
        result = _load_json(wd / "results" / f"{key}.json", None) or {}
        for term in (result.get("lexicon") or {}).get("terms", []):
            if term.get("define") and term.get("slug"):
                out.setdefault(term["slug"], key)
    return out


def run_status(bundle: RegisterBundle) -> int:
    """What the current authoring run actually did, decided from files rather
    than inferred by a model. /ch:verify reads this and judges only what is
    left genuinely ambiguous."""
    wd = work_dir(bundle)
    run = _load_json(wd / "run.json", None)
    if not run:
        raise AuthorError(
            f"no authoring run found under {wd} — start one with "
            f"{cmd(f'author {bundle.corpus.name}/{bundle.corpus.register}')}")
    planned: dict = run["chapters"]
    results_dir = wd / "results"
    failures = _load_json(wd / "failures.json", {})
    gate_dir = wd / "gated"
    gated_keys = {
        p.name.split("-lexicon")[0].split("-phrasebook")[0]
        .split("-concept-relations")[0]
        for p in (gate_dir.glob("*.json") if gate_dir.is_dir() else [])
    }
    by_local = {c.local_id: c for c in bundle.corpus.chapters}
    key_local = {k: info["id"].split("/", 2)[2] for k, info in planned.items()}

    print(f"run       {bundle.corpus.name}/{bundle.corpus.register} · "
          f"{'batch ' + run['batch_id'] if run.get('batch_id') else 'sync'} · "
          f"model {run.get('model')} · effort {run.get('effort')}")
    print(f"planned   {len(planned)} chapter(s)\n")

    rows, retry_ids, parked = [], [], []
    for key, info in planned.items():
        local = key_local[key]
        chapter = by_local.get(local)
        has_result = (results_dir / f"{key}.json").exists()
        attempts = int(info.get("attempts") or 0)
        if info.get("parked"):
            state = f"parked ({info['parked']})"
            parked.append(info["id"])
        elif not has_result:
            state = "no result — collect-level failure"
        elif local in failures:
            state = "REJECTED " + ", ".join(failures[local])
        elif key in gated_keys:
            state = "HELD (redefinition gate)"
        elif chapter is not None and all(
                s == "ok" for s in bundle.chapter_states(chapter).values()):
            state = "applied"
        else:
            state = "author found nothing to contribute"
        rows.append((info["id"], attempts, state))
    width = max((len(r[0]) for r in rows), default=10)
    for chapter_id, attempts, state in rows:
        print(f"  {chapter_id:<{width}}  attempts {attempts}  {state}")

    # --- health checks --------------------------------------------------------
    notes: list[str] = []
    missing = [i for i, _, s in rows if s.startswith("no result")]
    if missing:
        notes.append(
            f"{len(missing)} chapter(s) never produced a result — the fix is a "
            f"fresh run for those ids ({cmd('author <ids> --sync')}), not a retry")
    newest = max((p.stat().st_mtime for p in results_dir.glob("*.json")),
                 default=0.0)
    fail_path = wd / "failures.json"
    if failures and fail_path.exists() and fail_path.stat().st_mtime < newest:
        notes.append("failures.json is older than the newest result — it "
                     "describes a previous round; re-apply before triaging")
    orphans = [p.stem for p in results_dir.glob("*.json") if p.stem not in planned]
    if orphans:
        notes.append(
            f"{len(orphans)} result file(s) are not part of this run "
            f"({', '.join(sorted(orphans)[:5])}…) — leftovers from an earlier run")
    for note in notes:
        print(f"\n  note: {note}")

    # --- cascade ordering -----------------------------------------------------
    definers = _definers(wd, planned)
    cascades: list[str] = []
    for local, dims in failures.items():
        for dim, problems in dims.items():
            for problem in problems:
                match = _MENTION_BOUNCE.search(problem)
                if not match:
                    continue
                definer_key = definers.get(match.group(1))
                if definer_key is None:
                    continue
                definer_local = key_local.get(definer_key)
                if definer_local in failures or definer_key in gated_keys:
                    cascades.append(
                        f"{planned[definer_key]['id']} defines "
                        f"'{match.group(1)}' and bounced too — "
                        f"{by_local[local].id if local in by_local else local} "
                        f"is a cascade, not a genuine error")
                    if definer_key not in retry_ids:
                        retry_ids.append(definer_key)
    for local in failures:
        key = next((k for k, v in key_local.items() if v == local), None)
        if key and key not in retry_ids:
            retry_ids.append(key)
    if cascades:
        print("\n  cascades (retry the definer in the same set — apply "
              "processes register order, so the definition lands first):")
        for line in dict.fromkeys(cascades):
            print(f"    {line}")

    print()
    if retry_ids:
        capped = [k for k in retry_ids if int(planned[k].get("attempts") or 0) >= 2]
        live = [k for k in retry_ids if k not in capped]
        if live:
            ids = " ".join(planned[k]["id"] for k in live)
            print(f"next: {cmd(f'author --retry {ids}')}, then "
                  f"{cmd('author --apply')}")
        for key in capped:
            print(f"needs human review: {planned[key]['id']} "
                  f"(at the 2-retry cap)")
    elif gated_keys:
        print(f"next: {cmd('author --apply')} to reprint the redefinition "
              f"gate, then run the accept/reject command it prints")
    else:
        print(f"next: {state_line(bundle).split('next: ', 1)[-1]}")
    for chapter_id in parked:
        print(f"parked: {chapter_id}")
    return 1 if failures else 0
