"""The one target grammar, resolved in one place.

Every chiron verb — the CLI subcommands and the /ch: skills alike — acts on a
*target*. Before this module the grammar existed three times with three
different acceptance sets (a chapter-only resolver, an author-target resolver
that took registers and groups, and a work-dir resolver that also took a bare
corpus name), which is why the skills documented three different grammars and
one of them was narrower than its own tooling.

`resolve_targets` is the single implementation; `ch resolve` prints what an
expression expands to, so the grammar can be checked rather than trusted.
"""

from dataclasses import dataclass, field

from .corpora import CorpusError
from .model import Chapter

GRAMMAR = """target grammar
  (nothing)                    the caller's stated default
  all                          every register, one selection each
  <corpus>                     a corpus, when it has exactly one register
  <corpus>/<vN>                a register
  <corpus>/<vN>/<group>        a group
  <group>/<NN>                 a chapter, when one mounted register matches
  <corpus>/<group>/<NN>        a chapter, when the corpus has one register
  <corpus>/<vN>/<group>/<NN>   a chapter, always unambiguous"""


@dataclass
class Selection:
    """One register's worth of a resolved target expression."""

    kind: str  # all | corpus | register | group | chapter
    key: tuple[str, str]  # (corpus name, register)
    chapters: list[Chapter] = field(default_factory=list)
    note: str = ""

    @property
    def register(self) -> str:
        return f"{self.key[0]}/{self.key[1]}"


def resolve_factory(bundles):
    """Chapter-id resolver over the mounted bundles. Full ids
    ("fewshot-works-academy/v1/foundations/02"), or the shorthands
    "<corpus>/<group>/<NN>" / "<group>/<NN>" when exactly one mounted
    register matches (a segment count matches only its own form). Raises
    ValueError on unknown or ambiguous ids."""
    chapters = [c for b in bundles for c in b.corpus.chapters]
    by_id = {c.id: c for c in chapters}

    def resolve(chapter_id: str) -> Chapter:
        if chapter_id in by_id:
            return by_id[chapter_id]
        matches = [
            c for c in chapters
            if c.local_id == chapter_id
            or f"{c.corpus}/{c.group}/{c.number}" == chapter_id
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"ambiguous chapter id {chapter_id!r} — candidates: "
                + ", ".join(c.id for c in matches)
            )
        raise ValueError(f"no such chapter: {chapter_id}")

    return resolve


def checked_resolver(bundles):
    """resolve_factory, with ValueError re-raised as CorpusError carrying the
    grammar — the one wording for every ambiguous or unknown target."""
    resolve = resolve_factory(bundles)

    def wrapped(chapter_id: str) -> Chapter:
        try:
            return resolve(chapter_id)
        except ValueError as exc:
            raise CorpusError(f"{exc}\n\n{GRAMMAR}") from exc

    return wrapped


def pending(bundle) -> list[Chapter]:
    """Chapters with any tracked dimension not yet ok."""
    return [
        c for c in bundle.corpus.chapters
        if any(s != "ok" for s in bundle.chapter_states(c).values())
    ]


def _key(bundle) -> tuple[str, str]:
    return (bundle.corpus.name, bundle.corpus.register)


def _registers_for(bundles, expr: str) -> list:
    return [
        b for b in bundles
        if f"{b.corpus.name}/{b.corpus.register}" == expr or b.corpus.name == expr
    ]


