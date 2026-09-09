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
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": props,
    }


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
        _key(c): {"id": c.id, "modes": modes_needed(bundle, c, mode)}
        for c in chapters
    }

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
              f"next: author --apply")
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
    print("next: uv run python -m tools.lingua author --collect [--wait]")
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
        print("run was synchronous — results already collected; "
              "next: author --apply")
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
            failed.append((chapter_id, result.result.type))
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
    print("next: uv run python -m tools.lingua author --apply")
    return 1 if failed else 0


# --- apply -------------------------------------------------------------------

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
    for local, dims in applied.items():
        note = ""
        if local in demoted_report:
            note = f"  (auto-demoted: {', '.join(demoted_report[local])})"
        print(f"{verb} {local}: {', '.join(dims)}{note}")
    for local, dims in failures.items():
        for dim, problems in dims.items():
            print(f"REJECTED {local} {dim}:")
            for problem in problems:
                print(f"  - {problem}")
    if failures and not check:
        (wd / "failures.json").write_text(json.dumps(failures, indent=2))
        print("rejected payloads recorded — fix via: author --retry <id>")

    if gated:
        gate_dir = wd / "gated"
        gate_dir.mkdir(exist_ok=True)
        print("\nHELD for the redefinition gate (review, then run the "
              "printed commands):")
        for chapter, result in gated:
            for redef in result["redefinitions"]:
                current = bundle.data["lexicon"].get(redef["slug"], {})
                print(f"  {chapter.local_id}: {redef['slug']} "
                      f"(now defined by {current.get('defined_in', '?')}) — "
                      f"{redef['reason']}")
            for dim in dimensions.REGISTRY:
                if not result.get(dim):
                    continue
                path = gate_dir / f"{_key(chapter)}-{dim}.json"
                path.write_text(json.dumps(result[dim], indent=2))
                flag = " --redefine" if dim == "lexicon" else ""
                print(f"    uv run python -m tools.lingua set {dim} "
                      f"{chapter.id} --from {path}{flag}")
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
        print(f"{chapter.id}: re-authored — next: author --apply")
    return 0