def resolve_targets(bundles, exprs, *, pending_only: bool = True) -> list[Selection]:
    """Expand target expressions into one Selection per register, in mounted
    order. Register, corpus and group expressions take their pending chapters
    when `pending_only`; explicit chapter ids are always taken as given."""
    resolve = checked_resolver(bundles)
    order = [_key(b) for b in bundles]
    by_key = {_key(b): b for b in bundles}
    picked: dict[tuple[str, str], Selection] = {}

    def add(bundle, kind: str, chapters: list[Chapter], note: str = "") -> None:
        sel = picked.get(_key(bundle))
        if sel is None:
            picked[_key(bundle)] = Selection(
                kind=kind, key=_key(bundle), chapters=list(chapters), note=note)
            return
        seen = {c.id for c in sel.chapters}
        sel.chapters += [c for c in chapters if c.id not in seen]
        if sel.kind != kind:
            sel.kind = "chapter" if "chapter" in (sel.kind, kind) else kind

    if not exprs or exprs == ["all"]:
        kind = "all" if exprs else "default"
        for bundle in bundles:
            chapters = pending(bundle) if pending_only else list(bundle.corpus.chapters)
            if chapters:
                add(bundle, kind, chapters)
        if not picked:
            raise CorpusError(
                "nothing to do — every tracked state is already ok"
                if pending_only else "no chapters are mounted")
        return [picked[k] for k in order if k in picked]

    for expr in exprs:
        regs = _registers_for(bundles, expr)
        if len(regs) > 1:
            raise CorpusError(
                f"{expr!r} matches several registers — name one as "
                f"<corpus>/<vN>: " + ", ".join(
                    f"{b.corpus.name}/{b.corpus.register}" for b in regs))
        if regs:
            bundle = regs[0]
            chapters = pending(bundle) if pending_only else list(bundle.corpus.chapters)
            add(bundle, "register", chapters,
                "" if chapters else "every tracked state is already ok")
            continue

        groups = [
            (b, g) for b in bundles for g in b.corpus.group_ids
            if g == expr or f"{b.corpus.name}/{b.corpus.register}/{g}" == expr
        ]
        if len(groups) > 1:
            raise CorpusError(
                f"ambiguous group {expr!r} — qualify as <corpus>/<vN>/<group>: "
                + ", ".join(f"{b.corpus.name}/{b.corpus.register}/{g}"
                            for b, g in groups))
        if groups:
            bundle, group_id = groups[0]
            source = pending(bundle) if pending_only else bundle.corpus.chapters
            add(bundle, "group", [c for c in source if c.group == group_id])
            continue

        chapter = resolve(expr)
        add(by_key[(chapter.corpus, chapter.register)], "chapter", [chapter])

    selections = [picked[k] for k in order if k in picked]
    if not any(sel.chapters for sel in selections):
        raise CorpusError(
            "no chapters to act on — every tracked state in "
            + ", ".join(sel.register for sel in selections) + " is already ok")
    return selections


def registers_for(bundles, exprs) -> list:
    """Every register a list of expressions names — for the register-scoped
    read-only surfaces. No expression, like `all`, means every mounted one:
    a reader who does not know which corpus is relevant is exactly who these
    surfaces are for."""
    if not exprs or "all" in exprs:
        return list(bundles)
    picked: list = []
    for expr in exprs:
        matched = _registers_for(bundles, expr)
        if not matched:
            raise CorpusError(
                f"{expr!r} does not name a mounted register\n\n{GRAMMAR}")
        picked += [b for b in matched if b not in picked]
    return picked


def one_register(bundles, exprs) -> object:
    """The single register an expression names — for the run-scoped author
    subcommands. With no expression, the one register that has a run."""
    if exprs:
        regs = _registers_for(bundles, exprs[0])
        if len(regs) == 1:
            return regs[0]
        raise CorpusError(
            f"{exprs[0]!r} does not name exactly one register\n\n{GRAMMAR}")
    from . import author as authormod
    with_runs = [b for b in bundles if (authormod.work_dir(b) / "run.json").exists()]
    if len(with_runs) == 1:
        return with_runs[0]
    if not with_runs:
        raise CorpusError(
            "no authoring run found — start one with "
            "`./ch author <corpus>/<vN>`")
    raise CorpusError(
        "several registers have a run — name one: "
        + ", ".join(f"{b.corpus.name}/{b.corpus.register}" for b in with_runs))


def print_resolution(bundles, exprs) -> int:
    """`ch resolve` — show what a target expression means, or the grammar."""
    selections = resolve_targets(bundles, exprs, pending_only=not exprs or exprs == ["all"])
    for sel in selections:
        print(f"register  {sel.register}")
        if sel.kind in ("default", "all"):
            print("default   every chapter with a tracked state not ok")
        if sel.note:
            print(f"note      {sel.note}")
        print(f"chapters  {len(sel.chapters)}")
        bundle = next(b for b in bundles if _key(b) == sel.key)
        for chapter in sel.chapters:
            states = bundle.chapter_states(chapter)
            line = " · ".join(f"{s} {states[s]}" for s in bundle.tracked_modes)
            print(f"          {chapter.id}   {line}")
        print()
    return 0
